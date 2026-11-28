import base64
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest
from PIL import Image

from src import vision
from src.production_rules import CHINESE, ENGLISH, rule_revision


@pytest.fixture
def png():
    stream = BytesIO()
    Image.new("RGB", (24, 16)).save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize("provider", tuple(vision.PROVIDERS))
def test_review_sends_one_image_in_selected_protocol(monkeypatch, png, provider):
    profile = vision.PROVIDERS[provider]
    base_url = profile.base_url or "https://compatible.example/v1"
    key = "test-key-for-local-fixture"
    settings = vision.VisionSettings(provider, base_url, "vision-model-id", key)
    user_focus = '请细看第2格门框旁的留白和标注"局部02"。'

    class FakeClient:
        def open(self, request, timeout):
            assert timeout == 90 and request.get_method() == "POST"
            body = json.loads(request.data)
            assert body["model"] == "vision-model-id"
            assert body[profile.token_limit_field] == 1200
            assert body["messages"][-1]["role"] == "user"
            attachment, prompt = body["messages"][-1]["content"]
            assert prompt["type"] == "text" and key not in json.dumps(body)
            assert json.loads(prompt["text"]) == {"审图重点": user_focus}
            if profile.native_messages:
                assert len(body["messages"]) == 1
                assert body["system"] == [{"type": "text", "text": vision.review_instructions()}]
                assert request.full_url == base_url + "/messages"
                assert request.get_header("X-api-key") == key
                assert request.get_header("Anthropic-version") == "2026-10-21"
                assert attachment["type"] == "image"
                assert attachment["source"]["media_type"] == "image/png"
                encoded = attachment["source"]["data"]
                answer = {"content": [{"type": "thinking"}, {"type": "text", "text": "第 1 格待人工复核"}]}
            else:
                assert len(body["messages"]) == 2
                assert body["messages"][0] == {"role": "system", "content": vision.review_instructions()}
                assert request.full_url == base_url + "/chat/completions"
                assert request.get_header("Authorization") == f"Bearer {key}"
                encoded = attachment["image_url"]["url"]
                if not profile.raw_base64:
                    prefix, encoded = encoded.split(",", 1)
                    assert prefix == "data:image/png;base64"
                answer = {"choices": [{"message": {"content": "第 1 格待人工复核"}}]}
            assert base64.b64decode(encoded) == png
            return BytesIO(json.dumps(answer, ensure_ascii=False).encode())

    def fake_opener(handler):
        assert handler.redirect_request(None, None, 307, None, {}, "https://elsewhere.example") is None
        return FakeClient()

    monkeypatch.setattr(vision, "build_opener", fake_opener)
    assert vision.review_image(settings, png, focus=user_focus) == "第 1 格待人工复核"
    assert key not in repr(settings)


def test_visual_review_uses_active_workflow_and_optional_focus(png):
    settings = vision.VisionSettings("OpenAI", "https://api.openai.com/v1", "m", "key")
    body = json.loads(vision.build_request(settings, png, rules=CHINESE).data)
    assert json.loads(body["messages"][1]["content"][1]["text"]) == {"审图重点": ""}
    assert f"中文影片制作 v{rule_revision(CHINESE)}" in body["messages"][0]["content"]
    assert "可使用中文" in body["messages"][0]["content"]
    assert f"英文影片制作 v{rule_revision(ENGLISH)}" in vision.review_instructions()
    with pytest.raises(ValueError, match="审图重点最多"):
        vision.build_request(settings, png, focus="门" * (vision.MAX_REVIEW_FOCUS_CHARS + 1))


def test_rejects_non_https_and_invalid_image_before_connecting(monkeypatch, png):
    provider = "自定义 OpenAI 兼容"

    def unexpected_connection(*_args):
        pytest.fail("invalid requests should never open a connection")

    monkeypatch.setattr(vision, "build_opener", unexpected_connection)
    with pytest.raises(ValueError, match="HTTPS"):
        vision.review_image(vision.VisionSettings(provider, "http://example.com/v1", "m", "key"), png)
    with pytest.raises(OSError):
        vision.review_image(vision.VisionSettings(provider, "https://example.com/v1", "m", "key"), b"invalid")


def test_service_error_does_not_expose_response_or_key(monkeypatch, png):
    class UnauthorizedClient:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 401, "server-echoed-secret", None, None)

    monkeypatch.setattr(vision, "build_opener", lambda _handler: UnauthorizedClient())
    with pytest.raises(ValueError, match="HTTP 401") as caught:
        vision.review_image(vision.VisionSettings("Claude（Anthropic）", "https://api.anthropic.com/v1", "m", "secret"), png)
    assert "server-echoed-secret" not in str(caught.value)


@pytest.mark.parametrize("provider, reply", [
    ("OpenAI", {"choices": [{"message": {"content": "半条建议"}, "finish_reason": "length"}]}),
    ("Claude（Anthropic）", {"content": [{"type": "text", "text": "半条建议"}], "stop_reason": "max_tokens"}),
])
def test_incomplete_review_is_not_shown_as_advice(monkeypatch, png, provider, reply):
    class TruncatedClient:
        def open(self, request, timeout):
            return BytesIO(json.dumps(reply).encode("utf-8"))

    monkeypatch.setattr(vision, "build_opener", lambda _handler: TruncatedClient())
    base_url = vision.PROVIDERS[provider].base_url
    with pytest.raises(ValueError, match="审图意见未完成"):
        vision.review_image(vision.VisionSettings(provider, base_url, "m", "key"), png)


def test_large_images_are_encoded_locally_before_upload(monkeypatch):
    monkeypatch.setattr(vision, "MAX_IMAGE_BYTES", 4096)
    stream = BytesIO()
    Image.new("RGBA", (80, 50), (0, 0, 0, 0)).save(stream, format="PNG", compress_level=0)
    original = stream.getvalue()
    image, compressed = vision.prepare_review_image(original)

    assert compressed and len(image) < 4096 < len(original)
    assert vision.image_media_type(image) == "image/jpeg"
    with Image.open(BytesIO(image)) as prepared:
        assert prepared.size == (80, 50)
        assert prepared.getpixel((0, 0)) == (255, 255, 255)
