"""Approved sentence planning, group selection and cross-group source spans."""

import json
import re
from pathlib import Path

from .production_project import ProductionProject
from .production_rules import CHINESE
from .storyboard_preflight import CHINESE_SPEECH_LIMIT, chinese_breaks, chinese_speech_length, plan_dialogue


def approved_breaks(line, rules):
    if line.sentence_ends:
        return line.sentence_ends
    return chinese_breaks(line.text) if rules == CHINESE else (len(line.text),)


def plan_project_dialogue(project: ProductionProject, planner: Path | None = None) -> list[dict]:
    units = []
    for line in project.lines:
        offset = 0
        for end in approved_breaks(line, project.rules):
            units.append({"id": line.id, "speaker": line.speaker, "text": line.text, "start": offset, "end": end})
            offset = end
    return plan_dialogue(json.dumps(units, ensure_ascii=False), planner, rules=project.rules)


def group_scope(group: dict) -> dict[str, list[int]]:
    scope = {}
    for fragment in group["fragments"]:
        start, _ = scope.get(fragment["id"], (fragment["start"], None))
        scope[fragment["id"]] = [start, fragment["end"]]
    return scope


def select_scope(project: ProductionProject, group: dict, previous_group: str) -> None:
    save_scope(project, group_scope(group), previous_group)


def save_scope(project: ProductionProject, scope: dict[str, list[int]], previous_group: str) -> None:
    if project.rules == CHINESE:
        check_chinese_scope(project, scope)
    previous_group = previous_group.strip().upper()
    if any(start for start, _ in scope.values()):
        if (not re.fullmatch(r"SB\d{2,}", previous_group)
                or int(previous_group[2:]) >= int(project.group[2:])):
            raise ValueError("本组有跨组续说，请填写实际上一组的组号，如 SB01。")
    else:
        previous_group = ""
    for index, shot in enumerate(project.shots, 1):
        for identity, start, end in shot.dialogue:
            span = scope.get(identity)
            if not span or not span[0] <= start < end <= span[1]:
                raise ValueError(f"第 {index} 镜引用 {identity} 的区间不在所选组内，请先在镜头清单调整。")
    project.dialogue_scope = scope
    project.previous_group = previous_group


def check_chinese_scope(project, scope) -> None:
    """Allow an early cut at approved boundaries while protecting the intervening dialogue."""
    selected = [(index, line) for index, line in enumerate(project.lines) if line.id in scope]
    if len(selected) != len(scope) or not selected and project.lines:
        raise ValueError("本组对白范围须对应已批准的原文。")
    total = 0
    last_index, last_complete = -1, False
    for index, line in selected:
        start, end = scope[line.id]
        cuts = approved_breaks(line, CHINESE)
        if not 0 <= start < end <= len(line.text) or start not in (0, *cuts) or end not in cuts:
            raise ValueError(f"{line.id} 的组首或组末须落在原文的批准自然切点。")
        if last_index >= 0 and (index != last_index + 1 or not last_complete or start):
            raise ValueError(f"{line.id} 之前有遗漏或不连续的批准对白。")
        total += chinese_speech_length(line.text[start:end])
        last_index, last_complete = index, end == len(line.text)
    if total > CHINESE_SPEECH_LIMIT:
        raise ValueError(f"本组实际发声 {total} 字，超过 100 字。请在批准的自然切点换组。")


def scope_from_shots(project) -> dict[str, list[int]]:
    scope = {}
    for shot in project.shots:
        for identity, start, end in shot.dialogue:
            first, last = scope.get(identity, (start, start))
            if last != start:
                raise ValueError(f"{identity} 的镜头对白区间有遗漏、重读或倒序。")
            scope[identity] = [first, end]
    return scope


def validated_scope(project: ProductionProject, planner: Path | None) -> dict[str, list[int]]:
    scope = project.dialogue_scope
    if scope is None:
        groups = plan_project_dialogue(project, planner)
        if len(groups) > 1:
            if project.rules == CHINESE:
                raise ValueError("批准对白需要换组，请在「文本制片」确认本组的发声范围。")
            raise ValueError("批准对白需要按整句分组，请在「文本制片」选择本组采用的候选。")
        return group_scope(groups[0]) if groups else {}
    if project.rules == CHINESE:
        check_chinese_scope(project, scope)
    elif not any(group_scope(group) == scope for group in plan_project_dialogue(project, planner)):
        raise ValueError("本组对白区间与最新批准整句预排不符，请重新选择本组。")
    if any(start for start, _ in scope.values()):
        previous = project.previous_group
        if not re.fullmatch(r"SB\d{2,}", previous) or int(previous[2:]) >= int(project.group[2:]):
            raise ValueError("请确认跨组续说的上一组组号。")
    return scope


def handoff_rows(project: ProductionProject, scope: dict[str, list[int]]) -> tuple[list[str], list[str]]:
    source_rows, pending = [], []
    for line in project.lines:
        if line.id not in scope:
            continue
        start, end = scope[line.id]
        if start or end < len(line.text):
            source_rows.append(f"- {line.id} | {line.speaker} | {start}:{end} | {line.text}")
        if end < len(line.text):
            remainder = line.text[end:] if project.rules == CHINESE else line.text[end:].strip()
            pending.append(f"- {line.id} | {line.speaker} | {remainder}")
    return source_rows, pending
