"""Run the local validator and locate its diagnostics inside the same ZIP copy."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from shutil import copyfile
from subprocess import run
import os
import re
import sys
from zipfile import ZipFile


LEVELS = {
    "ERROR": "错误", "WARNING": "警告", "未验证": "未验证", "已批准例外": "已批准例外",
}
GROUP = re.compile(r"SB\d+(?:_[^/:：\r\n]+)?\Z", re.IGNORECASE)
SHOT = re.compile(r"\b(SB\d+-\d+[A-Za-z]?)\b|\b(?:shot|panel)\s+(\d+[A-Za-z]?)\b", re.IGNORECASE)
NAMED_FILE = re.compile(r"[^/\\:：]+\.(?:txt|png|jpe?g|webp)\b", re.IGNORECASE)
PREVIEW_LIMIT = {".txt": 1024**2, ".png": 32 * 1024**2, ".jpg": 32 * 1024**2,
                 ".jpeg": 32 * 1024**2, ".webp": 32 * 1024**2}


@dataclass(frozen=True)
class ReviewIssue:
    status: str
    group: str
    shot: str
    filename: str
    message: str


@dataclass(frozen=True)
class ReviewResult:
    exit_code: int
    report: str
    archive: Path
    members: dict[str, str]
    issues: list[ReviewIssue]


def index_members(archive: ZipFile) -> dict[str, str]:
    paths = [info.filename for info in archive.infolist() if not info.is_dir()]
    roots = {path.split("/", 1)[0] for path in paths}
    prefix = ""
    if len(roots) == 1:
        root = next(iter(roots))
        if any(len(parts := path.split("/")) >= 3 and GROUP.fullmatch(parts[1]) for path in paths):
            prefix = root + "/"
    return {path.removeprefix(prefix): path for path in paths}


def locate_issue(line: str, members: dict[str, str]) -> ReviewIssue | None:
    match = re.match(r"^(?:\[(ERROR|WARNING)\]\s*|(ERROR|WARNING|未验证|已批准例外):\s*)(.+)$", line)
    if not match:
        return None
    bracket, plain, message = match.groups()
    level = bracket or plain
    location, _, detail = message.partition(":" if bracket is None else " | ")
    first = location.partition("/")[0].strip()
    if level == "已批准例外":
        first = first.split(maxsplit=1)[0]
    group = first if GROUP.fullmatch(first) else ""
    filename = location.partition("/")[2].strip() if group else ""
    if PurePosixPath(filename).suffix.lower() not in PREVIEW_LIMIT:
        filename = ""
    if group and not filename and level != "未验证":
        group_files = [PurePosixPath(path).name for path in members if path.startswith(group + "/")]
        filename = next((name for name in sorted(group_files, key=len, reverse=True)
                         if name in detail), "")
        if not filename and (missing := re.match(r"\s*(.+?\.(?:txt|png|jpe?g|webp)) is missing\b", detail)):
            filename = missing[1]
    elif not filename and location in members and NAMED_FILE.fullmatch(location):
        filename = location
    shot_match = SHOT.search(detail)
    shot = (shot_match[1] or shot_match[2]) if shot_match else ""
    return ReviewIssue(LEVELS[level], group, shot, filename, message)


def run_review(arguments: list[str], directory: Path) -> ReviewResult:
    archive = directory / Path(arguments[0]).name
    copyfile(arguments[0], archive)
    completed = run(
        [sys.executable, "-m", "src.delivery_checker", str(archive), *arguments[1:]],
        capture_output=True, check=False, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    report = (completed.stdout + completed.stderr).replace(str(archive), arguments[0])
    members = {}
    integrity_passed = completed.returncode == 0 and ("--storyboard-validator" not in arguments[1:])
    if integrity_passed or re.search(r"^RESULT: ", completed.stdout, re.MULTILINE):
        with ZipFile(archive) as package:
            members = index_members(package)
    issues = []
    for line in report.splitlines():
        issue = locate_issue(line, members)
        if issue:
            issues.append(issue)
    return ReviewResult(completed.returncode, report, archive, members, issues)


def read_preview(result: ReviewResult, relative: str) -> bytes:
    limit = PREVIEW_LIMIT[PurePosixPath(relative).suffix.lower()]
    with ZipFile(result.archive) as package:
        member = package.getinfo(result.members[relative])
        if member.file_size > limit:
            raise ValueError("文件超过内置预览大小限制。")
        with package.open(member) as stream:
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError("文件超过内置预览大小限制。")
            return data
