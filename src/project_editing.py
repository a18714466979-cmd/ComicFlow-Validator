"""Merge changes from a task's project snapshot into the current saved group."""

from dataclasses import fields, is_dataclass, replace

_MISSING = object()


class ProjectEditConflict(ValueError):
    """The same part of the group was changed independently."""


def merge_project_edits(baseline, edited, current):
    """Preserve changes from other tasks and reject conflicting edits before saving."""
    if (baseline.episode, baseline.group, baseline.rules) != (current.episode, current.group, current.rules):
        raise ProjectEditConflict("项目的集次、组号或规则已变更，请重新打开任务。")
    return _merge(baseline, edited, current, "")


def _merge(base, edited, current, path):
    if edited == base:
        return current
    if current == base or edited == current:
        return edited
    if isinstance(base, dict) and isinstance(edited, dict) and isinstance(current, dict):
        changes = {}
        for key in dict.fromkeys((*current, *edited, *base)):
            value = _merge(base.get(key, _MISSING), edited.get(key, _MISSING), current.get(key, _MISSING),
                           f"{path}.{key}")
            if value is not _MISSING:
                changes[key] = value
        return changes
    if is_dataclass(base) and type(base) is type(edited) is type(current):
        return replace(current, **{
            item.name: _merge(getattr(base, item.name), getattr(edited, item.name), getattr(current, item.name),
                              f"{path}.{item.name}")
            for item in fields(base)
        })
    if isinstance(base, list) and isinstance(edited, list) and isinstance(current, list):
        keys = tuple(map(_identity, base))
        if all(keys) and len(keys) == len(set(keys)):
            latest = tuple(map(_identity, current))
            draft = tuple(map(_identity, edited))
            if latest[:len(keys)] == keys and draft[:len(keys)] == keys:
                result = [_merge(x, y, z, f"{path}[{index + 1}]")
                          for index, (x, y, z) in enumerate(zip(base, edited, current))]
                pending = dict(zip(latest[len(keys):], current[len(keys):]))
                for key, item in zip(draft[len(keys):], edited[len(keys):]):
                    pending[key] = _merge(_MISSING, item, pending.get(key, _MISSING), f"{path}[{key}]")
                if all(pending) and len(pending) == len(set(latest + draft) - set(keys)):
                    return result + list(pending.values())
        if current[:len(base)] == edited[:len(base)] == base:
            extra = current[len(base):]
            return base + extra + [item for item in edited[len(base):] if item not in extra]
    section = path.lstrip(".")
    raise ProjectEditConflict(f"其他任务已修改同一处内容（{section}）。请先核对冲突，再重新打开任务。")


def _identity(record):
    return record.get("id") if isinstance(record, dict) else getattr(record, "id", None)
