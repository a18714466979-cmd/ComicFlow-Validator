from dataclasses import replace

import pytest

from src.action_sequence import ActionCard, card_preview_source, plan_action_handoff
from src.dialogue_blocking import apply_dialogue_view, dialogue_fields, dialogue_variant
from src.production_project import ApprovedLine, ProductionProject, Shot
from src.production_rules import CHINESE


def test_dialogue_view_preserves_shot_dialogue_and_other_project_fields():
    shot = Shot(id="one", source="source", anchor="entry",
                fields={"动作起止": "看向门外", "景别": "全景"}, dialogue=[("D1", 0, 7)],
                plate="board", scene="门厅")
    adjacent = Shot(id="two", anchor="reply")
    project = ProductionProject("样例", "EP01", "SB03", shots=[shot, adjacent], rules=CHINESE,
                                lines=[ApprovedLine("D1", "尧", "门还没有关上。", "source")])
    mapped = {"A": "岚", "B": "尧"}
    updated = apply_dialogue_view(project, "dialogue-02", 1, mapped, shot.id)
    changes = dialogue_fields("dialogue-02", 1, mapped)
    assert changes["景别"] == "中景" and changes["机位/角度"] == "左过肩"
    assert changes["机位空间"] == "机位在 岚 肩后，岚 的肩留在画左前景，对焦画右的 尧。"
    assert updated == replace(project, shots=[replace(shot, fields={**shot.fields, **changes}), adjacent])
    assert project.shots[0].fields["景别"] == "全景"


def test_dialogue_view_refuses_wrong_speaker_and_unknown_shot():
    project = ProductionProject("样例", "EP01", "SB03", rules=CHINESE,
                                shots=[Shot(id="one", dialogue=[("D1", 0, 2)])],
                                lines=[ApprovedLine("D1", "岚", "听我说。", "source")])
    roles = {"A": "岚", "B": "尧"}
    with pytest.raises(ValueError, match="批准对白"):
        apply_dialogue_view(project, "dialogue-02", 1, roles, "one")
    with pytest.raises(ValueError, match="找不到"):
        apply_dialogue_view(project, "dialogue-02", 2, roles, "removed")


def test_camera_reference_cannot_use_generic_motion_handoff():
    card = ActionCard(title="过肩机位", movement="从肩后取景", shot_id="one",
                      preset_id=dialogue_variant("dialogue-02", 2))
    assert card_preview_source(card, {}).name == "dialogue-02-2.webp"
    project = ProductionProject("样例", "EP01", "SB03", shots=[Shot(id="one")])
    with pytest.raises(ValueError, match="对话与站位"):
        plan_action_handoff(project, [card], [card.id])
