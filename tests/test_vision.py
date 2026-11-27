import base64
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest
from PIL import Image

from src import vision


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

    class FakeClient:
        def open(self, request, timeout):
            assert timeout == 90 and request.get_method() == "POST"
            body = json.loads(request.data)
            assert body["model"] == "vision-model-id"
            assert body[profile.token_limit_field] == 1200
            assert len(body["messages"]) == 1
            attachment, prompt = body["messages"][0]["content"]
            assert prompt["type"] == "text" and key not in json.dumps(body)
            if profile.native_messages:
                assert request.full_url == base_url + "/messages"
                assert request.get_header("X-api-key") == key
                assert request.get_header("Anthropic-version") == "2026-10-21"
                assert attachment["type"] == "image"
                assert attachment["source"]["media_type"] == "image/png"
                encoded = attachment["source"]["data"]
                answer = {"content": [{"type": "thinking"}, {"type": "text", "text": "第 1 格待人工复核"}]}
            else:
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
    assert vision.review_image(settings, png) == "第 1 格待人工复核"
    assert key not in repr(settings)


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
