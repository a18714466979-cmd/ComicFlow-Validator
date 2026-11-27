"""Locate affected files and publish a new ZIP only after local revalidation."""

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .asset_registry import sha256_file
from .delivery_checker import validate_delivery
from .shot_review import load_shots
from .storyboard_review import ReviewResult, index_members


def affected_files(package: ReviewResult, group: str, shot: str) -> list[str]:
    records = load_shots(package)
    selected = [row for row in records if row.shot == shot and (not group or row.group == group)]
    if len(selected) != 1:
        raise ValueError("请填写有唯一生产记录的完整镜号，例如 SB05-04。")
    row = selected[0]
    paths = [row.storyboard, f"{row.group}/{row.plate.filename}" if row.plate else None]
    paths.extend(path for path in package.members if path.startswith(row.group + "/")
                 and path.lower().endswith(("_shot_details.txt", "/sd2_prompt.txt")))
    paths.extend(path for path in package.members if "/" not in path
                 and path.lower().startswith("readme"))
    return list(dict.fromkeys(path for path in paths if path))


def zip_fingerprints(path: Path) -> dict[str, str]:
    with ZipFile(path) as package:
        members = index_members(package)
        if len(members) != sum(not item.is_dir() for item in package.infolist()):
            raise ValueError("对照 ZIP 内有重复路径。")
        fingerprints = {}
        for relative, name in members.items():
            with package.open(name) as stream:
                fingerprints[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
        return fingerprints


@dataclass(frozen=True)
class PackageResult:
    exit_code: int
    report: str
    sha256: str | None = None
    output: Path | None = None
    changed: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


def write_delivery_zip(folder: Path, target: Path) -> None:
    """Write stable member metadata so an approved draft hash binds its final ZIP."""
    with ZipFile(target, "x") as package:
        for file in sorted(folder.rglob("*"), key=lambda path: path.relative_to(folder).as_posix()):
            if file.is_symlink():
                raise ValueError(f"交付目录包含符号链接：{file.relative_to(folder)}")
            if file.is_file():
                item = ZipInfo(file.relative_to(folder).as_posix())
                item.compress_type = ZIP_DEFLATED
                item.create_system = 3
                item.external_attr = 0o100644 << 16
                with file.open("rb") as source, package.open(item, "w") as destination:
                    copyfileobj(source, destination)


def pack_repair(
    folder: Path, output: Path, validator: Path, baseline: Path | None = None,
    registry: Path | None = None, panel_exception: Path | None = None,
) -> PackageResult:
    folder, output, validator = (path.expanduser().resolve() for path in (folder, output, validator))
    if not folder.is_dir() or not validator.is_file():
        raise ValueError("请选择返修后的交付目录和现行故事板校验脚本。")
    if output.suffix.lower() != ".zip" or not output.parent.is_dir() or output.is_relative_to(folder):
        raise ValueError("请在交付目录之外选择新 ZIP 的保存位置。")
    if output.exists():
        raise FileExistsError(f"目标已存在，请使用新文件名：{output.name}")
    preflight = validate_delivery(folder)
    if not preflight.passed:
        return PackageResult(1, "\n".join(f"{issue.level} {issue.path} · {issue.message}" for issue in preflight.issues))

    before = None
    if baseline:
        baseline = baseline.expanduser().resolve()
        if not baseline.is_file() or not validate_delivery(baseline).passed:
            raise ValueError("原交付 ZIP 未通过文件完整性检查。")
        before = zip_fingerprints(baseline)
    with TemporaryDirectory(prefix="comicflow-repair-", dir=output.parent) as temporary:
        draft = Path(temporary) / output.name
        write_delivery_zip(folder, draft)
        command = [sys.executable, "-m", "src.delivery_checker"]
        if panel_exception:
            command.extend((str(draft), "--panel-exception", str(panel_exception.resolve())))
        else:
            command.extend((str(folder), "--zip", str(draft)))
        command.extend(("--storyboard-validator", str(validator)))
        if registry:
            command.extend(("--asset-registry", str(registry.resolve())))
        run = subprocess.run(command, check=False, capture_output=True, encoding="utf-8", errors="replace",
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        report = (run.stdout + run.stderr).replace(str(draft), str(output))
        digest = sha256_file(draft)
        if run.returncode:
            return PackageResult(run.returncode, report, digest)

        after = zip_fingerprints(draft)
        current = {path.relative_to(folder).as_posix(): sha256_file(path)
                   for path in folder.rglob("*") if path.is_file()}
        if after != current:
            return PackageResult(1, report + "\n返修目录与 ZIP 成员或 SHA-256 不一致。", digest)
        changed = added = removed = ()
        if before is not None:
            changed = tuple(sorted(path for path in after.keys() & before.keys() if after[path] != before[path]))
            added = tuple(sorted(after.keys() - before.keys()))
            removed = tuple(sorted(before.keys() - after.keys()))
        if os.name == "nt":
            # Windows rename fails if the destination was created concurrently.
            draft.rename(output)
        else:
            os.link(draft, output)
        return PackageResult(0, report, digest, output, changed, added, removed)
