"""Read advisory motion cards from local 3D Director Desk project exports.

Format: https://github.com/xiaozangao/3d-director-desk/blob/main/docs/embed-contract.md
Only visible actor and prop paths are used. Recorded points describe the
previs scene and do not assert final motion, prop ownership or shot approval.
"""

import json
from pathlib import Path
from sys import float_info


PROJECT_FORMAT = "3d-director-desk-project"
MAX_PROJECT_BYTES = 32 * 1024**2

# Segment action identifiers defined by the Director Desk character presets.
ACTION_NAMES = {
    "walk-cycle": ("行走", "Walk"),
    "run-cycle": ("跑步", "Run"),
    "crouch-cycle": ("蹲下起立", "Crouch and rise"),
    "side-step-left": ("向左跨步", "Step left"),
    "jump-cycle": ("原地跳跃", "Jump in place"),
    "wave-cycle": ("挥手", "Wave"),
}


def _project(document, localized):
    if isinstance(document, dict) and document.get("format") == PROJECT_FORMAT:
        version = document.get("schemaVersion")
        if type(version) is not int or version not in (0, 1):
            raise ValueError(localized("不支持这个 3D 导演台工程版本。", "Unsupported 3D Director Desk project version."))
        document = document.get("project")

    # The upstream importer also recognizes the legacy bare project shape.
    if (
        not isinstance(document, dict)
        or type(document.get("version")) is not int or document["version"] != 1
        or not isinstance(document.get("scene"), dict) or not isinstance(document["scene"].get("backgroundColor"), str)
        or any(not isinstance(document.get(key), list) for key in ("objects", "assets", "cameras"))
    ):
        raise ValueError(localized("请选择 3D 导演台导出的工程 JSON。", "Select a project JSON exported by 3D Director Desk."))
    return document


def _vector(values):
    if (
        not isinstance(values, list) or len(values) != 3
        or any(type(value) not in (int, float) or not -float_info.max <= value <= float_info.max for value in values)
    ):
        raise ValueError
    return ", ".join(format(value, ".6g") for value in values)


def _point_summary(point, localized):
    position = _vector(point["transform"]["position"])
    rotation = _vector(point["transform"]["rotation"])
    return localized(
        f"路线点 {point['time']:.1%} · 位置 XYZ ({position}) · 记录旋转 ({rotation}) 弧度",
        f"Route point {point['time']:.1%} · Position XYZ ({position}) · Recorded rotation ({rotation}) rad",
    )


def _route_summary(points, character, localized):
    summary = localized(f"{len(points)} 个路线点", f"{len(points)} route points")
    if len(points) > 2:
        via = " → ".join(f"({_vector(point['transform']['position'])})" for point in points[1:-1][:3])
        if len(points) > 5:
            via += localized(f"，另有 {len(points) - 5} 个中间点", f", plus {len(points) - 5} more waypoints")
        summary += localized(f" · 途经 XYZ {via}", f" · Via XYZ {via}")

    if character:
        actions = []
        for point in points[:-1]:
            action_id = point.get("actionPresetId")
            if isinstance(action_id, str) and action_id:
                action = localized(*ACTION_NAMES.get(action_id, ("其他预设动作", "Other preset action")))
                if not actions or action != actions[-1]:
                    actions.append(action)
        if actions:
            sequence = " → ".join(actions[:6])
            if len(actions) > 6:
                sequence += " → …"
            summary += localized(f" · 已记录分段动作 {sequence}", f" · Recorded segment actions {sequence}")
    return summary


def import_director_cards(path: str | Path, *, language: str = "zh") -> list[dict[str, str]]:
    """Return editable local card drafts in project order, one per visible route."""
    def localized(chinese, english):
        return english if language == "en" else chinese

    with Path(path).open("rb") as stream:
        data = stream.read(MAX_PROJECT_BYTES + 1)
    if len(data) > MAX_PROJECT_BYTES:
        raise ValueError(localized("3D 导演台工程超过 32 MiB。", "3D Director Desk project exceeds 32 MiB."))
    try:
        document = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(localized("无法读取 3D 导演台工程 JSON。", "Could not read the 3D Director Desk project JSON.")) from exc

    cards = []
    for index, obj in enumerate(_project(document, localized)["objects"], 1):
        if (
            not isinstance(obj, dict) or obj.get("kind") not in ("character", "prop")
            or obj.get("visible") is not True or obj.get("motionPath") is None
        ):
            continue

        character = obj["kind"] == "character"
        name = obj.get("name")
        if isinstance(name, str):
            name = "".join(char if char.isprintable() else " " for char in name).strip()[:100]
        else:
            name = ""
        if not name:
            name = (localized(f"人物 {index}", f"Character {index}") if character
                    else localized(f"道具 {index}", f"Prop {index}"))
        try:
            points = obj["motionPath"]["keyframes"]
            if not isinstance(points, list):
                raise ValueError
            if len(points) < 2:
                continue
            for point in points:
                time = point["time"]
                if type(time) not in (int, float) or not 0 <= time <= 1:
                    raise ValueError
                _vector(point["transform"]["position"])
                _vector(point["transform"]["rotation"])
            points = sorted(points, key=lambda point: point["time"])
            start = _point_summary(points[0], localized)
            movement = _route_summary(points, character, localized)
            end = _point_summary(points[-1], localized)
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(localized(
                f"3D 导演台对象 {index}（{name}）的路线点格式不正确。",
                f"3D Director Desk object {index} ({name}) has invalid route points.",
            )) from exc

        cards.append({
            "title": localized(f"3D 导演台 · {name}", f"3D Director Desk · {name}"),
            "actor": name if character else "",
            "prop": "" if character else name,
            "start": start,
            "movement": movement,
            "end": end,
        })
    return cards
