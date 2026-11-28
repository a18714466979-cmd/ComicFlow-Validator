"""Route a reviewed delivery issue back to its source project and production tool."""

from dataclasses import dataclass
from itertools import islice
from pathlib import Path, PurePosixPath
import re
from tkinter import filedialog, messagebox
from zipfile import BadZipFile

from .production_project import ProductionProject
from .production_rules import ENGLISH, CHINESE, rule_revision
from .shot_review import IMAGE_SUFFIXES, shot_id
from .storyboard_review import GROUP, ReviewIssue, ReviewResult, read_preview
from .ui_language import translate


GROUP_HEADER = re.compile(r"组号[：:]\s*(SB\d+)\s*", re.IGNORECASE)
RULE_HEADER = re.compile(r"制作规则[：:]\s*(\S+)\s*")
SHOT_ROW = re.compile(r"-\s+(SB\d+-\d+[A-Z]?)\s*\|\s*([A-Za-z0-9._-]+)\s*\|", re.IGNORECASE)


@dataclass(frozen=True)
class ReviewLocation:
    group: str
    shot: str
    filename: str
    stage: str
    title: str = ""
    episode: str = ""
    rules: str = ""
    shot_ids: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RepairTarget:
    path: Path
    stage: str
    shot_id: str = ""
    asset_filename: str = ""


def project_group(folder: str) -> str:
    return folder.partition("_")[0].upper() if GROUP.fullmatch(folder) else ""


def _production_stage(filename: str, message: str, shot: str) -> str:
    filename, message = filename.casefold(), message.casefold()
    if filename == "sd2_prompt.txt":
        return "prompts"
    if any(term in message for term in ("场景局部", "净板绑定", "板格坐标", "窗口坐标", "格间衔接",
                                        "plate mapping", "shot window", "layout slot")):
        return "layout"
    if PurePosixPath(filename).suffix in IMAGE_SUFFIXES:
        return "assets"
    if "提示词" in message or re.search(r"\bprompts?\b", message):
        return "prompts"
    if (any(term in message for term in ("原图", "复用", "资产", "16:9"))
            or re.search(r"\b(images?|assets?|pixels?|ratios?)\b", message)):
        return "assets"
    if shot or filename.endswith("_shot_details.txt"):
        return "shots"
    return "deliver"


def _read_group_trace(result: ReviewResult, group: str):
    """Read the existing README export ledger, including combined group packages."""
    readmes = [path for path in result.members if path.casefold() == "readme.txt"]
    if len(readmes) != 1:
        return "", "", "", ()
    try:
        lines = read_preview(result, readmes[0]).decode("utf-8-sig").splitlines()
    except (OSError, ValueError, KeyError, BadZipFile):
        return "", "", "", ()
    headers = [(n, match[1].upper()) for n, line in enumerate(lines)
               if (match := GROUP_HEADER.fullmatch(line.strip()))]
    matches = [(n, index) for index, (n, identity) in enumerate(headers) if identity == group]
    if len(matches) != 1:
        return "", "", "", ()
    start, index = matches[0]
    end = headers[index + 1][0] if index + 1 < len(headers) else len(lines)
    rule = RULE_HEADER.fullmatch(lines[start - 1].strip()) if start else None
    header_index = start - (2 if rule else 1)
    header = lines[header_index].strip() if header_index >= 0 else ""
    title, _, episode = header.rpartition(" · ") if not header.startswith(("-", "•", "*")) else ("", "", "")
    if not title:
        episode = ""
    revisions = {CHINESE: (CHINESE, rule_revision(CHINESE)),
                 ENGLISH: (ENGLISH, "14.10.4", rule_revision(ENGLISH))}
    rules = next((key for key, versions in revisions.items() if rule and rule[1] in versions), "")
    ledger = next((n for n in range(start + 1, end) if lines[n].strip() in ("镜头与来源：", "镜头与来源:")), None)
    shots = []
    if ledger is not None:
        for line in lines[ledger + 1:end]:
            if not (row := SHOT_ROW.match(line.strip())) or not row[1].upper().startswith(group + "-"):
                break
            shots.append((shot_id(row[1], group), row[2]))
    if (len({label for label, _ in shots}) != len(shots)
            or len({identity for _, identity in shots}) != len(shots)):
        shots.clear()
    return title, episode, rules, tuple(shots)


def review_location(result: ReviewResult, issue: ReviewIssue | None = None, selected_member: str = "") -> ReviewLocation:
    folders = {folder for path in result.members if (folder := path.partition("/")[0]) and GROUP.fullmatch(folder)}
    member = PurePosixPath(selected_member)
    member_folder = member.parts[0] if len(member.parts) > 1 else ""
    explicit_folder = issue.group if issue and GROUP.fullmatch(issue.group) else ""
    shot_folder = re.match(r"^(SB\d+)-", issue.shot, re.IGNORECASE) if issue else None
    if explicit_folder:
        chosen = [folder for folder in folders if folder.casefold() == explicit_folder.casefold()]
        if not chosen:
            chosen = [folder for folder in folders if project_group(folder) == project_group(explicit_folder)]
    elif member_folder in folders:
        chosen = [member_folder]
    elif shot_folder:
        chosen = [folder for folder in folders if project_group(folder) == shot_folder[1].upper()]
    else:
        chosen = list(folders)
    if len(chosen) != 1:
        raise ValueError("请选择可定位到唯一故事板组的验收结果或包内文件。")
    folder = chosen[0]
    group = project_group(folder)
    numeric_label = shot_id(issue.shot, group) if issue and issue.shot else ""
    label = numeric_label if numeric_label.startswith(group + "-") else ""
    filename = PurePosixPath(issue.filename).name if issue and issue.filename else ""
    if not filename and member_folder == folder:
        filename = member.name
    stage = _production_stage(filename, issue.message if issue else "", label)
    if sum(project_group(item) == group for item in folders) > 1:
        return ReviewLocation(group, label, filename, stage)
    return ReviewLocation(group, label, filename, stage, *_read_group_trace(result, group))


def _project_evidence(location: ReviewLocation, project: ProductionProject) -> tuple[set[str], str]:
    if (project.group.upper() != location.group
            or (location.title and project.name != location.title)
            or (location.episode and project.episode != location.episode)
            or (location.rules and project.rules != location.rules)):
        raise ValueError("所选项目的项目名、集次、组号或制作规则与该交付包不符。")
    current = {shot.id for shot in project.shots}
    pending = {shot.id for shot in project.pending_shots}
    recorded = {identity for _, identity in location.shot_ids}
    if recorded and not (current | pending) & recorded:
        raise ValueError("所选项目没有与交付包相符的镜头源 ID。请核对项目文件。")
    expected = dict(location.shot_ids).get(location.shot, "")
    return (current | pending) & recorded, expected if expected in current else ""


def resolve_repair_target(location: ReviewLocation, path: Path) -> RepairTarget:
    path = path.expanduser().resolve()
    if path.suffix.casefold() != ".cfproject" or not path.is_file():
        raise ValueError("请选择本组的 .cfproject 单组项目文件。")
    project = ProductionProject.open(path)
    _, target_shot = _project_evidence(location, project)
    filename = next((image.filename for image in project.images
                     if image.filename.casefold() == location.filename.casefold() and not image.reference_only), "")
    return RepairTarget(path, location.stage, target_shot, filename)


def _project_candidates(source_archive: Path | None, project_paths):
    paths = list(project_paths)
    if source_archive is not None:
        try:
            paths.extend(path for path in islice(Path(source_archive).parent.iterdir(), 128)
                         if path.suffix.casefold() == ".cfproject")
        except OSError:
            pass
    seen = set()
    for path in paths:
        if not path:
            continue
        try:
            candidate = Path(path).expanduser().resolve()
            if candidate not in seen and candidate.suffix.casefold() == ".cfproject" and candidate.is_file():
                seen.add(candidate)
                yield candidate
        except (OSError, RuntimeError):
            continue


def find_repair_project(location: ReviewLocation, *, source_archive: Path | None = None, project_paths=()) -> Path | None:
    """Automatic routing requires one local project with the complete archived production ledger."""
    if not location.shot_ids:
        return None
    candidates = []
    for path in _project_candidates(source_archive, project_paths):
        try:
            matched, _ = _project_evidence(location, ProductionProject.open(path))
        except (OSError, ValueError, AttributeError, TypeError):
            continue
        if len(matched) == len(location.shot_ids):
            candidates.append(path)
    return candidates[0] if len(candidates) == 1 else None


def open_review_repair(parent, result: ReviewResult, issue: ReviewIssue | None, *, source_archive: Path | None = None,
                       selected_member="", project_paths=(), open_production) -> bool:
    tr = lambda label: translate(parent, label)
    title = tr("回到制作返修")
    try:
        location = review_location(result, issue, selected_member)
        path = find_repair_project(location, source_archive=source_archive, project_paths=project_paths)
        if path is None:
            choice = filedialog.askopenfilename(
                parent=parent, title=tr("请选择 {group} 的单组项目").format(group=location.group),
                filetypes=((tr("单组制作项目"), "*.cfproject"),),
            )
            if not choice:
                return False
            path = Path(choice)
        target = resolve_repair_target(location, path)
        if not location.shot_ids and not messagebox.askyesno(
            title, tr("该 ZIP 缺少可核对的镜头源 ID。确认打开你选择的项目 {file}，并在项目内自行核对镜头？")
            .format(file=target.path.name), parent=parent,
        ):
            return False
        open_production(target.stage, target.path, shot_id=target.shot_id, asset_filename=target.asset_filename)
        return True
    except (OSError, ValueError, RuntimeError, AttributeError, TypeError) as exc:
        messagebox.showerror(title, tr(str(exc)), parent=parent)
        return False
