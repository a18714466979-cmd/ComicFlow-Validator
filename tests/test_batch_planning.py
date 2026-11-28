from copy import deepcopy

import pytest

from src.batch_planning import coverage_issues, materialize_group, plan_episode, regroup, trace_rows
from src.production_export import render_dialogue
from src.production_project import ProductionProject
from src.production_rules import CHINESE, ENGLISH


def make(text, rules=ENGLISH):
    return plan_episode("demo", "EP01", "final.md", text, rules)


def projects(plan):
    return [materialize_group(plan, g["group"]) for g in plan["groups"]]


def test_exact_source_trace_and_stable_ids_across_regroup(tmp_path):
    source = "# Episode 01\r\n\r\nINT. STATION - DAY\r\nShe lifts the lamp.\r\n佐伊： “I see it.”\r\nShe sets it down."
    plan = make(source)
    assert plan == make(source)
    assert len(plan["shots"]) == 3 and plan["assets"] == ["场景：INT. STATION - DAY", "人物：佐伊"]
    ids = [s["id"] for s in plan["shots"]]
    updated = regroup(plan, [[ids[0]], ids[1:]])
    assert len(plan["groups"]) == 1
    ps = projects(updated)
    assert all(p.sources[0].text == source for p in ps)
    for p in ps:
        p.save(tmp_path / (p.group+".cfproject"))
    ps = [ProductionProject.open(tmp_path/(p.group+".cfproject")) for p in ps]
    assert not coverage_issues(updated, ps)
    rows = trace_rows(updated, ps)
    assert len(rows) == 5
    assert rows[0]["shot_id"] == rows[2]["shot_id"]
    assert rows[3]["text"] == "I see it." and rows[3]["group"] == "SB02" and rows[3]["slot"] == 1
    assert all(source[r["start"]:r["end"]] == r["text"] for r in rows)
    assert render_dialogue(ps[1], None)[2] == 3


def test_english_complete_sentence_capacity_accepts_sixty_and_defers_next_turn():
    a = " ".join(["listen"]*55) + "."
    b = " ".join(["now"]*5) + "."
    c = " ".join(["keep"]*15) + "!"
    plan = make(f"莉娜：{a}\n莉娜：{b}\n伊森：{c}")
    assert [g["spoken_count"] for g in plan["groups"]] == [60, 15]
    ps = projects(plan)
    assert ps[0].notes["分组状态"] == "对白容量拆组"
    assert [render_dialogue(p, None)[2] for p in ps] == [60, 15]
    assert ps[-1].lines[0].text == c and not coverage_issues(plan, ps)
    plan = make(f"莉娜：{a}\n伊森：{c}")
    assert [g["spoken_count"] for g in plan["groups"]] == [55, 15]


def test_single_oversize_sentence_is_blocked_without_losing_any_text():
    line = " ".join(["word"]*61)
    plan = make("张： " + line)
    assert plan["issues"] and plan["lines"][0]["text"] == line
    assert coverage_issues(plan, projects(plan))
    with pytest.raises(ValueError):
        regroup(plan, [plan["groups"][0]["shot_ids"]])


def test_chinese_semantic_continuation_is_lossless_across_groups():
    line = "走"*70 + "，" + "停"*36 + "。"
    plan = make("妇人：" + line, CHINESE)
    ps = projects(plan)
    assert len(ps) == 2 and not plan["issues"]
    assert ps[0].lines == ps[1].lines and ps[1].previous_group == "SB01"
    assert [render_dialogue(p, None)[2] for p in ps] == [70, 36]
    assert "".join(s["text"] for s in plan["shots"]) == line
    assert not coverage_issues(plan, ps)
    unsafe = make("来人："+"字"*101, CHINESE)
    assert unsafe["issues"] and len(unsafe["lines"][0]["text"]) == 101


def test_source_documents_notes_scenes_speaker_and_stage_directions():
    en = make("# Episode 01\n---\n## EP001-SC001 内 车站 夜\n来源：本集稿\n梅：Wait here.\n中文译文：等着。")
    assert not en["issues"] and len(en["shots"]) == 1
    assert en["shots"][0]["scene"] == "内 车站 夜"
    assert [r["kind"] for r in trace_rows(en)] == ["heading", "heading", "scene", "heading", "dialogue", "translation"]
    assert trace_rows(en)[-1]["shot_id"] == en["shots"][0]["id"]
    cn = make("\ufeff《试演》第一集\n家中\n柜员无奈：等一下……（被打断）\n转场（茶馆）（雨声先入）\n门卫1：下雨了。", CHINESE)
    assert not cn["issues"] and len(cn["shots"]) == 3
    assert cn["shots"][0]["speaker"] == "柜员" and cn["shots"][0]["text"] == "等一下……"
    assert cn["shots"][-1]["speaker"] == "门卫1" and cn["shots"][-1]["scene"] == "茶馆"
    assert "（被打断）" in trace_rows(cn)[2]["source_line"]


def test_live_coverage_reports_wrong_source_lost_order_and_changed_speaker():
    p = make("甲：First.\n乙：Second.")
    group = projects(p)[0]
    group.shots.reverse()
    assert any("顺序" in msg for msg in coverage_issues(p, [group]))
    group = projects(p)[0]
    group.shots[0].dialogue.clear()
    assert any("发声" in msg for msg in coverage_issues(p, [group]))
    group = projects(p)[0]
    group.sources.clear()
    assert any("批准源稿" in msg for msg in coverage_issues(p, [group]))
    broken = deepcopy(p)
    broken["passages"].pop()
    assert coverage_issues(broken, projects(p))
    with pytest.raises(ValueError, match="覆盖"):
        regroup(p, [[p["shots"][0]["id"], p["shots"][0]["id"]]])


def test_metadata_alone_does_not_create_performed_shots():
    plan = make("# 标题\n场景：大堂\n道具：钥匙")
    assert plan["issues"] and not plan["groups"] and plan["assets"] == ["道具：钥匙"]
    assert all(not r["shot_id"] for r in trace_rows(plan))


def test_editor_cuts_action_at_selected_source_position_and_rebuilds_coverage(tmp_path):
    from src.batch_planning import split_passage
    text = "场景：门厅\n甲推开门。乙听见动静，抬头。\n甲：到了。"
    base = make(text, CHINESE)
    p = base["passages"][1]
    cut = text.index("乙听见")
    plan = split_passage(base, p["id"], [cut])
    group = projects(plan)[0]
    assert not coverage_issues(plan, [group])
    assert group.shots[0].id == projects(base)[0].shots[0].id
    assert [shot.fields["批准父镜ID"] for shot in group.shots[:2]] == [p["id"], p["id"]]
    assert group.shots[0].id != group.shots[1].id
    rows = [r for r in trace_rows(plan) if r["passage_id"] == p["id"]]
    assert [r["text"] for r in rows] == ["甲推开门。", "乙听见动静，抬头。"]
    assert split_passage(plan, p["id"], []) == base
    with pytest.raises(ValueError, match="内部"):
        split_passage(base, p["id"], [p["end"]])
    with pytest.raises(ValueError, match="动作原文"):
        split_passage(base, base["passages"][-1]["id"], [cut])


def test_screenplay_dialogue_lines_and_voice_cues_remain_attached_to_cast():
    plan = make("INT. LAB - NIGHT\nMIRA (V.O.)\n(softly)\nWait until the light turns green.")
    assert not plan["issues"] and len(plan["shots"]) == 1
    shot = projects(plan)[0].shots[0]
    assert plan["lines"][0]["speaker"] == "MIRA" and shot.fields["声源位置"] == "V.O."
    assert [r["kind"] for r in trace_rows(plan)] == ["scene", "speaker", "direction", "dialogue"]
    assert render_dialogue(projects(plan)[0], None)[2] == 6


def test_parenthetical_delivery_and_voice_only_roles_do_not_become_spoken_or_visual_assets():
    plan = make("林OS：（轻声）“Wait.”\n旁白：Night settles.")
    assert [line['text'] for line in plan['lines']] == ["Wait.", "Night settles."]
    assert not plan['assets'] and plan['shots'][0]['cue'] == "OS"
    assert all(plan['source_text'][s['start']:s['end']] == s['text'] for s in plan['shots'])
    assert make("林：We will (beat) talk later.")["issues"]


def test_cannot_cut_a_source_word_in_half():
    from src.batch_planning import split_passage
    plan = make("Mira runs outside.")
    with pytest.raises(ValueError, match="截断单词"):
        split_passage(plan, plan['passages'][0]['id'], [2])
