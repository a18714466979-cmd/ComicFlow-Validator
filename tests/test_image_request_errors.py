"""Exercise HTTP diagnostics with synthetic responses and no provider requests."""

from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from src.image_api import IMAGE_PROVIDERS, TEXT, ImageRequestError, ImageSettings, build_image_request, submit_image


def request_settings(provider="火山方舟 Seedream"):
    preset = IMAGE_PROVIDERS[provider]
    settings = ImageSettings(provider, preset.base, preset.model, "demo-image-key")
    return settings, build_image_request(settings, TEXT, "合成测试图")


def stub_error(monkeypatch, exception):
    class Opener:
        def open(self, request, timeout):
            raise exception

    monkeypatch.setattr("src.image_api.build_opener", lambda *_: Opener())


class UnreadableErrorBody(BytesIO):
    def read(self, *args):
        raise AssertionError("provider error body was read")


@pytest.mark.parametrize(("code", "guidance", "uncertain"), (
    (401, "API Key", False),
    (403, "调用权限", False),
    (404, "接入点是否已开通", False),
    (413, "参考图的大小和数量", False),
    (429, "调用频率、配额", False),
    (408, "核对受理状态", True),
    (503, "核对受理状态", True),
))
def test_http_error_preserves_bounded_header_and_specific_guidance(monkeypatch, code, guidance, uncertain):
    settings, request = request_settings()
    headers = Message()
    headers["X-rEqUeST-ID"] = "ark-test.request_123"
    body = UnreadableErrorBody(b"do not read this")
    stub_error(monkeypatch, HTTPError(request.full_url, code, "untrusted detail", headers, body))

    with pytest.raises(ImageRequestError, match=guidance) as raised:
        submit_image(settings, request)

    assert f"HTTP {code}" in str(raised.value)
    assert raised.value.request_id == "ark-test.request_123"
    assert raised.value.uncertain is uncertain and body.closed


@pytest.mark.parametrize(("provider", "header_value"), (
    ("火山方舟 Seedream", "demo-image-key"),
    ("火山方舟 Seedream", "prefix-demo-image-key"),
    ("火山方舟 Seedream", "a" * 129),
    ("火山方舟 Seedream", "line one\nline two"),
    ("Google Gemini", "demo-image-key"),
))
def test_invalid_or_reflected_secret_request_id_is_discarded(monkeypatch, provider, header_value):
    settings, request = request_settings(provider)
    headers = Message()
    headers["X-Request-Id"] = header_value
    stub_error(monkeypatch, HTTPError(request.full_url, 401, "untrusted detail", headers, BytesIO()))

    with pytest.raises(ImageRequestError) as raised:
        submit_image(settings, request)

    assert not raised.value.request_id
    assert settings.key not in str(raised.value)


def test_timeout_remains_uncertain_without_service_request_id(monkeypatch):
    settings, request = request_settings()
    stub_error(monkeypatch, URLError(TimeoutError("untrusted detail")))

    with pytest.raises(ImageRequestError, match="服务商后台") as raised:
        submit_image(settings, request)

    assert raised.value.uncertain and not raised.value.request_id
