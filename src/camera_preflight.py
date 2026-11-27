"""Flag repeated framing in declared shot fields for subsequent visual review."""

from dataclasses import dataclass
import re
from unicodedata import normalize

from .production_rules import CHINESE, ENGLISH


SIZE_ALIASES = {
    "大全景": ("大远景", "大遠景", "extreme wide shot", "extreme long shot", "ews", "els"),
    "远景": ("遠景", "long shot", "ls"),
    "全景": ("wide shot", "full shot", "ws", "fs"),
    "中全景": ("medium wide shot", "medium long shot", "mws", "mls"),
    "中景": ("medium shot", "ms"),
    "中近景": ("近中景", "medium close up", "medium close up shot", "mcu"),
    "近景": ("close shot",),
    "特写": ("特寫", "close up", "close up shot", "cu"),
    "大特写": ("大特寫", "extreme close up", "extreme close up shot", "ecu"),
}
ANGLE_ALIASES = {
    "平视": ("平視", "eye level", "eye level shot"),
    "俯拍": ("俯视", "俯視", "high angle", "high angle shot"),
    "仰拍": ("仰视", "仰視", "low angle", "low angle shot"),
    "顶拍": ("頂拍", "overhead", "top down"),
}
MISSING_ANGLES = {
    "?", "无", "無", "未知", "未填", "未填写", "未提供", "未记录", "未定", "待定", "待确认", "待核对",
    "不适用", "不明确", "同上", "同前", "unknown", "unspecified", "not recorded", "not applicable",
    "n/a", "na", "none", "tbd",
}


@dataclass(frozen=True)
class CameraCut:
    kind: str
    shots: tuple[str, ...]
    size: str
    angle: str = ""


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


def project_camera_cuts(project):
    shots = ((f"{project.group}-{index:02d}", shot.fields) for index, shot in enumerate(project.shots, 1))
    return camera_cuts(shots, project.rules, fight=project.notes.get("内容类型", "").strip() in {"打斗", "纯打斗"})


def camera_findings_text(findings, *, english=False):
    messages = {
        "same_scale": ("分镜记录景别相同。请核对是否为重复构图或应合成一镜。",
                       "Same recorded shot size. Check for repeated framing or one continuous shot."),
        "same_framing": ("分镜记录同景别同角度。请核对叙事目的和真实动作衔接。",
                         "Same recorded shot size and angle. Check the shot purpose and match on action."),
        "fight_triple": ("打斗规则禁止三连同景别同角度。请核对并调整实际画面。",
                         "The fight rule prohibits three cuts with the same shot size and angle. Check the actual panels."),
    }
    return "\n".join(f"{' → '.join(item.shots)} · {messages[item.kind][int(english)]}" for item in findings)
