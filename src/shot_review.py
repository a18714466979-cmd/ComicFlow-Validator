"""Resolve approved shot and clean-plate references for side-by-side review."""

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath

from .storyboard_review import GROUP, PREVIEW_LIMIT, ReviewResult, read_preview


IMAGE_SUFFIXES = PREVIEW_LIMIT.keys() - {".txt"}
SHOT_HEADERS = {
    "production": re.compile(r"^分镜(?:[^\S\r\n]*[：:]|[^\S\r\n]+)[^\S\r\n]*([^\r\n]+)", re.MULTILINE),
    "sd2": re.compile(r"^分镜编号[^\S\r\n]*[：:][^\S\r\n]*([^\r\n]+)", re.MULTILINE),
}
PRODUCTION_FOOTER = re.compile(r"^(?:资产复用核对|场景资产模式|场景局部对应表|图像验收记录|资产清单)[ \t]*[：:]", re.MULTILINE)


@dataclass(frozen=True)
class PlateReference:
    filename: str
    slot: str
    scene: str
    description: str


@dataclass(frozen=True)
class ShotReview:
    group: str
    shot: str
    storyboard: str | None
    production: str
    sd2: str
    plate: PlateReference | None
    notices: tuple[str, ...]
    board_box: tuple[int, int, int, int] | None = None
    plate_box: tuple[int, int, int, int] | None = None


def shot_id(value: str, group: str) -> str:
    value = value.strip().upper()
    match = re.fullmatch(r"(?:(SB\d+)-)?(\d+)([A-Z]?)", value)
    if match:
        return f"{match[1] or group}-{int(match[2]):02d}{match[3]}"
    return value


def shot_sections(text: str, kind: str, group: str) -> dict[str, list[str]]:
    matches = list(SHOT_HEADERS[kind].finditer(text))
    sections = defaultdict(list)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if kind == "production" and (footer := PRODUCTION_FOOTER.search(text, match.end(), end)):
            end = footer.start()
        identity = shot_id(match[1], group)
        if identity:
            sections[identity].append(text[match.start():end].strip())
    return dict(sections)


def plate_references(text: str, group: str) -> dict[str, list[PlateReference]]:
    match = re.search(r"^场景局部对应表[ \t]*[：:][ \t]*.*$", text, re.MULTILINE)
    references = defaultdict(list)
    if match:
        for line in text[match.end():].splitlines():
            line = line.strip()
            if not line:
                continue
            if not line.startswith(("- ", "• ", "* ")):
                break
            values = [value.strip() for value in line[2:].split("|", 4)]
            if len(values) == 5 and all(values):
                identity, filename, slot, scene, description = values
                references[shot_id(identity, group)].append(PlateReference(filename, slot, scene, description))
    return dict(references)


def load_shots(result: ReviewResult) -> list[ShotReview]:
    grouped = defaultdict(list)
    for path in result.members:
        folder, _, name = path.partition("/")
        if GROUP.fullmatch(folder) and name and "/" not in name:
            grouped[folder].append(name)

    shots = []
    for folder in sorted(grouped, key=lambda item: (int(re.match(r"SB(\d+)", item, re.I)[1]), item)):
        group = folder.partition("_")[0].upper()
        files = grouped[folder]
        notices = []

        def find_one(names: list[str], label: str) -> str | None:
            if len(names) == 1:
                return f"{folder}/{names[0]}"
            notices.append(f"{label}缺失。" if not names else f"有多份{label}，请先核对版本。")
            return None

        def read_text(path: str | None, label: str) -> str:
            if path:
                try:
                    return read_preview(result, path).decode("utf-8-sig")
                except (OSError, ValueError) as exc:
                    notices.append(f"无法读取{label}：{exc}")
            return ""

        boards = [n for n in files if "storyboard" in n.lower()
                  and PurePosixPath(n).suffix.lower() in IMAGE_SUFFIXES]
        production = read_text(find_one([n for n in files if n.lower().endswith("_shot_details.txt")], "生产记录"), "生产记录")
        sd2 = read_text(find_one([n for n in files if n.lower() == "sd2_prompt.txt"], "SD2 提示词"), "SD2 提示词")
        source = shot_sections(production, "production", group)
        prompts = shot_sections(sd2, "sd2", group)
        plates = plate_references(production, group)
        windows = image_windows(production, group)
        for identity in dict.fromkeys([*source, *prompts]):
            warnings = list(notices)
            storyboard = f"{folder}/{boards[0]}" if len(boards) == 1 else None
            source_rows = source.get(identity, [])
            prompt_rows = prompts.get(identity, [])
            for rows, label in ((source_rows, "生产记录"), (prompt_rows, "SD2 提示词")):
                if len(rows) != 1:
                    warnings.append(f"{label}中该镜号{'有多条记录' if rows else '没有匹配记录'}。")
            bindings = plates.get(identity, [])
            plate = bindings[0] if len(bindings) == 1 else None
            if plate is None:
                warnings.append("该镜未找到唯一的净板对应关系。")
            elif plate.filename not in files or PurePosixPath(plate.filename).suffix.lower() not in IMAGE_SUFFIXES:
                warnings.append(f"净板文件未在本组图像中找到：{plate.filename}")
            board_box = plate_box = None
            matches = windows.get(identity, ())
            if len(matches) == 1:
                board, board_position, clean, plate_position = matches[0]
                if board in boards:
                    storyboard, board_box = f"{folder}/{board}", board_position
                if plate and plate.filename == clean and clean in files:
                    plate_box = plate_position
            if not storyboard:
                warnings.append("故事板缺失。" if not boards else "有多张故事板，请核对该镜的页码和窗口。")
            if "实际画面窗口：" in production and not board_box:
                warnings.append("该镜缺少与正式文件一致的窗口坐标。")
            shots.append(ShotReview(folder, identity, storyboard,
                                    source_rows[0] if len(source_rows) == 1 else "",
                                    prompt_rows[0] if len(prompt_rows) == 1 else "", plate, tuple(warnings),
                                    board_box, plate_box))
    return shots


def image_windows(text, group):
    match = re.search(r"^实际画面窗口[ \t]*[：:][ \t]*\r?$", text, re.MULTILINE)
    found = defaultdict(list)
    if not match:
        return found
    for row in text[match.end():].strip().splitlines():
        if not row.startswith("- "):
            break
        cells = [part.strip() for part in row[2:].split("|")]
        if len(cells) != 5:
            continue
        identity, board, a, clean, b = cells
        if not all(re.fullmatch(r"\d{1,8}(?:,\d{1,8}){3}", part) for part in (a, b)):
            continue
        boxes = [tuple(map(int, part.split(","))) for part in (a, b)]
        if all(x < right and y < bottom and (right - x) * 9 == (bottom - y) * 16 for x, y, right, bottom in boxes):
            found[shot_id(identity, group)].append((board, boxes[0], clean, boxes[1]))
    return found


def shot_summary(shot: ShotReview) -> str:
    for label in ("动作起止", "画面/事件", "动作", "景别"):
        match = re.search(rf"^{re.escape(label)}[ \t]*[：:][ \t]*(.+)$", shot.production or shot.sd2, re.MULTILINE)
        if match:
            return match[1].strip()
    return "镜头文字缺失或未找到动作说明。"


def pixel_selection(
    start: tuple[int, int], end: tuple[int, int], image_bounds: tuple[int, int, int, int],
    original_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    """Convert a rectangle on the fitted preview into original image coordinates."""
    left, top, width, height = image_bounds
    x1, x2 = sorted((start[0] - left, end[0] - left))
    y1, y2 = sorted((start[1] - top, end[1] - top))
    x1, x2 = max(0, x1), min(width, x2)
    y1, y2 = max(0, y1), min(height, y2)
    if x2 - x1 < 5 or y2 - y1 < 5:
        return None
    return (round(x1 * original_size[0] / width), round(y1 * original_size[1] / height),
            round(x2 * original_size[0] / width), round(y2 * original_size[1] / height))
