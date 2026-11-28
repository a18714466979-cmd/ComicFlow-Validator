"""Publish reviewed storyboard groups as independently usable episode and series archives."""

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from .asset_registry import sha256_file
from .batch_planning import coverage_issues, trace_rows
from .production_export import publish_batch, publish_project
from .production_handoff import boundary_report, reviewed_boundary
from .production_project import ProductionProject
from .production_rules import CHINESE, rule_revision


@dataclass
class _Episode:
    id: str
    title: str
    plan: dict
    files: list
    trace: list
    signature: str


def _read_episode(workspace, episode_id, validator):
    episode = next((ep for ep in workspace.episodes if ep.id == episode_id), None)
    if episode is None or not re.fullmatch(r"EP[0-9]+", episode_id):
        raise ValueError("请选择批次里已有的集次。")
    if not workspace.plan_approved(episode_id):
        raise ValueError(f"{episode_id} 的分组计划尚未确认。")
    if not validator or not Path(validator).is_file():
        raise ValueError(f"{episode_id} 缺少对应制作规则的正式校验脚本。")
    plan = workspace.plan_for(episode_id)
    if (plan["episode"] != episode_id or plan["rules"] != workspace.rules
            or plan["source_text"] != workspace.source_text(episode_id)):
        raise ValueError(f"{episode_id} 的分组计划与当前批准剧本或规则不一致。")
    paths = workspace.group_paths(episode_id)
    expected = [f"SB{number:02d}" for number in range(1, len(paths) + 1)]
    if not paths or [g["group"] for g in plan["groups"]] != expected:
        raise ValueError(f"{episode_id} 的组号、组数或顺序有缺失。")
    files = [(ProductionProject.open(path), path) for path in paths]
    projects = [project for project, _ in files]
    for index, project in enumerate(projects):
        label = f"{episode_id}/{expected[index]}"
        if ((project.name, project.episode, project.rules, project.group)
                != (plan["name"], episode_id, workspace.rules, expected[index])):
            raise ValueError(f"{label} 的项目身份、制作规则或组号与计划不一致。")
        gaps = workspace.required_asset_gaps(episode_id, project.group)
        if gaps:
            raise ValueError(f"{label} 缺少指定资产：" + "、".join(gaps))
        if project.impacts():
            raise ValueError(f"{label} 尚未逐格确认当前版本的画面。")
        if index < len(projects) - 1 and project.notes.get("分组状态", "").strip() == "整集尾组":
            raise ValueError(f"{label} 提前标记为整集尾组。")
    if projects[-1].pending_shots:
        raise ValueError(f"{episode_id} 最后一组仍有待制作镜头。")
    problems = coverage_issues(plan, projects)
    if problems:
        raise ValueError(f"{episode_id} 原稿覆盖需要复核：\n" + "\n".join(problems))

    planner = None if workspace.rules == CHINESE else Path(validator).with_name("plan_english_dialogue.py")
    for left, right in zip(projects, projects[1:]):
        _, issues = boundary_report(left, right, planner)
        if issues:
            raise ValueError(f"{episode_id}/{left.group} → {right.group}\n" + "\n".join(issues))
        if not reviewed_boundary(left, right):
            raise ValueError(f"{episode_id}/{left.group} → {right.group} 的当前版本尚未确认交接。")

    # Exclude private card drafts. A new formal shot, approval or boundary invalidates this export.
    revisions = [(p.fingerprint(), p.structure_review, p.handoffs,
                  [(r.identity, r.state, r.version, r.deliver)
                   for r in workspace.required_assets(episode_id, p.group)]) for p in projects]
    signature = hashlib.sha256(json.dumps(
        [episode.title, plan, revisions], ensure_ascii=False, sort_keys=True,
    ).encode("utf-8")).hexdigest()
    return _Episode(episode_id, episode.title, plan, files, trace_rows(plan, projects), signature)


def _accept(result, label):
    if result.exit_code or not result.output or not result.sha256:
        raise ValueError(f"{label} 未通过正式验收：\n{result.report}")
    with ZipFile(result.output) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"{label} 的 ZIP 成员校验失败：{bad}")
    if sha256_file(result.output) != result.sha256:
        raise ValueError(f"{label} 的 ZIP 版本在验收后发生变化。")


def _bundle(output, files, documents):
    """Store verified child ZIPs as-is, then reopen and verify the assembled archive."""
    texts = {name: value.encode("utf-8-sig") for name, value in documents.items()}
    digests = {name: digest for name, path, digest in files}
    digests.update((name, hashlib.sha256(data).hexdigest()) for name, data in texts.items())
    if len(digests) != len(files) + len(documents):
        raise ValueError("交付文件名重复。")
    with ZipFile(output, "x") as archive:
        for name, path, _ in files:
            archive.write(path, name, compress_type=ZIP_STORED)
        for name, data in texts.items():
            archive.writestr(name, data, compress_type=ZIP_DEFLATED)
    with ZipFile(output) as archive:
        if list(archive.namelist()) != list(digests):
            raise ValueError("交付 ZIP 与预期清单不一致。")
        for name, digest in digests.items():
            with archive.open(name) as stream:
                # Reading the entire member checks its CRC as well as its SHA-256.
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise ValueError(f"交付文件与批准版本不一致：{name}")


def _write_episode(episode, validator, scratch, output):
    files, group_records = [], []
    if len(episode.files) > 1:
        combined = publish_batch(episode.files, validator, scratch / "combined.zip")
        _accept(combined, episode.id)
        combined.output.unlink()
    for project, path in episode.files:
        name = f"{project.group}.zip"
        result = publish_project(project, path, validator, scratch / name)
        _accept(result, f"{episode.id}/{project.group}")
        if project is episode.files[-1][0]:
            with ZipFile(result.output) as package:
                if "待制作分镜.txt" in package.namelist():
                    raise ValueError(f"{episode.id} 尾组仍有未交付的镜头或对白。")
        files.append((name, result.output, result.sha256))
        group_records.append({"组号": project.group, "文件": name, "镜头数": len(project.shots),
                              "确认版本": project.fingerprint(), "SHA256": result.sha256})
    index = {
        "集号": episode.id, "片名": episode.title, "制作规则版本": rule_revision(episode.plan["rules"]),
        "原稿": episode.plan["source_name"], "原稿SHA256": hashlib.sha256(
            episode.plan["source_text"].encode("utf-8")).hexdigest(),
        "交付组": group_records, "原稿到分镜": episode.trace,
        "相邻组交接": [{"前组": left.group, "后组": right.group, "核对": left.handoffs[right.group]["review"]}
                    for (left, _), (right, _) in zip(episode.files, episode.files[1:])],
    }
    readme = [f"{episode.id} · {episode.title}", "", "各组可单独解压使用。原稿覆盖.json 可按源段或镜号查找。", ""]
    readme.extend(f"{record['组号']}    {record['镜头数']} 镜    {record['文件']}" for record in group_records)
    _bundle(output, files, {"交付目录.txt": "\n".join(readme) + "\n",
                            "原稿覆盖.json": json.dumps(index, ensure_ascii=False, indent=2) + "\n"})


def _destination(output, replace):
    output = Path(output).expanduser().absolute()
    if output.suffix.lower() != ".zip" or not output.parent.is_dir():
        raise ValueError("请选择已有目录中的 .zip 文件名。")
    if output.is_symlink() or output.exists() and not output.is_file():
        raise ValueError("交付目标必须是普通 ZIP 文件。")
    if output.exists() and not replace:
        raise FileExistsError(f"目标已存在，请确认替换或选择新文件名：{output.name}")
    return output, _file_version(output)


def _file_version(path):
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, sha256_file(path)


@contextmanager
def _publication_lock(output):
    # Concurrent ComicFlow writers share this short-lived OS lock across workspaces.
    # Keep the lock inode in the OS temp directory so that waiting processes agree.
    key = hashlib.sha256(os.fsencode(os.path.normcase(str(output.resolve())))).hexdigest()
    with (Path(gettempdir()) / f"comicflow-delivery-{key}.lock").open("a+b") as holder:
        if os.name == "nt":
            import msvcrt
            if holder.tell() == 0:
                holder.write(b"0")
                holder.flush()
            holder.seek(0)
            msvcrt.locking(holder.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        yield


def _commit(draft, output, original):
    with _publication_lock(output):
        if output.is_symlink() or _file_version(output) != original:
            raise FileExistsError(f"目标文件在导出期间发生变化，已保留现有文件：{output.name}")
        if original is not None:
            draft.replace(output)
        elif os.name == "nt":
            draft.rename(output)
        else:
            os.link(draft, output)
    return output


def publish_episode(workspace, episode_id, validator, output, *, replace=False):
    """Deliver one whole episode using the active plan and actual reviewed group projects."""
    output, original = _destination(output, replace)
    workspace = type(workspace).open(workspace.path)
    episode = _read_episode(workspace, episode_id, validator)
    with TemporaryDirectory(prefix="comicflow-episode-", dir=output.parent) as temp:
        scratch = Path(temp)
        draft = scratch / "episode.zip"
        _write_episode(episode, Path(validator), scratch, draft)
        current = type(workspace).open(workspace.path)
        if _read_episode(current, episode_id, validator).signature != episode.signature:
            raise ValueError(f"{episode_id} 数据已在导出期间更新，请重新验收后交付。")
        return _commit(draft, output, original)


def publish_series(workspace, validator_by_rules, output, episode_ids=None, *, replace=False):
    """Deliver the selected complete episodes in their project order."""
    output, original = _destination(output, replace)
    workspace = type(workspace).open(workspace.path)
    ordered = [ep.id for ep in workspace.episodes]
    ids = list(ordered if episode_ids is None else episode_ids)
    if not ids or len(set(ids)) != len(ids) or set(ids) - set(ordered):
        raise ValueError("请选择批次中的有效集次，每集仅可交付一次。")
    if workspace.rules not in validator_by_rules:
        raise ValueError("请选择本批次制作规则对应的正式校验脚本。")
    validator = validator_by_rules[workspace.rules]
    episodes = [_read_episode(workspace, ep, validator) for ep in ordered if ep in ids]
    with TemporaryDirectory(prefix="comicflow-series-", dir=output.parent) as temp:
        scratch = Path(temp)
        files, records = [], []
        for episode in episodes:
            subdir = scratch / episode.id
            subdir.mkdir()
            name = f"{episode.id}.zip"
            path = subdir / name
            _write_episode(episode, Path(validator), subdir, path)
            digest = sha256_file(path)
            files.append((name, path, digest))
            records.append({"集号": episode.id, "片名": episode.title, "文件": name,
                            "组数": len(episode.files), "SHA256": digest})
        draft = scratch / "series.zip"
        _bundle(draft, files, {"剧集目录.json": json.dumps(records, ensure_ascii=False, indent=2) + "\n"})
        current = type(workspace).open(workspace.path)
        if episode_ids is None and ordered != [ep.id for ep in current.episodes]:
            raise ValueError("剧集清单已在导出期间更新，请重新交付。")
        for episode in episodes:
            if _read_episode(current, episode.id, validator).signature != episode.signature:
                raise ValueError(f"{episode.id} 在导出期间发生修改，请重新交付。")
        return _commit(draft, output, original)
