"""Approved sentence planning, group selection and cross-group source spans."""

import json
import re
from pathlib import Path

from .production_project import ProductionProject
from .storyboard_preflight import plan_dialogue


def plan_project_dialogue(project: ProductionProject, planner: Path) -> list[dict]:
    units = []
    for line in project.lines:
        offset = 0
        for end in line.sentence_ends or (len(line.text),):
            units.append({"id": line.id, "speaker": line.speaker, "text": line.text, "start": offset, "end": end})
            offset = end
    return plan_dialogue(json.dumps(units, ensure_ascii=False), planner) if units else []


def group_scope(group: dict) -> dict[str, list[int]]:
    scope = {}
    for fragment in group["fragments"]:
        start, _ = scope.get(fragment["id"], (fragment["start"], None))
        scope[fragment["id"]] = [start, fragment["end"]]
    return scope


def select_scope(project: ProductionProject, group: dict, previous_group: str) -> None:
    scope = group_scope(group)
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


def validated_scope(project: ProductionProject, planner: Path) -> dict[str, list[int]]:
    groups = plan_project_dialogue(project, planner)
    if project.dialogue_scope is None:
        if len(groups) > 1:
            raise ValueError("批准对白需要按整句分组，请在「文本制片」选择本组采用的候选。")
        return group_scope(groups[0]) if groups else {}
    if not any(group_scope(group) == project.dialogue_scope for group in groups):
        raise ValueError("本组对白区间与最新批准整句预排不符，请重新选择本组。")
    if any(start for start, _ in project.dialogue_scope.values()):
        previous = project.previous_group
        if not re.fullmatch(r"SB\d{2,}", previous) or int(previous[2:]) >= int(project.group[2:]):
            raise ValueError("请确认跨组续说的上一组组号。")
    return project.dialogue_scope


def handoff_rows(project: ProductionProject, scope: dict[str, list[int]]) -> tuple[list[str], list[str]]:
    source_rows, pending = [], []
    for line in project.lines:
        if line.id not in scope:
            continue
        start, end = scope[line.id]
        if start or end < len(line.text):
            source_rows.append(f"- {line.id} | {line.speaker} | {start}:{end} | {line.text}")
        if end < len(line.text):
            pending.append(f"- {line.id} | {line.speaker} | {line.text[end:].strip()}")
    return source_rows, pending
