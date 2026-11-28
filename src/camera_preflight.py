"""Check recorded framing across independent shots in playback order."""

from dataclasses import dataclass, replace
import re
from unicodedata import normalize

from .production_rules import CHINESE, ENGLISH


SIZE_ALIASES = {
    "大全景": ("大远景", "大遠景", "extreme wide", "extreme long", "extreme wide shot", "extreme long shot", "ews", "els"),
    "远景": ("遠景", "long shot", "ls"),
    "全景": ("wide", "wide shot", "full shot", "ws", "fs"),
    "中全景": ("medium wide", "medium long", "medium wide shot", "medium long shot", "mws", "mls"),
    "中景": ("medium", "medium shot", "ms"),
    "中近景": ("近中景", "medium close up", "medium close up shot", "mcu"),
    "近景": ("close shot",),
    "特写": ("特寫", "close up", "close up shot", "cu"),
    "大特写": ("大特寫", "extreme close up", "extreme close up shot", "ecu"),
}
ANGLE_ALIASES = {
    "平视": ("平視", "平视镜头", "eye level", "eye level shot"),
    "俯拍": ("俯视", "俯視", "高角度", "high angle", "high angle shot"),
    "仰拍": ("仰视", "仰視", "低角度", "low angle", "low angle shot"),
    "正面": ("正面机位", "frontal", "front view", "front angle"),
    "侧面": ("側面", "侧面机位", "profile", "side view", "side angle"),
    "顶拍": ("頂拍", "overhead", "top down"),
    "左过肩": ("左過肩", "Over-the-shoulder, left foreground"),
    "右过肩": ("右過肩", "Over-the-shoulder, right foreground"),
}
MISSING_ANGLES = {
    "?", "无", "無", "未知", "未填", "未填写", "未提供", "未记录", "未定", "待定", "待确认", "待核对",
    "不适用", "不明确", "同上", "同前", "unknown", "unspecified", "not recorded", "not applicable",
    "n/a", "na", "none", "tbd", "其他", "待补", "待补充", "待核实", "待填写", "other", "unconfirmed",
}


@dataclass(frozen=True)
class CameraCut:
    kind: str
    shots: tuple[str, ...]
    size: str
    angle: str = ""
    source_ids: tuple[str, ...] = ()


def normalized_text(value):
    if not isinstance(value, str):
        return ""
    value = normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[-‐‑‒–—−_]+", " ", value).strip(" .。").split())


def alias_table(groups):
    return {normalized_text(term): canonical for canonical, terms in groups.items() for term in (canonical, *terms)}


SIZES = alias_table(SIZE_ALIASES)
ANGLES = alias_table(ANGLE_ALIASES)


def declared_framing(fields):
    size = SIZES.get(normalized_text(fields.get("景别")), "")
    angle_text = normalized_text(fields.get("机位/角度"))
    angle = "" if angle_text in MISSING_ANGLES else ANGLES.get(angle_text, angle_text)
    return size, angle


def camera_cuts(shots, rules, *, fight=False) -> tuple[CameraCut, ...]:
    """Compare shot declarations in the supplied playback order.

    Keep unknown sizes and missing angles out of comparisons. These findings
    describe the recorded scale and angle, so users still inspect the actual
    camera position, composition, and continuity in the panels.
    """
    if rules not in {CHINESE, ENGLISH}:
        return ()
    frames = [(label, *declared_framing(fields)) for label, fields in shots]
    findings = []
    for index, (previous, current) in enumerate(zip(frames, frames[1:]), 1):
        label, size, angle = current
        if not size or size != previous[1]:
            continue
        pair = (previous[0], label)
        same_angle = bool(angle) and angle == previous[2]
        if rules == CHINESE:
            findings.append(CameraCut("same_scale", pair, size, angle if same_angle else ""))
        elif same_angle:
            findings.append(CameraCut("same_framing", pair, size, angle))
            if fight and index >= 2 and frames[index - 2][1:] == (size, angle):
                findings.append(CameraCut("fight_triple", (frames[index - 2][0], *pair), size, angle))
    return tuple(findings)


def recorded_camera_cuts(rules, notes, entries):
    """Check (display label, shot) pairs; any approval belongs to this group."""
    if rules not in {CHINESE, ENGLISH}:
        return ()
    entries = tuple(entries)
    shots = [(label, shot.fields) for label, shot in entries]
    findings = camera_cuts(shots, rules, fight=notes.get("内容类型", "").strip() in {"打斗", "纯打斗"})
    if rules == CHINESE:
        # Store a manually approved exception in the receiving group's production
        # notes. Stable source IDs keep it attached to just that ordered pair.
        approved = set()
        for line in notes.get("景别衔接核对", "").splitlines():
            match = re.fullmatch(r"\s*(?:[-*•]\s+)?批准镜对[：:]\s*(\S+)\s+→\s+(\S+)\s*[|｜]\s*(.+?)\s*", line)
            if match:
                reason = normalized_text(match[3])
                if reason and reason not in MISSING_ANGLES | {"理由", "具体理由", "具体批准理由", "〈具体批准理由〉"}:
                    approved.add((match[1], match[2]))
        identifiers = {label: f"{label.rpartition('-')[0]}/{shot.id}" if shot.id else "" for label, shot in entries}
        remaining = []
        for cut in findings:
            pair = tuple(identifiers[label] for label in cut.shots)
            if pair not in approved:
                remaining.append(replace(cut, source_ids=pair))
        return tuple(remaining)

    repeated_purposes = []
    for (left, first), (right, second) in zip(shots, shots[1:]):
        size, _ = declared_framing(first)
        purpose = normalized_text(first.get("本格新增叙事功能"))
        if (size in {"中景", "大全景"} and size == declared_framing(second)[0]
                and purpose and purpose not in MISSING_ANGLES
                and purpose == normalized_text(second.get("本格新增叙事功能"))):
            repeated_purposes.append(CameraCut("same_purpose", (left, right), size))
    return (*findings, *repeated_purposes)


def project_camera_cuts(project):
    entries = [(f"{project.group}-{index:02d}", shot) for index, shot in enumerate(project.shots, 1)]
    return recorded_camera_cuts(project.rules, project.notes, entries)


def boundary_camera_cuts(left, right):
    if not left.shots or not right.shots:
        return ()
    entries = [(f"{left.group}-{len(left.shots):02d}", left.shots[-1]), (f"{right.group}-01", right.shots[0])]
    return recorded_camera_cuts(right.rules, right.notes, entries)


def require_camera_rules(project):
    findings = project_camera_cuts(project)
    if findings:
        raise ValueError(camera_findings_text(findings))


def camera_findings_text(findings, *, english=False):
    messages = {
        "same_scale": ("相邻独立镜头的登记景别相同。请改变实际取景范围，或将同一机位的连续动作合为一镜。",
                       "Same recorded shot size. Reframe the independent shot or merge one continuous take."),
        "same_framing": ("相邻独立镜头登记为同景别同角度。请调整实际取景范围或机位角度；同一机位的连续动作应合为一镜。",
                         "Same recorded shot size and angle. Change framing or camera angle, or merge one continuous take."),
        "fight_triple": ("打斗规则禁止三连同景别同角度。请核对并调整实际画面。",
                         "The fight rule prohibits three cuts with the same shot size and angle. Check the actual panels."),
        "same_purpose": ("相邻镜头以同一中景或大全景表达同一个已登记目的。请合镜或明确不同的叙事功能。",
                         "Adjacent shots repeat the same stated purpose at medium or extreme wide size."),
    }
    rows = []
    for item in findings:
        rows.append(f"{' → '.join(item.shots)} · {messages[item.kind][int(english)]}")
        if item.kind == "same_scale" and len(item.source_ids) == 2 and all(item.source_ids):
            rows.append("For an explicitly approved exception, add this line to the receiving group’s 景别衔接核对:"
                        if english else "若用户已明确批准此镜对，在后镜所在组的「景别衔接核对」添加一行：")
            rows.append(f"- 批准镜对：{' → '.join(item.source_ids)} | 〈具体批准理由〉")
    return "\n".join(rows)
