"""Chinese capacity, source continuity, and production TXT regression tests."""

import json
import re

import pytest

from src.production_dialogue import plan_project_dialogue, save_scope, scope_from_shots, select_scope
from src.production_export import chinese_text_records, write_chinese_texts
from src.production_handoff import boundary_report
from src.production_project import SHOT_FIELDS, ProductionProject, Shot
from src.production_rules import CHINESE
from src.storyboard_preflight import chinese_speech_length, plan_dialogue


def approved(text, **extra):
    return {"id": "D001", "speaker": "门外的值班员", "text": text, **extra}


def plan(*rows):
    return plan_dialogue(json.dumps(rows, ensure_ascii=False), rules=CHINESE)


def project_with_shots(group, spec, count, rows):
    project = ProductionProject("信号站", "EP01", group, rules=CHINESE)
    source = project.import_source("合成批准剧本.md", "R1", "\n".join(item["text"] for item in rows) or "门灯熄灭。")
    project.import_dialogue(source, json.dumps(rows, ensure_ascii=False))
    project.notes = {"分组状态": "常规", "对白规格": spec, "覆盖段落": "信号站交接",
                     "本组进入状态": "门灯熄灭", "本组退出状态": "门灯熄灭", "连续性锁定": "门关闭，灯灭"}
    project.prompt = {"场景/总体状态": "夜间信号站，门关闭", "公共限制": "保持门和开关的空间关系"}
    fields = dict.fromkeys(SHOT_FIELDS, "室内信号站")
    fields.update({"唯一角色数量锁定": "无", "动作起止": "观察门灯状态", "成片动作": "", "成片声音": "",
                   "声源位置": "画外同期", "场景/环境": "桌上批准标牌写着「检修中」"})
    for index in range(count):
        project.shots.append(Shot(source=source.id, anchor=f"环境观察 {index + 1}", fields=fields.copy()))
    return project


def spoken(text):
    return re.findall(r"^对白：门外的值班员：[“「](.*)[”」]$", text, flags=re.MULTILINE)


def test_100_stays_and_101_rolls_over_at_natural_boundary():
    first = "等" * 98 + " A2。  "
    groups = plan(approved(first.strip()))
    assert [group["characters"] for group in groups] == [100]
    longer = first + "走！"
    groups = plan(approved(longer))
    parts = [group["fragments"][0] for group in groups]
    assert [group["characters"] for group in groups] == [100, 1]
    assert [part["cue"] for part in parts] == ["首说", "续说"]
    assert (parts[0]["end"], parts[1]["start"]) == (len(first), len(first))
    assert "".join(part["text"] for part in parts) == longer


def test_unmarked_long_line_reports_the_location_and_respects_a_marked_pause():
    first, rest = "听" * 85 + "，", "走" * 16 + "。"
    with pytest.raises(ValueError, match=r"D001 \[0:103\] 有 101 字"):
        plan(approved(first + rest))
    groups = plan(approved(first + rest, sentence_ends=[len(first), len(first + rest)]))
    assert [group["characters"] for group in groups] == [85, 16]
    assert [group["fragments"][0]["text"] for group in groups] == [first, rest]


def test_long_line_stitches_across_saved_groups_and_both_text_files(tmp_path):
    first = ("这盏灯本来连着北门的开关，现在灯灭了，门却没有动。"
             "我刚在门外听见有人停下脚步，还以为是换班的人回来了。"
             "我得先确认声音从哪边来；你守着这里，别去碰那只开关。  ")
    second = ("如果听见敲门，先问是谁。隔着门听不清，就等我回来。"
              "那张写着检修中的纸还放在桌上，把它压在杯子下面，免得开窗时吹走。")
    rows = [approved(first + second, sentence_ends=[len(first), len(first + second)])]
    left, right = [project_with_shots(group, "三句以上或长对白", 6, rows) for group in ("SB01", "SB02")]
    plans = plan_project_dialogue(left)
    assert [group["characters"] for group in plans] == [chinese_speech_length(first), chinese_speech_length(second)]
    select_scope(left, plans[0], "")
    select_scope(right, plans[1], "SB01")
    left.shots[0].dialogue = [("D001", 0, len(first))]
    cut = len(first) + second.index("。") + 1
    right.shots[0].dialogue = [("D001", len(first), cut)]
    right.shots[1].dialogue = [("D001", cut, len(first + second))]
    reopened = []
    actual = []
    for project, audible in ((left, first), (right, second)):
        path = tmp_path / f"{project.group}.cfproject"
        project.save(path)
        project = ProductionProject.open(path)
        reopened.append(project)
        exported = write_chinese_texts(project, tmp_path)
        record = (exported / f"{project.group}_shot_details.txt").read_text(encoding="utf-8-sig")
        sd2 = (exported / "SD2_prompt.txt").read_text(encoding="utf-8-sig")
        assert all(file.read_bytes().startswith(b"\xef\xbb\xbf") for file in exported.iterdir())
        assert re.findall(r"^分镜 (SB\d+-\d+)", record, re.M) == re.findall(r"^分镜编号：(SB\d+-\d+)", sd2, re.M)
        assert spoken(record) == spoken(sd2)
        assert "".join(spoken(sd2)) == audible
        assert f"总发声字数：{chinese_speech_length(audible)}" in record
        assert "成片字幕、标牌、UI/HUD、系统提示和拟声字允许中文" in sd2
        assert "「检修中」" in sd2
        assert not any(name in sd2 for name in ("总发声字数", "对白编号", "跨组对白原文", "对白保全核对"))
        actual.extend(spoken(sd2))
        if project.group == "SB01":
            assert second in (exported / "待制作分镜.txt").read_text(encoding="utf-8-sig")
        else:
            assert "D001=续说" in record and "上一组 SB01" in record
            assert not (exported / "待制作分镜.txt").exists()
    assert "".join(actual) == first + second
    _, issues = boundary_report(*reopened, None)
    assert not issues


def test_chinese_scope_can_stop_early_at_an_approved_semantic_cut():
    first, second = "先听里面的动静，", "确认没有回应再按门铃。"
    project = project_with_shots("SB01", "1-2句短对白", 8,
                                 [approved(first + second, sentence_ends=[len(first), len(first + second)])])
    assert len(plan_project_dialogue(project)) == 1
    project.shots[0].dialogue = [("D001", 0, len(first))]
    save_scope(project, scope_from_shots(project), "")
    records = chinese_text_records(project)
    assert spoken(records["SD2_prompt.txt"]) == [first]
    assert second in records["待制作分镜.txt"]
    project.shots[0].dialogue = [("D001", 0, len(first) - 2)]
    with pytest.raises(ValueError, match="自然切点"):
        save_scope(project, scope_from_shots(project), "")


def test_cross_group_report_detects_a_skipped_approved_line():
    rows = [approved(text) | {"id": f"D{index:03}"}
            for index, text in enumerate(("先关灯。", "再听门外。", "最后开门。"), 1)]
    left, right = [project_with_shots(group, "1-2句短对白", 8, rows) for group in ("SB01", "SB02")]
    left.shots[0].dialogue = [("D001", 0, len(rows[0]["text"]))]
    right.shots[0].dialogue = [("D003", 0, len(rows[2]["text"]))]
    for project in (left, right):
        save_scope(project, scope_from_shots(project), "")
    assert "D002" in chinese_text_records(left)["待制作分镜.txt"]
    _, issues = boundary_report(left, right, None)
    assert any("D002" in issue for issue in issues)


@pytest.mark.parametrize(("spec", "count", "repeat", "accepted"), [
    ("无对白", 9, 0, True), ("无对白", 10, 0, True), ("无对白", 11, 0, False),
    ("1-2句短对白", 8, 2, True), ("1-2句短对白", 6, 2, False), ("1-2句短对白", 8, 3, False),
    ("三句以上或长对白", 6, 1, True), ("三句以上或长对白", 6, 3, True),
])
def test_chinese_panel_requirements_use_actual_unique_spoken_lines(spec, count, repeat, accepted):
    rows = [approved("灯灭了。") | {"id": f"D{i:03}"} for i in range(1, repeat + 1)]
    project = project_with_shots("SB01", spec, count, rows)
    for shot, row in zip(project.shots, rows):
        shot.dialogue = [(row["id"], 0, len(row["text"]))]
    if accepted:
        assert f"格数：{count}" in chinese_text_records(project)["SB01_shot_details.txt"]
    else:
        with pytest.raises(ValueError, match="对白规格|需要"):
            chinese_text_records(project)
