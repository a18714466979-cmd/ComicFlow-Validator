from dataclasses import replace
import json

import pytest

from src.action_sequence import (
    ActionCard, action_continuity, load_action_cards, plan_action_handoff, rebind_action_cards, save_action_cards,
)
from src.production_project import ProductionProject, Shot


def test_portable_action_json_roundtrip_keeps_order_ids_and_unicode(tmp_path):
    left = ActionCard(title="道具交接", actor="甲", prop="电影木剑", movement="两人交换位置\n留出接镜点")
    right = ActionCard(title="窗边", actor="乙", movement="转身")
    path = tmp_path / "动作.json"
    save_action_cards(path, [right, left])
    assert load_action_cards(path) == [right, left]
    assert "电影木剑" in path.read_text(encoding="utf-8")

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cards"].append(payload["cards"][0])
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="唯一 ID"):
        load_action_cards(path)


def test_adjacent_review_only_flags_explicit_discontinuities():
    left = ActionCard(actor="角色甲", prop="电影木剑", hand_end="右手")
    wrong_hand = ActionCard(actor="角色甲", prop="电影木剑", hand_start="left hand")
    wrong_prop = replace(wrong_hand, prop="折扇", hand_start="right hand")
    assert action_continuity([left, wrong_hand])[0].field == "hand"
    assert action_continuity([left, wrong_prop])[0].field == "prop"
    assert not action_continuity([left, replace(wrong_prop, hand_start="待确认")])
    assert not action_continuity([left, replace(wrong_prop, actor="角色乙")])
    assert not action_continuity([left, replace(wrong_hand, hand_start="right hand")])


def test_action_handoff_preserves_bound_shot_identity_and_appends_only_explicitly():
    project = ProductionProject("试用", "EP01", "SB01")
    source = project.import_source("试用", "R1", "角色甲走到门前。")
    saved = Shot(source=source.id, scene="走廊", plate="旧净板", anchor="批准第1行",
                 dialogue=[("D001", 0, 2)], fields={"景别": "近景", "成片动作": "旧动作"})
    project.shots.append(saved)
    first = ActionCard(title="握杯", actor="角色甲", scene=saved.scene, prop="杯子",
                       movement="把杯子放在窗台", shot_id=saved.id)
    following = ActionCard(title="停步", actor="角色甲", movement="转身停在门内")
    cards = [first, following]
    requested = [following.id, first.id]
    with pytest.raises(ValueError, match="批准剧本"):
        plan_action_handoff(project, cards, requested)
    assert project.shots == [saved]
    shots, linked = plan_action_handoff(project, cards, requested, source_id=source.id, anchor="批准第1行")
    assert [card.id for card in linked] == [card.id for card in cards]
    assert shots[0].id == saved.id and shots[0].plate == saved.plate and shots[0].dialogue == saved.dialogue
    assert shots[0].fields["景别"] == saved.fields["景别"]
    assert "把杯子放在窗台" in shots[0].fields["动作起止"] == shots[0].fields["成片动作"]
    assert linked[1].shot_id == shots[1].id and shots[1].source == source.id and shots[1].anchor == "批准第1行"
    assert project.shots == [saved]
    project.shots = shots
    assert plan_action_handoff(project, linked, requested)[0] == shots


def test_older_sequences_drop_only_unavailable_links_and_reject_wrong_scene_on_adoption():
    project = ProductionProject("试用", "EP01", "SB01")
    target = Shot(scene="走廊")
    project.shots.append(target)
    old = ActionCard(title="开窗", scene="卧室", movement="抬手打开窗", reference="旧参考", shot_id=target.id)
    assert rebind_action_cards([old], project) == [replace(old, reference="")]
    assert rebind_action_cards([old], ProductionProject("其他", "EP01", "SB01")) == [
        replace(old, reference="", shot_id="")]
    with pytest.raises(ValueError, match="地点与目标分镜不同"):
        plan_action_handoff(project, [old], [old.id])
