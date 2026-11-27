import json

import pytest

from src.production_rules import CHINESE, ENGLISH
from src.storyboard_planning_dialog import asset_report, planning_request, save_new_text


def test_script_language_follows_production_rules_and_source_is_preserved():
    source = "张女士：别开门。\n\n门把手转动。"
    en, text = planning_request("script", "集次 1", source, ENGLISH)
    zh, _ = planning_request("script", "集次 1", source, CHINESE)
    assert "英文剧本草稿" in en and "简体中文剧本草稿" in zh
    assert json.loads(text) == {"title": "集次 1", "draft_or_brief": source}
    _, analysis = planning_request("assets", "集次 1", source, CHINESE)
    assert json.loads(analysis)["script_lines"] == {
        "1": "张女士：别开门。",
        "2": "",
        "3": "门把手转动。",
    }


def test_asset_inventory_uses_reviewable_sections_and_citations():
    source = "阿兰出门。\n\n阿兰放下书。"
    inventory = {"characters": [{"name": "阿兰", "source_lines": [3, 1, 3], "notes": "两镜同一身份"}],
                 "locations": [], "props": [{"name": "书", "source_lines": [3], "notes": ""}]}
    raw = json.dumps(inventory, ensure_ascii=False)
    report = asset_report(raw, "SB01 剧本", source, english=True)
    assert "review required" in report
    assert "## Characters" in report and "## Sets" in report and "## Props" in report
    assert "阿兰 · Script lines 1, 3" in report
    assert "书 · Script lines 3" in report
    for invalid in ([2], [4], [True], []):
        inventory["props"][0]["source_lines"] = invalid
        with pytest.raises(ValueError, match="剧本行号"):
            asset_report(json.dumps(inventory), "SB01 剧本", source)


def test_export_does_not_overwrite_a_prior_file(tmp_path):
    target = tmp_path / "稿件.md"
    save_new_text(target, "第一版\n")
    with pytest.raises(FileExistsError):
        save_new_text(target, "第二版")
    assert target.read_bytes() == "第一版\n".encode()
