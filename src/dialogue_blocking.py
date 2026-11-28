"""Offline camera and blocking references for dialogue scenes."""

from dataclasses import dataclass, replace
from pathlib import Path
from unicodedata import normalize

from .production_rules import ENGLISH

DIALOGUE_PREVIEW_DIRECTORY = Path("assets/dialogue_previews")
DIALOGUE_SHOT_FIELDS = ("景别", "机位/角度", "机位空间", "人物站位")


@dataclass(frozen=True)
class DialogueView:
    title: tuple[str, str]
    size: str
    angle: str
    speaker: str
    listeners: tuple[str, ...]
    position: tuple[str, str]
    blocking: tuple[str, str]


@dataclass(frozen=True)
class DialogueCard:
    id: str
    title: tuple[str, str]
    roles: tuple[str, ...]
    summary: tuple[str, str]
    views: tuple[DialogueView, DialogueView]


TWO_SHOT_POSITION = (
    "机位在对话轴同侧，以平视中景同框拍摄 {A} 和 {B}，保留两人间距。",
    "Frame {A} and {B} together in an eye-level medium shot from one side of the dialogue axis, with their spacing visible.",
)
DIALOGUE_CARDS = (
    DialogueCard(
        "dialogue-01", ("双人平视中景同框", "Eye-level medium two-shot"), ("A", "B"),
        ("同一机位的两种表演参考。可以在同一连续镜头里完成问答。",
         "Two performances from one camera position. Both beats may stay in the same continuous shot."),
        (
            DialogueView(("平视双人中景 · A 发问", "Medium two-shot · A speaks"), "中景", "平视", "A", ("B",),
                         TWO_SHOT_POSITION,
                         ("{A} 在画左看向 {B} 并说话，{B} 在画右回看 {A}，闭口听。",
                          "{A} speaks from screen left and looks at {B}. {B} looks back from screen right and listens with lips closed.")),
            DialogueView(("平视双人中景 · B 回答", "Medium two-shot · B replies"), "中景", "平视", "B", ("A",),
                         TWO_SHOT_POSITION,
                         ("{A} 保持画左并闭口听，{B} 留在画右，面向 {A} 回答。",
                          "{A} stays on screen left and listens with lips closed. {B} replies from screen right, looking at {A}.")),
        ),
    ),
    DialogueCard(
        "dialogue-02", ("双人过肩正反打", "Over-the-shoulder shot and reverse"), ("A", "B"),
        ("两个机位在对话轴同一侧。前景是听者的肩，正反打交换拍摄对象。",
         "Place both cameras on one side of the dialogue axis. The foreground shoulder belongs to the listener. The subject reverses between views."),
        (
            DialogueView(("A 肩后看 B · B 说话", "Over A’s shoulder · B speaks"), "中景", "左过肩", "B", ("A",),
                         ("机位在 {A} 肩后，{A} 的肩留在画左前景，对焦画右的 {B}。",
                          "Shoot from behind {A}. Keep their shoulder in the left foreground and {B} in focus on screen right."),
                         ("{A} 留在原位、背向镜头听，{B} 面向 {A} 说话，视线朝画左。",
                          "{A} stays in place and listens with their back toward camera. {B} speaks and looks to screen left toward {A}.")),
            DialogueView(("B 肩后看 A · A 回应", "Over B’s shoulder · A replies"), "中景", "右过肩", "A", ("B",),
                         ("机位在 {B} 肩后，仍在对话轴同侧。{B} 的肩留在画右前景，对焦画左的 {A}。",
                          "Shoot from behind {B} on the same side of the dialogue axis. Keep their shoulder in the right foreground and {A} in focus on screen left."),
                         ("{B} 留在原位、背向镜头听，{A} 面向 {B} 回应，视线朝画右。",
                          "{B} stays in place and listens with their back toward camera. {A} replies and looks to screen right toward {B}.")),
        ),
    ),
    DialogueCard(
        "dialogue-03", ("三人三角站位接话", "Three-person triangle and interjection"), ("A", "B", "C"),
        ("A 在左、B 在右、C 在两人后方。C 接话时，A、B 转移视线，延续原来的三角站位。",
         "A stays on the left, B on the right and C farther back between them. A and B shift their eye lines to C when C joins in."),
        (
            DialogueView(("三人同框 · A 对 B 说话", "Three-shot · A speaks to B"), "中全景", "平视", "A", ("B", "C"),
                         ("从 {A} 与 {B} 的对话轴同侧平视建立三人位置，让后方的 {C} 在两人之间可见。",
                          "Establish the three positions from eye level on one side of the A–B dialogue axis, with {C} visible behind the gap between {A} and {B}."),
                         ("{A} 在画左向 {B} 说话，{B} 在画右闭口看向 {A}，{C} 在两人后方听。",
                          "{A} speaks to {B} from screen left. {B} listens on screen right and looks at {A}. {C} listens farther back.")),
            DialogueView(("三人同框 · C 接话", "Three-shot · C chimes in"), "中景", "平视", "C", ("A", "B"),
                         ("同侧收紧构图。{C} 在中间清楚可见，画左和画右保留 {A}、{B} 的反应。",
                          "Tighten the frame from the same side. Keep {C} visible in the middle, with {A} and {B} reacting on the left and right."),
                         ("{C} 接话，画左的 {A} 和画右的 {B} 闭口转向 {C}，三人延续原位。",
                          "{C} chimes in. {A} on the left and {B} on the right close their mouths and turn to {C} without moving off their marks.")),
        ),
    ),
)
_BY_ID = {card.id: card for card in DIALOGUE_CARDS}
_ANGLES = {"左过肩": "Over-the-shoulder, left foreground", "右过肩": "Over-the-shoulder, right foreground",
           "平视": "Eye level"}
_SIZES = {"中景": "Medium shot", "中全景": "Medium wide shot"}


def dialogue_preview_path(card_id, index):
    if card_id not in _BY_ID or index not in (0, 1, 2):
        raise ValueError("找不到指定的对话站位图。")
    suffix = "map" if index == 0 else str(index)
    return Path(__file__).resolve().parents[1] / DIALOGUE_PREVIEW_DIRECTORY / f"{card_id}-{suffix}.webp"


def action_dialogue_preview(preset_id):
    prefix, _, suffix = preset_id.partition("-")
    if prefix == "dialogueview" and len(suffix) == 2 and suffix.isascii() and suffix.isdecimal() and int(suffix):
        card_number, variant = divmod(int(suffix) - 1, 2)
        card_id = f"dialogue-{card_number + 1:02d}"
        if card_id in _BY_ID:
            return dialogue_preview_path(card_id, variant + 1)
    return None


def dialogue_variant(card_id, index):
    dialogue_view(card_id, index)
    ordinal = 2 * (int(card_id[-2:]) - 1) + index
    return f"dialogueview-{ordinal:02d}"


def dialogue_view(card_id, index):
    if card_id not in _BY_ID or index not in (1, 2):
        raise ValueError("请选择对话卡的第 1 或第 2 个镜头。")
    card = _BY_ID[card_id]
    return card, card.views[index - 1]


def dialogue_roles(card_id, mapping, *, english=False):
    values = {role: " ".join(mapping.get(role, "").split()) for role in _BY_ID[card_id].roles}
    if any(not name or len(name) > 64 or any(c in name for c in "|\0") for name in values.values()):
        raise ValueError("Enter a valid name for each role (up to 64 characters)." if english
                         else "请为每个角色填写有效名称（最多 64 字）。")
    normalized = {normalize("NFKC", name).casefold() for name in values.values()}
    if len(normalized) != len(values) or len("、".join(values.values())) > 180:
        raise ValueError("Assign each role a different name and keep all names within 180 characters in total."
                         if english else "请为每个角色填写不同名称，角色名称合计最多 180 字。")
    return values


def dialogue_fields(card_id, index, mapping, *, english=False):
    _, view = dialogue_view(card_id, index)
    roles = dialogue_roles(card_id, mapping, english=english)
    return _view_fields(view, roles, english)


def _view_fields(view, roles, english):
    return dict(zip(DIALOGUE_SHOT_FIELDS, (
        _SIZES[view.size] if english else view.size,
        _ANGLES[view.angle] if english else view.angle,
        view.position[int(english)].format_map(roles),
        view.blocking[int(english)].format_map(roles),
    )))


def apply_dialogue_view(project, card_id, index, mapping, shot_id):
    """Update one existing shot by stable ID while retaining the approved dialogue and assets."""
    english = project.rules == ENGLISH
    _, view = dialogue_view(card_id, index)
    roles = dialogue_roles(card_id, mapping, english=english)
    target = next((shot for shot in project.shots if shot.id == shot_id), None)
    if target is None:
        raise ValueError("The target shot no longer exists in this group." if english else "当前组已找不到这条分镜。")
    line_ids = {line_id for line_id, *_ in target.dialogue}
    speakers = {normalize("NFKC", line.speaker.strip()).casefold()
                for line in project.lines if line.id in line_ids}
    if speakers and normalize("NFKC", roles[view.speaker]).casefold() not in speakers:
        raise ValueError("Match this view’s speaker to the approved dialogue in the target shot." if english
                         else "请让这个镜头的说话者与目标分镜中的批准对白对应。")
    updated = replace(target, fields={**target.fields, **_view_fields(view, roles, english)})
    return replace(project, shots=[updated if shot.id == shot_id else shot for shot in project.shots])
