#!/usr/bin/env python3
"""Validate ecommerce reference-video storyboard delivery packages."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TEMPORARY_SUFFIXES = {".writing", ".tmp", ".part", ".download"}

FORBIDDEN_ENGLISH_HEADINGS = re.compile(
    r"^(GROUP|SOURCE RANGE|PANEL COUNT|FORMAT|CONTINUITY LOCK|PANEL|TIME|"
    r"SHOT SIZE|CAMERA ANGLE|CAMERA MOVEMENT|IMAGE / ACTION|"
    r"CHARACTER POSITIONS|DIALOGUE CN|DIALOGUE EN|SOUND|CONTINUITY|"
    r"MODEL CONSTRAINTS|ASSET MANIFEST|NEGATIVE / DO NOT)\s*:?",
    re.MULTILINE,
)

REQUIRED_CHINESE_FIELDS = (
    "分组", "覆盖段落", "格数", "画面格式", "故事板文件数", "连续性锁定", "分镜", "时间码",
    "景别", "机位/角度", "运镜", "画面/事件", "人物站位", "对白", "声音",
    "连续性", "视频模型约束", "人物资产核对", "资产清单", "产品资产",
)


def is_16_9(width: int, height: int, tolerance: float = 0.006) -> bool:
    return height > 0 and abs((width / height) - (16 / 9)) <= tolerance


def is_9_16(width: int, height: int, tolerance: float = 0.006) -> bool:
    return height > 0 and abs((width / height) - (9 / 16)) <= tolerance


def looks_grayscale(image: Image.Image, tolerance: float = 1.5) -> bool:
    red, green, blue = image.convert("RGB").split()
    pairs = ((red, green), (red, blue), (green, blue))
    return all(ImageStat.Stat(ImageChops.difference(left, right)).mean[0] <= tolerance for left, right in pairs)


def validate(root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not root.is_dir():
        return [f"Not a directory: {root}"], warnings

    groups = sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith("SB"))
    if not groups:
        errors.append("No SBxx_* group directories found")
    if not (root / "README.txt").is_file():
        warnings.append("Top-level README.txt is missing")

    for path in root.rglob("*"):
        if path.is_file() and (
            path.suffix.lower() in TEMPORARY_SUFFIXES or path.name.startswith(".~")
        ):
            errors.append(
                f"Temporary or unfinished file must not be packaged: {path.relative_to(root)}"
            )

    for group in groups:
        images = sorted(path for path in group.iterdir() if path.suffix.lower() in IMAGE_EXTENSIONS)
        txt_files = sorted(group.glob("*.txt"))
        storyboards = [path for path in images if "storyboard" in path.name.lower()]
        characters = [path for path in images if "character" in path.name.lower() or "kyle" in path.name.lower()]
        products = [path for path in images if "product" in path.name.lower()]

        if not storyboards:
            errors.append(f"{group.name}: composite storyboard sheet is missing")
        elif len(storyboards) != 1:
            errors.append(
                f"{group.name}: found {len(storyboards)} storyboard images; "
                "all panels must be combined into exactly one 9:16 storyboard sheet"
            )
        elif "sheet" not in storyboards[0].name.lower():
            errors.append(
                f"{group.name}/{storyboards[0].name}: composite storyboard filename "
                "must include 'sheet'"
            )
        if not txt_files:
            errors.append(f"{group.name}: per-group TXT is missing")

        for path in images:
            try:
                with Image.open(path) as image:
                    width, height = image.size
                    if path in storyboards:
                        if not is_9_16(width, height):
                            errors.append(
                                f"{group.name}/{path.name}: {width}x{height} is not 9:16"
                            )
                        if width < 1080 or height < 1920:
                            errors.append(
                                f"{group.name}/{path.name}: storyboard must be at least 1080x1920"
                            )
                        if looks_grayscale(image):
                            errors.append(
                                f"{group.name}/{path.name}: storyboard must be full color"
                            )
                    elif not is_16_9(width, height):
                        errors.append(
                            f"{group.name}/{path.name}: asset image {width}x{height} is not 16:9"
                        )
                    # Force full pixel decoding so truncated PNG/JPEG data is
                    # rejected instead of passing on header dimensions alone.
                    image.load()
            except Exception as exc:
                errors.append(f"{group.name}/{path.name}: unreadable image ({exc})")

        for path in characters:
            try:
                with Image.open(path) as image:
                    if not is_16_9(*image.size):
                        errors.append(f"{group.name}/{path.name}: character sheet must be 16:9")
            except Exception:
                pass

        combined_character_files = [
            path for path in characters
            if "other_characters" in path.name.lower()
            or "combined_characters" in path.name.lower()
        ]
        for path in combined_character_files:
            errors.append(
                f"{group.name}/{path.name}: use one separate turnaround image per character"
            )

        for path in txt_files:
            content = path.read_text(encoding="utf-8-sig", errors="replace")
            english_heading = FORBIDDEN_ENGLISH_HEADINGS.search(content)
            if english_heading:
                errors.append(
                    f"{group.name}/{path.name}: English production heading is not allowed "
                    f"({english_heading.group(1)})"
                )
            if re.search(r"^\s*(?:中文对白|英文对白)\s*[：:]", content, flags=re.MULTILINE):
                errors.append(
                    f"{group.name}/{path.name}: use one 对白 field and preserve the source language"
                )
            for field in REQUIRED_CHINESE_FIELDS:
                if field not in content:
                    errors.append(f"{group.name}/{path.name}: missing Chinese field {field}")

            declared_match = re.search(r"格数\s*[：:]\s*(\d+)", content)
            storyboard_file_match = re.search(
                r"故事板文件数\s*[：:]\s*(\d+)", content
            )
            if storyboard_file_match and int(storyboard_file_match.group(1)) != 1:
                errors.append(
                    f"{group.name}/{path.name}: 故事板文件数 must be 1"
                )
            panel_count = len(re.findall(r"^分镜(?:\s|[：:])", content, flags=re.MULTILINE))
            if declared_match and int(declared_match.group(1)) != panel_count:
                errors.append(
                    f"{group.name}/{path.name}: declared {declared_match.group(1)} panels "
                    f"but found {panel_count} panel records"
                )
            if len(storyboards) == 1:
                filename_panel_match = re.search(
                    r"(\d+)panel", storyboards[0].name, flags=re.IGNORECASE
                )
                if not filename_panel_match:
                    errors.append(
                        f"{group.name}/{storyboards[0].name}: storyboard sheet filename "
                        "must declare the combined panel count, such as 6panel"
                    )
                elif int(filename_panel_match.group(1)) != panel_count:
                    errors.append(
                        f"{group.name}/{storyboards[0].name}: filename declares "
                        f"{filename_panel_match.group(1)} panels but TXT contains {panel_count}"
                    )
            if panel_count > 10:
                errors.append(
                    f"{group.name}/{path.name}: {panel_count} panels exceed the 10-panel maximum"
                )

            dialogue_values = re.findall(
                r"^对白\s*[：:]\s*(.+?)\s*$", content, flags=re.MULTILINE
            )
            has_dialogue = any(
                value not in {"无", "None", "NONE"} for value in dialogue_values
            )
            if has_dialogue and panel_count > 6:
                errors.append(
                    f"{group.name}/{path.name}: dialogue group has {panel_count} panels; maximum is 6"
                )

            product_match = re.search(
                r"^\s*-?\s*产品资产\s*[：:]\s*(.*?)\s*$",
                content,
                flags=re.MULTILINE,
            )
            if product_match:
                product_value = product_match.group(1).strip()
                has_product = product_value not in {"无", "None", "NONE", "无。"}
                if has_product and len(products) != 1:
                    errors.append(
                        f"{group.name}: TXT declares product assets but found {len(products)} "
                        "product images; provide exactly one standalone combined 16:9 product sheet"
                    )
                if not has_product and products:
                    errors.append(
                        f"{group.name}: TXT declares 产品资产：无 but product image files are present"
                    )
    return errors, warnings


def validate_zip(zip_path: Path) -> list[str]:
    if not zip_path.is_file():
        return [f"ZIP not found: {zip_path}"]
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                member = Path(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    return [f"ZIP contains unsafe path: {info.filename}"]
                if (
                    member.suffix.lower() in TEMPORARY_SUFFIXES
                    or member.name.startswith(".~")
                ):
                    return [
                        f"ZIP contains temporary or unfinished file: {info.filename}"
                    ]
            bad_member = archive.testzip()
            return [f"ZIP contains a corrupt member: {bad_member}"] if bad_member else []
    except zipfile.BadZipFile:
        return [f"Invalid ZIP file: {zip_path}"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("delivery", type=Path, help="Top-level delivery directory")
    parser.add_argument("--zip", dest="zip_path", type=Path, help="Optional ZIP to test")
    args = parser.parse_args()

    errors, warnings = validate(args.delivery.resolve())
    if args.zip_path:
        errors.extend(validate_zip(args.zip_path.resolve()))
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"RESULT: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
