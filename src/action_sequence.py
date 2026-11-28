"""Local action cards, declared continuity checks, and formal-shot handoff."""

import json
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

from .production_project import Shot, atomic_text, identifier


SEQUENCE_FORMAT = "comicflow-action-sequence"
SEQUENCE_VERSION = 1
MAX_CARDS = 500
MAX_SEQUENCE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class ActionCard:
    id: str = field(default_factory=identifier)
    title: str = ""
    actor: str = ""
    scene: str = ""
    prop: str = ""
    start: str = ""
    movement: str = ""
    end: str = ""
    hand_start: str = ""
    hand_end: str = ""
    reference: str = ""
    shot_id: str = ""
    route_notes: str = ""


@dataclass(frozen=True)
class ContinuityIssue:
    left_id: str
    right_id: str
    field: str
    previous: str
    current: str

    @property
    def message(self) -> str:
        label = {"hand": "持物手", "prop": "同一持物手的道具"}[self.field]
        return f"{label}从「{self.previous}」变成「{self.current}」。请核对中间是否有交接动作。"

    @property
    def english(self) -> str:
        label = {"hand": "The holding hand", "prop": "The prop in the same hand"}[self.field]
        return f"{label} changes from “{self.previous}” to “{self.current}”. Check the transition."


CARD_FIELDS = {entry.name for entry in fields(ActionCard)}
DESCRIPTIVE_FIELDS = {"start", "movement", "end", "route_notes"}
UNKNOWN = {"", "待核对", "待确认", "未知", "unknown", "tbd", "n/a"}
EMPTY_PROP = {"无", "none"}
HANDS = {
    "左": "left", "左手": "left", "left": "left", "left hand": "left",
    "右": "right", "右手": "right", "right": "right", "right hand": "right",
    "双手": "both", "两手": "both", "both": "both", "both hands": "both",
    "无": "none", "none": "none",
}


def cards_from_records(records: list[dict]) -> list[ActionCard]:
    if not isinstance(records, list) or len(records) > MAX_CARDS:
        raise ValueError(f"动作卡需要列表，每份最多 {MAX_CARDS} 张。")
    cards, seen = [], set()
    for number, record in enumerate(records, 1):
        if not isinstance(record, dict) or record.keys() - CARD_FIELDS or "id" not in record:
            raise ValueError(f"第 {number} 张动作卡的字段无效。")
        clean = {}
        for key, value in record.items():
            limit = 1500 if key in DESCRIPTIVE_FIELDS else 180
            if (not isinstance(value, str) or len(value) > limit or "\0" in value
                    or (key not in DESCRIPTIVE_FIELDS and any(mark in value for mark in "\n\r"))):
                raise ValueError(f"第 {number} 张动作卡的 {key} 无效。")
            clean[key] = value.strip()
        if not clean["id"] or clean["id"] in seen:
            raise ValueError(f"第 {number} 张动作卡缺少唯一 ID。")
        seen.add(clean["id"])
        cards.append(ActionCard(**clean))
    return cards


def cards_to_records(cards) -> list[dict]:
    return [asdict(card) for card in cards_from_records([asdict(card) for card in cards])]


def load_action_cards(path: Path) -> list[ActionCard]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_SEQUENCE_BYTES + 1)
    if len(raw) > MAX_SEQUENCE_BYTES:
        raise ValueError("动作卡文件超过 8 MiB。")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("请选择 UTF-8 编码的 ComicFlow 动作卡 JSON。") from error
    if (not isinstance(payload, dict) or payload.keys() != {"format", "version", "cards"}
            or payload["format"] != SEQUENCE_FORMAT
            or type(payload["version"]) is not int or payload["version"] != SEQUENCE_VERSION):
        raise ValueError("动作卡文件的格式或版本不兼容。")
    return cards_from_records(payload["cards"])


def save_action_cards(path: Path, cards) -> None:
    payload = {"format": SEQUENCE_FORMAT, "version": SEQUENCE_VERSION, "cards": cards_to_records(cards)}
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if len(content.encode("utf-8")) > MAX_SEQUENCE_BYTES:
        raise ValueError("动作卡文件超过 8 MiB。")
    atomic_text(path, content)


def rebind_action_cards(cards, project) -> list[ActionCard]:
    """Keep project-local links only when their targets exist in this project."""
    images = {image.id for image in project.images}
    shots = {shot.id for shot in project.shots}
    return [replace(card, reference=card.reference if card.reference in images else "",
                    shot_id=card.shot_id if card.shot_id in shots else "") for card in cards]


def comparable(text: str) -> str:
    return " ".join(text.casefold().split())


def action_continuity(cards) -> tuple[ContinuityIssue, ...]:
    """Flag explicit adjacent declarations for the same actor and known props."""
    findings = []
    for left, right in zip(cards, cards[1:]):
        actor = comparable(left.actor)
        if actor in UNKNOWN or actor != comparable(right.actor):
            continue
        previous_prop, current_prop = comparable(left.prop), comparable(right.prop)
        if previous_prop in UNKNOWN | EMPTY_PROP or current_prop in UNKNOWN | EMPTY_PROP:
            continue
        previous_hand, current_hand = HANDS.get(comparable(left.hand_end)), HANDS.get(comparable(right.hand_start))
        if not previous_hand or not current_hand:
            continue
        if previous_prop == current_prop and previous_hand != current_hand:
            findings.append(ContinuityIssue(left.id, right.id, "hand", left.hand_end, right.hand_start))
        elif previous_hand == current_hand != "none" and previous_prop != current_prop:
            findings.append(ContinuityIssue(left.id, right.id, "prop", left.prop, right.prop))
    return tuple(findings)


def motion_summary(card: ActionCard) -> str:
    parts = (
        ("人物", card.actor), ("道具", card.prop), ("起点", card.start), ("动作与反应", card.movement),
        ("结束状态", card.end), ("起始持物手", card.hand_start), ("结束持物手", card.hand_end),
    )
    return "；".join(f"{label}为{' '.join(value.split())}" for label, value in parts if value.strip())


def plan_action_handoff(project, cards, selected_ids, *, source_id="", anchor="") -> tuple[list[Shot], list[ActionCard]]:
    """Plan explicit shot changes without touching the project or its saved file."""
    cards = cards_from_records([asdict(card) for card in cards])
    picks = set(selected_ids)
    if not picks or not picks <= {card.id for card in cards}:
        raise ValueError("请选择要带入分镜的有效动作卡。")
    selected = [card for card in cards if card.id in picks]
    formal = {shot.id: shot for shot in project.shots}
    sources = {source.id for source in project.sources}
    anchor = anchor.strip()
    if any(not card.shot_id for card in selected):
        if source_id not in sources or not anchor or any(mark in anchor for mark in "|\n\r"):
            raise ValueError("新增分镜需要选择批准剧本并填写实际源段位置。")
    planned, additions, updated, summaries = {}, [], {}, {}
    for card in selected:
        if not card.movement.strip():
            if card.route_notes:
                raise ValueError(f"请先把「{card.title}」的导演台轨迹写成分镜动作，再带入镜头。")
            raise ValueError(f"「{card.title or card.id}」缺少可带入分镜的动作内容。")
        if card.shot_id:
            shot = formal.get(card.shot_id)
            if shot is None:
                raise ValueError(f"「{card.title or card.id}」绑定的分镜已移除，请重新选择。")
            if card.scene and shot.scene and comparable(card.scene) != comparable(shot.scene):
                raise ValueError(f"「{card.title or card.id}」的地点与目标分镜不同，请先核对场景。")
        else:
            shot = Shot(source=source_id, anchor=anchor, scene=card.scene)
            additions.append(shot.id)
            updated[card.id] = replace(card, shot_id=shot.id)
        summaries.setdefault(shot.id, []).append(motion_summary(card))
        planned[shot.id] = shot
    for identity, shot in planned.items():
        action = "。接续动作：".join(summaries[identity])
        planned[identity] = replace(shot, fields={**shot.fields, "动作起止": action, "成片动作": action})
    return ([planned.get(shot.id, shot) for shot in project.shots] + [planned[identity] for identity in additions],
            [updated.get(card.id, card) for card in cards])
