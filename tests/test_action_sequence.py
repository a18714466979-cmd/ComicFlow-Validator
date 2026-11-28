from dataclasses import replace
import json

from PIL import Image
import pytest

from src.action_card_catalog import ACTION_PRESETS, PRESETS, action_preview_path, get_preset
from src.action_sequence import (
    ActionCard, action_continuity, card_preview_source, cards_from_records, cards_to_records, load_action_cards,
    plan_action_handoff, preset_for_card, rebind_action_cards, save_action_cards,
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


def test_preset_ids_bind_both_languages_without_remapping_old_record_order():
    assert len(set(preset.id for preset in ACTION_PRESETS)) == len(ACTION_PRESETS) == 53
    assert len({preset.category for preset in ACTION_PRESETS}) == len(PRESETS) == 9
    records = [(category, title, movement, prop) for category, items in PRESETS.items()
               for title, movement, prop in items]
    for preset, (category, title, movement, prop) in zip(ACTION_PRESETS, records):
        assert (preset.category, preset.title, preset.movement, preset.prop) == (category, title, movement, prop)
        assert get_preset(preset.id) is preset
        assert action_preview_path(preset.id).name == f"{preset.id}.webp"
        for language in range(2):
            old = ActionCard(title=title[language], movement=movement[language], prop=prop[language])
            assert preset_for_card(old) is preset
            assert "preset_id" not in cards_to_records([old])[0]
            assert preset_for_card(replace(old, movement=old.movement + " copied annotation")) is None
    assert action_preview_path("../outside") is None


def test_preset_preview_never_overrides_project_reference_or_leaks_to_handoff(tmp_path):
    preset = get_preset("performance-03")
    card = ActionCard(title=preset.title[0], movement=preset.movement[0], prop=preset.prop[0], preset_id=preset.id)
    legacy_record = {"id": "old", "title": card.title, "movement": card.movement, "prop": card.prop}
    project = ProductionProject("动作示意", "EP01", "SB01", action_cards=[legacy_record])
    project_path = tmp_path / "scene.cfproject"
    project.save(project_path)
    original = project_path.read_bytes()
    older_card, = cards_from_records(ProductionProject.open(project_path).action_cards)
    assert card_preview_source(older_card, {}) == action_preview_path(preset.id)
    assert project_path.read_bytes() == original

    portrait = tmp_path / "local.png"
    Image.new("RGB", (64, 36), "teal").save(portrait)
    image = project.import_image(project_path, portrait, "local.png", action="直接复用",
                                 reason="现有画面", inspection="核对原图", reference_only=True)
    attached = replace(card, reference=image.id)
    assert card_preview_source(attached, {image.id: image}) is image
    rebound, = rebind_action_cards([attached], ProductionProject("其他项目", "EP02", "SB01"))
    assert rebound == card and card_preview_source(rebound, {}) == action_preview_path(preset.id)
    output = tmp_path / "cards.json"
    save_action_cards(output, [attached])
    assert load_action_cards(output) == [attached]
    assert ".webp" not in output.read_text(encoding="utf-8")

    shot = Shot()
    project.shots.append(shot)
    updated = replace(attached, shot_id=shot.id)
    shots, _ = plan_action_handoff(project, [updated], [updated.id])
    assert shots[0].fields["成片动作"].endswith(card.movement)
    assert preset.id not in shots[0].fields["成片动作"]


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


def test_director_route_is_retained_for_previs_without_leaking_into_formal_actions():
    project = ProductionProject("试用", "EP01", "SB01")
    target = Shot()
    project.shots.append(target)
    route = ActionCard(title="导演台场景", shot_id=target.id, route_notes="XYZ (0, 1, 2)")
    with pytest.raises(ValueError, match="导演台轨迹写成分镜动作"):
        plan_action_handoff(project, [route], [route.id])
    ready = replace(route, movement="从门口走到桌边")
    shots, cards = plan_action_handoff(project, [ready], [ready.id])
    assert cards[0].route_notes == route.route_notes
    assert shots[0].fields["成片动作"] == "动作与反应为从门口走到桌边"
