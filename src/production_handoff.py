"""Preserve deferred shots and review the boundary between adjacent groups."""

from dataclasses import replace

from .camera_preflight import boundary_camera_cuts, camera_findings_text
from .production_dialogue import approved_breaks, handoff_rows, validated_scope
from .production_rules import CHINESE


def defer_tail(project, index):
    if not 0 <= index < len(project.shots):
        raise ValueError("请选择待制作尾段的首镜。")
    project.pending_shots = project.shots[index:] + project.pending_shots
    del project.shots[index:]


def restore_tail(project):
    project.shots.extend(project.pending_shots)
    project.pending_shots.clear()


def pending_spans(project):
    lines = {line.id: line for line in project.lines}
    spans = {}
    for shot in project.pending_shots:
        for identity, start, end in shot.dialogue:
            line = lines.get(identity)
            first, last = spans.get(identity, (start, start))
            if not line or line.source != shot.source or start != last or not 0 <= start < end <= len(line.text):
                raise ValueError(f"待制作对白 {identity} 的批准来源或区间需要复核。")
            spans[identity] = (first, end)
    return spans


def active_scope(project, planner):
    scope = validated_scope(project, planner)
    if not project.pending_shots:
        return scope
    pending = pending_spans(project)
    lines = {line.id: line for line in project.lines}
    result = {}
    for identity, (start, end) in scope.items():
        cut = pending.get(identity, (end, end))[0]
        if cut < start:
            raise ValueError(f"待制作对白 {identity} 早于本组批准的区间。")
        if start < cut < end and cut not in approved_breaks(lines[identity], project.rules):
            boundary = "自然切点" if project.rules == CHINESE else "整句边界"
            raise ValueError(f"{identity} 延到下一批时须在批准的{boundary}交接。")
        if cut != start:
            result[identity] = [start, min(cut, end)]
    return result


def pending_record(project, scope):
    _, leftover = handoff_rows(project, scope)
    spans = pending_spans(project)
    seen = {row.split(" | ", 1)[0][2:] for row in leftover}
    for line in project.lines:
        if line.id in spans and line.id not in seen:
            leftover.append(f"- {line.id} | {line.speaker} | {line.text[spans[line.id][0]:].strip()}")
            seen.add(line.id)
    if project.rules == CHINESE and scope:
        last = max(index for index, line in enumerate(project.lines) if line.id in scope)
        leftover.extend(f"- {line.id} | {line.speaker} | {line.text}" for line in project.lines[last + 1:]
                        if line.id not in seen)
    if not leftover and not project.pending_shots:
        return ""
    result = [f"上一正式组 {project.group} 退出状态：{project.notes.get('本组退出状态') or '待核对'}",
              "制作状态：需与下一批连续分镜合组制作，未遗漏、未完成故事板。"]
    if leftover:
        result.extend(("待接续批准对白：", *leftover))
    sources = {item.id: item for item in project.sources}
    for number, shot in enumerate(project.pending_shots, 1):
        source = sources.get(shot.source)
        if source is None or not shot.anchor:
            raise ValueError("待制作镜头需要保留批准剧本与源段。")
        result.extend((f"\n待制作镜头 {number:02d}", f"源镜ID：{shot.id}", f"批准来源：{source.name} {source.version}",
                       f"源段：{shot.anchor}", f"地点：{shot.scene}", f"净板机位说明：{shot.plate_note}"))
        result.extend(f"{key}：{value}" for key, value in shot.fields.items() if value.strip())
        for identity, start, end in shot.dialogue:
            line = next(item for item in project.lines if item.id == identity)
            result.append(f"批准对白 {identity} [{start}:{end}] {line.speaker}：“{line.text[start:end].strip()}”")
    return "\n".join(result) + "\n"


def adjacent(left, right):
    if left.rules != right.rules:
        raise ValueError("相邻组需使用同一套制作规则。")
    if (left.name, left.episode) != (right.name, right.episode) or int(right.group[2:]) - int(left.group[2:]) != 1:
        raise ValueError("请选择同项目、同集次且组号连续的项目。")


def adopt_pending(previous, project):
    adjacent(previous, project)
    if not previous.pending_shots:
        raise ValueError("上一组没有待制作镜头。")
    existing = {shot.id for shot in project.shots + project.pending_shots}
    if any(shot.id in existing for shot in previous.pending_shots):
        raise ValueError("当前项目已收录待制作镜头。")
    pending_spans(previous)
    sources = {item.id: item for item in previous.sources}
    used, catalog, transferred = {}, [], []
    for shot in previous.pending_shots:
        source = sources[shot.source]
        target = next((item for item in project.sources if (item.name, item.version) == (source.name, source.version)), None)
        if target is not None and source.text != target.text:
            raise ValueError("当前项目同版本批准剧本的原文不同。")
        destination = used.setdefault(source.id, target or source)
        transferred.append(replace(shot, source=destination.id, plate=""))
    ids = {identity for shot in previous.pending_shots for identity, _, _ in shot.dialogue}
    current = {line.id: line for line in project.lines}
    for original in previous.lines:
        if original.id not in ids:
            continue
        line = replace(original, source=used[original.source].id)
        if line.id in current and line != current[line.id]:
            raise ValueError(f"对白 {line.id} 与当前批准来源不一致。")
        if line.id not in current:
            catalog.append(line)
    project.sources.extend(item for item in used.values() if item not in project.sources)
    project.shots[:0] = transferred
    project.lines[:0] = catalog
    if catalog:
        project.dialogue_scope = None


def boundary_report(left, right, planner, *, english=False):
    adjacent(left, right)
    if not left.shots or not right.shots:
        raise ValueError("相邻两组需要实际首尾镜头。")
    a, b = active_scope(left, planner), active_scope(right, planner)
    older, newer = ({line.id: line for line in project.lines} for project in (left, right))
    transcript = []
    issues = [camera_findings_text((cut,), english=english) for cut in boundary_camera_cuts(left, right)]
    for identity, (start, end) in b.items():
        if identity in a:
            x, y = older[identity], newer[identity]
            if (x.speaker, x.text) != (y.speaker, y.text) or a[identity][1] != start:
                issues.append(f"{identity} 的说话人、原文或相邻区间不一致。")
            else:
                transcript.append(f"{identity} {x.speaker} {a[identity][0]}:{start} → {start}:{end}")
        elif start:
            issues.append(f"{identity} 的续说缺少相邻前组的对应原文。")
        if start and right.previous_group != left.group:
            issues.append(f"{identity} 的续说来源需指向 {left.group}。")
    for identity, (_, end) in a.items():
        if end < len(older[identity].text) and identity not in b:
            issues.append(f"{identity} 仍有批准对白未被后组接续。")
    if left.rules == CHINESE and a and b:
        source_order = tuple(older)
        final_index = max(index for index, identity in enumerate(source_order) if identity in a)
        final_id = source_order[final_index]
        if a[final_id][1] == len(older[final_id].text) and final_index + 1 < len(source_order):
            expected = source_order[final_index + 1]
            lead = next(identity for identity in newer if identity in b)
            if lead != expected or (newer[lead].speaker, newer[lead].text) != (older[expected].speaker, older[expected].text):
                issues.append(f"后组需接续前组留存的批准对白 {expected}。")
    right_ids = {shot.id for shot in right.shots + right.pending_shots}
    if any(shot.id not in right_ids for shot in left.pending_shots):
        issues.append("前组仍有待制作镜头未移交到后组。")
    exit_state = left.notes.get("本组退出状态", "").strip()
    entry_state = right.notes.get("本组进入状态", "").strip()
    if not exit_state or not entry_state:
        issues.append("请填写前组退出状态和后组进入状态。")

    def glimpse(project, shot, ordinal, state):
        return (f"{project.group}-{ordinal:02d}  {shot.anchor}\n"
                f"动作起止　{shot.fields.get('动作起止') or '待核对'}\n"
                f"连续性　{shot.fields.get('连续性') or '待核对'}\n状态　{state}")

    lines = [glimpse(left, left.shots[-1], len(left.shots), exit_state), glimpse(right, right.shots[0], 1, entry_state),
             "对白交接\n" + ("\n".join(transcript) if transcript else "本边界无共用对白续说")]
    if exit_state and entry_state and exit_state != entry_state:
        lines.append("进出状态文字不同，请对照实际画面解释衔接。")
    if issues:
        lines.append("待处理\n" + "\n".join(issues))
    return "\n\n".join(lines), tuple(dict.fromkeys(issues))


def confirm_boundary(left, right, planner, review):
    _, issues = boundary_report(left, right, planner)
    if issues:
        raise ValueError("\n".join(issues))
    if not review.strip():
        raise ValueError("请记录实际核对的动作、空间和状态。")
    left.handoffs[right.group] = {"left": left.fingerprint(), "right": right.fingerprint(), "review": review.strip()}


def reviewed_boundary(left, right):
    state = left.handoffs.get(right.group, {})
    return ((state.get("left"), state.get("right")) == (left.fingerprint(), right.fingerprint())
            and bool(state.get("review", "").strip()))
