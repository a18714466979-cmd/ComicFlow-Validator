"""Local and mocked API regressions for the SD2 text milestone."""

import json
import os
from io import BytesIO
from pathlib import Path

import pytest

from src.production_dialogue import handoff_rows, plan_project_dialogue, select_scope, validated_scope
from src.production_drafting import (
    HANDOFF_TASK, SD2_TASK, SHOT_TASK, apply_candidate, build_context, record_candidate, revise_candidate,
)
from src.production_export import render_dialogue
from src.production_project import ProductionProject, Shot
from src.text_api import TextReply, locked_text_instructions, request_text
from src.vision import PROVIDERS, VisionSettings


@pytest.mark.parametrize("provider,endpoint", [("OpenAI", "/chat/completions"), ("Claude（Anthropic）", "/messages"),
                                             ("豆包（火山方舟）", "/chat/completions")])
def test_text_api_wire_contract(monkeypatch, provider, endpoint):
    native = provider.startswith("Claude")
    raw = {"content": [{"type": "text", "text": '{"shots": []}'}]} if native else {
        "choices": [{"message": {"content": '{"shots": []}'}, "finish_reason": "stop"}],
    }
    raw["model"] = "returned-model"

    class MockResponse(BytesIO):
        headers = {"x-request-id": "request-synthetic"}

    class MockOpener:
        def open(self, request, timeout):
            assert request.full_url.endswith(endpoint) and timeout == 90
            payload = json.loads(request.data)
            assert payload["model"] == "selected-model"
            assert payload[PROVIDERS[provider].token_limit_field] == 8192
            assert request.get_header("Authorization") == "Bearer test-key"
            locked = locked_text_instructions("rules")
            assert locked.endswith("\n\nrules") and "不能替换软件要求" in locked
            assert "selected excerpt" not in locked
            if native:
                assert request.get_header("Anthropic-version") == "2026-10-21"
                assert payload["system"] == [{"type": "text", "text": locked}]
                assert len(payload["messages"]) == 1
            else:
                assert payload["messages"][0] == {"role": "system", "content": locked}
                assert len(payload["messages"]) == 2
            assert payload["messages"][-1] == {"role": "user", "content": "selected excerpt"}
            return MockResponse(json.dumps(raw).encode())

    monkeypatch.setattr("src.text_api.build_opener", lambda _: MockOpener())
    result = request_text(VisionSettings(provider, PROVIDERS[provider].base_url, "selected-model", "test-key"),
                          "rules", "selected excerpt")
    assert result == TextReply('{"shots": []}', "request-synthetic", "returned-model")


def test_preview_edit_versions_and_apply_with_approved_fields_locked(tmp_path):
    project = ProductionProject("草稿测试", "EP01", "SB02", notes={
        "本组进入状态": "门闩关闭，电芯黄色，伤势左侧", "本组退出状态": "门闩关闭。",
    })
    source = project.import_source("样例.md", "R5", "私下备注，选段外。\n批准场景：电芯黄色。\n值班员：Hold here.")
    project.import_dialogue(source, '[{"id":"D001","speaker":"值班员","text":"Hold here."}]')
    shot = Shot(source=source.id, anchor="批准第3行", fields={
        "唯一角色数量锁定": "值班员×1", "连续性": "门闩关闭，左手持电芯", "成片动作": "停在原位",
    }, dialogue=[("D001", 0, 10)])
    project.shots.append(shot)
    project.structure_review = project.fingerprint()
    context, payload = build_context(project, source, SD2_TASK, 2, 2, shot.id)
    assert "私下备注" not in payload and "批准场景" in payload
    assert "Hold here." in payload and "电芯黄色" in payload
    with pytest.raises(ValueError, match="受保护"):
        record_candidate(project, SD2_TASK, context, "OpenAI", "demo", TextReply(
            '{"prompt":{"唯一角色数量锁定":"值班员×3","成片动作":"举目"}}'))
    assert not project.text_drafts
    draft = record_candidate(project, SD2_TASK, context, "OpenAI", "demo",
                             TextReply('{"prompt":{"成片动作":"值班员握紧手中电芯"}}', "request-test"))
    assert project.shots[0].fields["成片动作"] == "停在原位" and not project.impacts()
    edit = revise_candidate(project, draft, {"prompt": {"成片动作": "值班员左手握紧黄色电芯"}})
    path = tmp_path / "草稿项目.cfproject"
    project.save(path)
    project = ProductionProject.open(path)
    assert len(project.text_drafts) == 2 and edit["revision_of"] == draft["id"]
    apply_candidate(project, project.text_drafts[-1])
    assert project.shots[0].fields == {
        "唯一角色数量锁定": "值班员×1", "连续性": "门闩关闭，左手持电芯", "成片动作": "值班员左手握紧黄色电芯",
    }
    assert project.shots[0].dialogue == [["D001", 0, 10]] and project.lines[0].text == "Hold here."
    assert project.notes["本组进入状态"] == "门闩关闭，电芯黄色，伤势左侧" and project.impacts()
    with pytest.raises(ValueError, match="已变化"):
        apply_candidate(project, draft)
    handoff_context, _ = build_context(project, source, HANDOFF_TASK, 2, 3, previous={"退出状态": "门闩关闭"})
    handoff = record_candidate(project, HANDOFF_TASK, handoff_context, "OpenAI", "demo",
                               TextReply('{"handoff":{"进入建议":"建议沿用关闭门闩"}}'))
    with pytest.raises(ValueError, match="录入批准"):
        apply_candidate(project, handoff)


def test_breakdown_drafts_use_source_lines_and_create_pending_shots():
    project = ProductionProject("草稿测试", "EP01", "SB01")
    source = project.import_source("剧本.md", "R1", "前文\n门闩卡住。\n信号灯亮。")
    context, _ = build_context(project, source, SHOT_TASK, 2, 3)
    rows = [{"line_start": 2, "line_end": 2, "fields": {"动作起止": "门闩从转动到卡住"}},
            {"line_start": 3, "line_end": 3, "fields": {"画面/事件": "信号灯亮起"}}]
    with pytest.raises(ValueError, match="越界"):
        record_candidate(project, SHOT_TASK, context, "mock", "demo",
                         TextReply(json.dumps({"shots": [{**rows[0], "line_start": 1}]})))
    candidate = record_candidate(project, SHOT_TASK, context, "mock", "demo", TextReply(json.dumps({"shots": rows})))
    apply_candidate(project, candidate, (1, 0))
    assert [shot.anchor for shot in project.shots] == ["剧本第 2–2 行", "剧本第 3–3 行"]
    assert len({shot.id for shot in project.shots}) == 2
    assert all(shot.source == source.id and not shot.plate and not shot.dialogue
               and "唯一角色数量锁定" not in shot.fields and "连续性" not in shot.fields for shot in project.shots)


def test_scope_disallows_replacing_assigned_approved_dialogue():
    project = ProductionProject("草稿测试", "EP01", "SB02")
    source = project.import_source("剧本.md", "R1", "Hold here. Stay clear.")
    boundary = 11
    project.import_dialogue(source, json.dumps([{
        "id": "D001", "speaker": "值班员", "text": source.text, "sentence_ends": [boundary, len(source.text)],
    }]))
    group = {"fragments": [{"id": "D001", "start": boundary, "end": len(source.text)}]}
    with pytest.raises(ValueError, match="实际上一组"):
        select_scope(project, group, "")
    project.shots.append(Shot(source=source.id, dialogue=[("D001", 0, boundary)]))
    with pytest.raises(ValueError, match="调整"):
        select_scope(project, group, "SB01")
    project.shots[0].dialogue = [("D001", boundary, len(source.text))]
    select_scope(project, group, "SB01")
    assert project.dialogue_scope == {"D001": [boundary, len(source.text)]}
    assert handoff_rows(project, project.dialogue_scope) == (
        [f"- D001 | 值班员 | {boundary}:{len(source.text)} | {source.text}"], [],
    )


def test_real_workflow_capacity_and_continuations():
    configured = os.environ.get("COMICFLOW_M1_TEST_VALIDATOR")
    if not configured:
        pytest.skip("The installed storyboard workflow is used for this planner integration test.")
    planner = Path(configured).with_name("plan_english_dialogue.py")
    first = " ".join(["Wait"] * 54 + ["here."])
    second = " ".join(["Keep"] * 14 + ["moving."])
    original = first + " " + second
    cut = len(first) + 1
    project = ProductionProject("容量测试", "EP01", "SB01")
    source = project.import_source("剧本.md", "R1", original)
    project.import_dialogue(source, json.dumps([{
        "id": "D001", "speaker": "值班员", "text": original, "sentence_ends": [cut, len(original)],
    }]))
    groups = plan_project_dialogue(project, planner)
    assert [group["words"] for group in groups] == [55, 15]
    with pytest.raises(ValueError, match="按整句分组"):
        render_dialogue(project, planner)
    select_scope(project, groups[0], "")
    cross_cut = first.index(" ", 50) + 1
    project.shots = [Shot(source=source.id, dialogue=[("D001", 0, cross_cut)]),
                     Shot(source=source.id, dialogue=[("D001", cross_cut, cut)])]
    records, _, count = render_dialogue(project, planner)
    assert count == 55 and [item[1] for item in records] == ["D001=首说", "D001=续说"]
    assert handoff_rows(project, validated_scope(project, planner))[1] == [f"- D001 | 值班员 | {second}"]
    project.group = "SB02"
    project.shots = [Shot(source=source.id, dialogue=[("D001", cut, len(original))])]
    select_scope(project, groups[1], "SB01")
    records, ledger, count = render_dialogue(project, planner)
    assert count == 15 and records == [("D001", "D001=续说", f"值班员：“{second}”")]
    assert "上一组 SB01" in ledger

    sixty = " ".join(["Wait"] * 59 + ["here."])
    for identity, text in (("D060", sixty), ("D061", "Please " + sixty)):
        single = ProductionProject("容量测试", "EP01", "SB01")
        source = single.import_source("剧本.md", "R1", text)
        single.import_dialogue(source, json.dumps([{"id": identity, "speaker": "值班员", "text": text}]))
        if identity == "D060":
            assert plan_project_dialogue(single, planner)[0]["words"] == 60
        else:
            with pytest.raises(ValueError, match="one sentence unit has 61 words"):
                plan_project_dialogue(single, planner)
