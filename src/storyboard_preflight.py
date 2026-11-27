"""Local preflight for approved dialogue and the nine-image budget."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from .production_rules import CHINESE, ENGLISH

IMAGE_LIMIT = 9
CHINESE_SPEECH_LIMIT = 100
SPOKEN_CHARACTERS = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff0-9A-Za-z]")
NATURAL_BREAK = re.compile(r"[。！？!?；]+[”’」』）》】]*\s*")


def chinese_speech_length(text: str) -> int:
    return len(SPOKEN_CHARACTERS.findall(text))


def chinese_breaks(text: str) -> tuple[int, ...]:
    last = len(text) - match.start() if (match := SPOKEN_CHARACTERS.search(text[::-1])) else 0
    cuts, start = [], 0
    for match in NATURAL_BREAK.finditer(text):
        end = match.end()
        if end < last and SPOKEN_CHARACTERS.search(text, start, end):
            cuts.append(end)
            start = end
    return (*cuts, len(text))


def plan_chinese_dialogue(approved: list) -> list[dict]:
    groups, fragments, total = [], [], 0
    seen = {}
    previous = None
    for record in approved:
        if not isinstance(record, dict):
            raise ValueError("对白 JSON 每条需要 id、speaker 和 text。")
        identity, speaker, text = (record.get(key) for key in ("id", "speaker", "text"))
        if (not all(isinstance(value, str) and value.strip() for value in (identity, speaker, text))
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", identity)
                or any(char in speaker for char in "|：:\r\n；;“”「」")
                or any(char in text for char in "\r\n")):
            raise ValueError("请填写有效的源对白 ID、说话人和单行批准原文。")
        if "start" in record or "end" in record:
            start, end = record.get("start"), record.get("end")
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                raise ValueError(f"{identity} 的批准片段区间无效。")
            ends = (end,)
        else:
            start = 0
            specified = record.get("sentence_ends", ())
            if not isinstance(specified, (list, tuple)):
                raise ValueError(f"{identity} 的自然切点须使用数组。")
            ends = specified or chinese_breaks(text)
            if (any(type(end) is not int for end in ends)
                    or list(ends) != sorted(set(ends)) or ends[0] <= 0 or ends[-1] != len(text)):
                raise ValueError(f"{identity} 的自然切点须递增，最后一项为完整原文长度。")
        if identity in seen and (previous != identity or seen[identity] != (speaker, text, start)):
            raise ValueError(f"{identity} 的说话人、原文或接续区间不一致。")
        for end in ends:
            spoken = text[start:end]
            count = chinese_speech_length(spoken)
            if not count:
                raise ValueError(f"{identity} [{start}:{end}] 没有可计入的实际发声。")
            if count > CHINESE_SPEECH_LIMIT:
                raise ValueError(f"{identity} [{start}:{end}] 有 {count} 字。请在批准原文的自然停顿处用 sentence_ends 标记切点。")
            if total + count > CHINESE_SPEECH_LIMIT:
                groups.append({"characters": total, "fragments": fragments})
                fragments, total = [], 0
            fragments.append({"id": identity, "speaker": speaker, "text": spoken,
                              "cue": "续说" if start else "首说", "start": start, "end": end})
            total += count
            start = end
        seen[identity] = (speaker, text, start)
        previous = identity
    if fragments:
        groups.append({"characters": total, "fragments": fragments})
    return groups


def group_capacity(group: dict, rules: str) -> str:
    if rules == ENGLISH:
        return f"{group['words']} 词"
    more_than_two = len({fragment["id"] for fragment in group["fragments"]}) > 2
    panels = "6 格" if more_than_two else "短对白 8 格／长或表演型 6 格"
    return f"{group['characters']} 字（{panels}）"


def plan_dialogue(source: str, planner: Path | None = None, *, rules: str = ENGLISH) -> list[dict]:
    """Run the current production workflow's planner without changing the source."""
    # Legacy Windows editors may include a BOM when the JSON is pasted or loaded.
    source = source.removeprefix("\ufeff")
    try:
        approved = json.loads(source)
    except json.JSONDecodeError as exc:
        raise ValueError(f"对白 JSON 第 {exc.lineno} 行、第 {exc.colno} 列格式有误。") from None
    if not isinstance(approved, list):
        raise ValueError("对白 JSON 需要是按说话顺序排列的数组。")
    if not approved:
        return []
    if rules == CHINESE:
        return plan_chinese_dialogue(approved)
    if planner is None or not planner.is_file():
        raise ValueError("请先选择故事板校验脚本，并确认同目录有 plan_english_dialogue.py。")

    with TemporaryDirectory(prefix="comicflow-dialogue-") as temporary:
        dialogue = Path(temporary) / "approved.json"
        dialogue.write_text(source, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(planner.resolve()), str(dialogue)],
            check=False, capture_output=True, encoding="utf-8", errors="replace", timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    if completed.returncode:
        lines = completed.stderr.strip().splitlines()
        reason = lines[-1].partition(": error: ")[-1] if lines else "对白预排脚本未返回结果。"
        raise ValueError(reason)
    try:
        groups = json.loads(completed.stdout)
        if not isinstance(groups, list):
            raise ValueError
        for group in groups:
            if type(group["words"]) is not int or not group["fragments"]:
                raise ValueError
            for fragment in group["fragments"]:
                for key in ("id", "speaker", "text", "cue", "start", "end"):
                    fragment[key]
    except (ValueError, TypeError, KeyError):
        raise ValueError("预排脚本输出的格式不兼容，请检查所选工作流版本。") from None
    return groups


def image_budget(leads: int, supporting: int, props: int, scenes: int, *, storyboards: int = 1) -> tuple[int, int]:
    """Count image files, including each planned storyboard page."""
    if type(storyboards) is not int or storyboards not in (1, 2):
        raise ValueError("故事板需按实际页数计入九图。")
    if any(type(count) is not int or count < 0 for count in (leads, supporting, props, scenes)):
        raise ValueError("图片张数需为非负整数。")
    total = storyboards + leads + supporting + props + scenes
    return total, IMAGE_LIMIT - total
