"""Exercise ecommerce provider inputs without any network or billable requests."""

import base64
import json
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from src import ecommerce_ai as ai
from src.ecommerce_project import EcommerceShot
from src.image_api import IMAGE_PROVIDERS, TEXT, ImageSettings, build_image_request
from src.vision import PROVIDERS, VisionSettings


def sample(color="red", kind="PNG"):
    output = BytesIO()
    Image.new("RGB", (18, 32), color).save(output, format=kind)
    return output.getvalue()


def fields(identity, **changes):
    row = {"id": identity, **dict.fromkeys(ai.VISUAL_FIELDS, ""),
           "characters": ["演示人"], "props": [], "contains_product": None}
    row.update(changes)
    return row


@pytest.mark.parametrize("provider", ["OpenAI", "Claude（Anthropic）", "GLM（智谱）"])
def test_vision_request_lock_and_only_safe_draft_fields(monkeypatch, provider):
    settings = VisionSettings(provider, PROVIDERS[provider].base_url, "demo-vision", "not-in-preview-secret")
    shot = EcommerceShot("01A", 100, 1200, dialogue="Look here.", contains_product=True, scene_cut=True)
    raw = sample()
    response_text = json.dumps({"shots": [fields(shot.id, action="手抬到胸口")]}, ensure_ascii=False)
    if PROVIDERS[provider].native_messages:
        response = {"content": [{"type": "text", "text": response_text}]}
    else:
        response = {"choices": [{"message": {"content": response_text}}]}

    def fake_open(request, *, timeout):
        body = json.loads(request.data)
        blocks = body["messages"][-1]["content"]
        user = json.loads(blocks[-1]["text"])
        assert user["抽帧顺序"] == [{"抽帧格号": "01", "id": "01A", "起始毫秒": 100, "结束毫秒": 1200}]
        assert user["批准对白原文（可选，仅供语境）"] == shot.dialogue
        if PROVIDERS[provider].native_messages:
            assert body["system"][0]["text"] == ai.ANALYSIS_RULES
            assert base64.b64decode(blocks[0]["source"]["data"]) == raw
        else:
            assert body["messages"][0] == {"role": "system", "content": ai.ANALYSIS_RULES}
            assert base64.b64decode(blocks[0]["image_url"]["url"].rsplit(",", 1)[-1]) == raw
        return BytesIO(json.dumps(response).encode("utf-8"))

    monkeypatch.setattr(ai, "build_opener", lambda *_: SimpleNamespace(open=fake_open))
    preview = ai.preview_ecommerce_analysis(settings, raw, [shot], product_name="试用品", transcript=shot.dialogue)
    assert "not-in-preview-secret" not in preview and "Look here." in preview
    [proposed] = ai.draft_ecommerce_shots(settings, raw, [shot], product_name="试用品", transcript=shot.dialogue)
    applied = replace(shot, **proposed)
    assert applied.action == "手抬到胸口" and applied.characters == ("演示人",)
    assert applied.dialogue == shot.dialogue and applied.start_ms == shot.start_ms
    assert applied.end_ms == shot.end_ms and applied.scene_cut and applied.contains_product


def test_vision_output_rejects_extra_source_fields_and_swapped_rows():
    row = fields("01A", dialogue="unapproved")
    with pytest.raises(ValueError, match="字段"):
        ai.parse_ecommerce_analysis(json.dumps({"shots": [row]}), ["01A"])
    with pytest.raises(ValueError, match="编号"):
        ai.parse_ecommerce_analysis(json.dumps({"shots": [fields("01B"), fields("01A")]}), ["01A", "01B"])
    with pytest.raises(ValueError, match="单行"):
        ai.parse_ecommerce_analysis(json.dumps({"shots": [fields("01A", scene="first\nsecond")]}), ["01A"])
    assert ai.parse_ecommerce_analysis('```json\n' + json.dumps({"shots": [fields("01A", contains_product=False)]})
                                      + '\n```', ["01A"])[0]["contains_product"] is False


def test_ecommerce_image_uses_locked_board_layout_and_product_first(monkeypatch):
    preset = IMAGE_PROVIDERS["火山方舟 Seedream"]
    settings = ImageSettings("火山方舟 Seedream", preset.base, preset.model, "not-in-preview-secret")
    reference = sample(kind="JPEG")
    keys = ("01A", "01B", "01C")
    brief = "让人物拿起产品。"
    args = {"product_name": "滴漏壶", "includes_product": True, "panel_ids": keys}
    with pytest.raises(ValueError, match="第一张参考图"):
        ai.preview_ecommerce_image(settings, "board", brief, **args)
    preview = ai.preview_ecommerce_image(settings, "board", brief, references=(reference,), **args)
    assert "9:16" in preview and "2 列 × 2 行" in preview and "not-in-preview-secret" not in preview

    def capture(config, request):
        assert config is settings
        body = json.loads(request.data)
        assert body["size"] == "1440x2560"
        assert "第一张参考图是用户批准的独立产品资产" in body["prompt"]
        locked, data = body["prompt"].split("\n\n用户资料\n")
        assert brief not in locked and json.loads(data)["分镜编号顺序"] == list(keys)
        ref, converted = body["image"].split(",")
        assert ref == "data:image/png;base64" and base64.b64decode(converted).startswith(b"\x89PNG")
        return ai.ImageReply((sample(),))

    monkeypatch.setattr(ai, "submit_image", capture)
    assert ai.submit_ecommerce_image(settings, "board", brief, references=(reference,), **args).results


@pytest.mark.parametrize(("name", "key", "wide", "tall"), [
    ("火山方舟 Seedream", "size", "2560x1440", "1440x2560"),
    ("OpenAI GPT Image", "size", "2048x1152", "1152x2048"),
    ("xAI Grok Imagine", "aspect_ratio", "16:9", "9:16"),
    ("腾讯云混元", "Resolution", "1280:720", "720:1280"),
])
def test_aspect_argument_preserves_existing_wide_default(name, key, wide, tall):
    preset = IMAGE_PROVIDERS[name]
    settings = ImageSettings(name, preset.base, preset.model, "", "")
    default = build_image_request(settings, TEXT, "Draft", preview=True)
    portrait = build_image_request(settings, TEXT, "Draft", preview=True, aspect_ratio="9:16")
    assert json.loads(default.data)[key] == wide
    assert json.loads(portrait.data)[key] == tall
