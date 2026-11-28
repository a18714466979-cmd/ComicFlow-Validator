import json
from unittest.mock import Mock

import pytest

from src.production_rules import CHINESE, ENGLISH
from src.storyboard_planning_dialog import PlanningDialog, asset_report, planning_request, save_new_text


def test_script_language_follows_production_rules_and_source_is_preserved():
    source = "张女士：别开门。\n\n门把手转动。"
    en, text = planning_request("script", "集次 1", source, ENGLISH)
    zh, _ = planning_request("script", "集次 1", source, CHINESE)
    assert "英文剧本草稿" in en and "简体中文剧本草稿" in zh
    assert "英文影片制作 v14.10.4" in en and "中文影片制作 v14.8.8" in zh
    assert source not in en and source not in zh
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


def test_linked_asset_analysis_preserves_script_lines_and_cites_confirmed_shots():
    source = "门开了。\n\n安娜跑出去。"
    context = ({"shot_id": "id-123", "number": "SB01-03", "source_lines": [3],
                "description": "安娜提着公文包跑出去。"},)
    instructions, payload = planning_request("assets", "撤离", source, CHINESE, shot_context=context)
    assert "仅整理当前组" in instructions
    assert json.loads(payload) == {"title": "撤离", "script_lines": {"1": "门开了。", "2": "", "3": "安娜跑出去。"},
                                   "current_shots": list(context)}
    inventory = {"characters": [], "locations": [], "props": [
        {"name": "公文包", "notes": "安娜持有", "source_lines": [], "shot_ids": ["id-123"]},
    ]}
    assert "公文包 · 镜头 SB01-03" in asset_report(json.dumps(inventory), "撤离", source, shot_context=context)
    inventory["props"][0]["shot_ids"] = ["SB02-03"]
    with pytest.raises(ValueError, match="镜头编号"):
        asset_report(json.dumps(inventory), "撤离", source, shot_context=context)


@pytest.mark.parametrize(("pane", "caption"), (("source", "左侧稿件"), ("output", "右侧候选")))
def test_script_handoff_uses_selected_pane_after_explicit_confirmation(monkeypatch, pane, caption):
    dialog = PlanningDialog.__new__(PlanningDialog)
    dialog.english = False
    dialog.busy = False
    dialog.window = Mock()
    dialog.title = Mock()
    dialog.title.get.return_value = "  撤离  "
    dialog.status = Mock()
    dialog.source, dialog.output = Mock(), Mock()
    dialog.source.get.return_value = "左稿\n\n保留换行\n"
    dialog.output.get.return_value = "候选稿\n\n保留换行\n"
    dialog.on_use_script = Mock(return_value=True)
    confirm = Mock(side_effect=[False, True])
    monkeypatch.setattr("src.storyboard_planning_dialog.messagebox.askyesno", confirm)
    editor = getattr(dialog, pane)

    dialog.use_script(editor)
    dialog.on_use_script.assert_not_called()
    assert caption in confirm.call_args.args[1]

    dialog.use_script(editor)
    dialog.on_use_script.assert_called_once_with("撤离", editor.get.return_value)
    dialog.window.destroy.assert_not_called()

    editor.get.return_value = " \n  "
    dialog.use_script(editor)
    assert dialog.on_use_script.call_count == 1 and confirm.call_count == 2
