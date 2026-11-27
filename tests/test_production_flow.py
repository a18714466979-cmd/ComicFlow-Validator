import pytest

from src.production_flow import asset_shot_context, attach_script, shot_sources
from src.production_project import ProductionProject, Shot
from src.production_rules import CHINESE, ENGLISH


def test_script_handoff_adds_revisions_and_preserves_existing_anchors(tmp_path):
    path = tmp_path / "SB01.cfproject"
    original = "小禾打开灯。\n\n她说：“到了。”\n"
    project, first = attach_script(path, "信号灯", original, CHINESE, existing=False)
    shot = Shot(source=first.id, anchor="剧本第 1–3 行")
    project.shots.append(shot)
    project.save(path)

    updated, second = attach_script(path, "信号灯", "小禾关灯。", ENGLISH, existing=True)
    assert second.version == "R2" and second.id != first.id
    assert updated.rules == CHINESE and updated.shots[0].source == first.id
    before = path.read_bytes()
    reopened, selected = attach_script(path, "信号灯", original, ENGLISH, existing=True)
    assert selected.id == first.id and selected.text == original
    assert reopened.sources[1].id == second.id and path.read_bytes() == before
    with pytest.raises(ValueError, match="已存在"):
        attach_script(path, "信号灯", "被拒绝的稿件。", ENGLISH, existing=False)
    assert path.read_bytes() == before


def test_asset_handoff_uses_selected_version_and_current_shot_numbers():
    project = ProductionProject("样例", "EP01", "SB04")
    first = project.import_source("信号灯", "R1", "小禾开灯。\n\n门开了。")
    later = project.import_source("信号灯", "R2", "灯灭了。")
    first_shot = Shot(source=first.id, anchor="剧本第 1–3 行", scene="监控室", fields={"画面/事件": "捡起钥匙"})
    later_shot = Shot(source=later.id, anchor="试用镜头")
    manual = Shot(source=first.id, anchor="近景补镜")
    invalid = Shot(source=first.id, anchor="剧本第 2–5 行")
    project.shots.extend((first_shot, later_shot, manual, invalid))
    project.pending_shots.append(Shot(source=first.id, anchor="待做镜头"))
    assert shot_sources(project) == (first, later)
    context = asset_shot_context(project, first)
    assert [item["shot_id"] for item in context] == [first_shot.id, manual.id, invalid.id]
    assert context[0] == {"shot_id": first_shot.id, "number": "SB04-01", "description": "剧本第 1–3 行",
                          "scene": "监控室", "fields": {"画面/事件": "捡起钥匙"}, "script_line_span": [1, 3]}
    assert context[1]["number"] == "SB04-03" and "script_line_span" not in context[1]
    assert "script_line_span" not in context[2]
