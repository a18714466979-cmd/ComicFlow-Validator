#!/usr/bin/env python3
"""Validate structural and basic visual constraints for AI-drama storyboard packages.

This validator is for complete SD2 packages only. It checks new continuity fields structurally, but does not pretend to verify physical reachability, visibility, contact anatomy, or source-dialogue completeness. Partial deliverables require manual scope-specific review.
Manual review is still mandatory for protagonist selection, complete turnaround coverage, crowd-face diversity, shot-scale rhythm, emotional performance, pursuit escalation, tactical blocking, exact singleton counts, weapon-line safety, three-unit composite layout, combat-wide roster completeness, adjacent-group handoffs, coherent character-sheet layout, Chinese visible labels, scene identity, genuine non-mirrored reverse views, storyboard-matched clean scene-detail plates, one-information-unit-per-storyboard-panel, whether formal main/reverse scene files are single full-frame views rather than collages/boards, and whether an image was improperly derived from a master/overview board.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageStat

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TEMPORARY_SUFFIXES = {".writing", ".tmp", ".part", ".download"}
PLACEHOLDER_TOKENS = ("placeholder", "empty", "blank", "none_asset", "no_character")

FORBIDDEN_ENGLISH_HEADINGS = re.compile(
    r"^(GROUP|SOURCE RANGE|PANEL COUNT|FORMAT|CONTINUITY LOCK|PANEL|TIME|"
    r"SHOT SIZE|CAMERA ANGLE|CAMERA MOVEMENT|IMAGE / ACTION|"
    r"CHARACTER POSITIONS|DIALOGUE CN|DIALOGUE EN|SOUND|CONTINUITY|"
    r"MODEL CONSTRAINTS|ASSET MANIFEST|NEGATIVE / DO NOT)\s*:?",
    re.MULTILINE,
)

REQUIRED_CHINESE_FIELDS = (
    "分组", "覆盖段落", "视频任务时长", "对白规格", "格数", "画面格式", "本组进入状态", "本组退出状态", "连续性锁定", "分镜", "时间码",
    "景别", "机位/角度", "运镜", "画面/事件", "人物站位", "唯一角色数量锁定", "对白", "声音",
    "连续性", "视频模型约束", "视频上色约束", "视频文字约束", "主角判定", "武器轴线核对", "镜头节奏核对",
    "空间合理性核对", "群像差异化核对", "追击节奏核对", "本格新增叙事功能", "情绪/表演", "环境威胁/视觉副线",
    "机位空间", "可见范围", "动作起止", "声源位置", "对白保全核对",
    "场景局部对应表", "人物资产核对", "人物资产分表", "其他人物合集", "资产清单",
)

SCENE_RE = re.compile(
    r"^(?P<prefix>\d+_)?scene_(?P<scene>.+?)_(?P<kind>main|reverse|details)_16x9$",
    re.IGNORECASE,
)
COMPACT_SCENE_RE = re.compile(
    r"^(?:\d+_)?scene_多场景局部_details_(0[1-3])_16x9$",
    re.IGNORECASE,
)
PACKED_SCENE_RE = re.compile(r"^(?:\d+_)?scene_九图合并_(\d{2})_16x9$", re.IGNORECASE)


def is_16_9(width: int, height: int, tolerance: float = 0.006) -> bool:
    return height > 0 and abs((width / height) - (16 / 9)) <= tolerance


def pixel_channel_spread(image: Image.Image) -> float:
    """Mean per-pixel max(R,G,B)-min(R,G,B), not differences of channel means."""
    import numpy as np
    pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
    return float((pixels.max(axis=2) - pixels.min(axis=2)).mean())


def split_dialogue_records(value: str) -> list[str]:
    """Split record delimiters only outside quoted spoken text."""
    result, buf, closing = [], [], None
    pairs = {"“": "”", '"': '"', "「": "」", "『": "』"}
    for char in value:
        if closing is not None:
            buf.append(char)
            if char == closing:
                closing = None
        elif char in pairs:
            closing = pairs[char]
            buf.append(char)
        elif char in "；;":
            if "".join(buf).strip():
                result.append("".join(buf).strip())
            buf = []
        else:
            buf.append(char)
    if "".join(buf).strip():
        result.append("".join(buf).strip())
    return result


def read_field_block(content: str, field: str) -> str | None:
    """Read inline or list-style content up to the next heading/field."""
    match = re.search(rf"^{re.escape(field)}[^\S\r\n]*[：:][^\S\r\n]*(.*)$", content, re.MULTILINE)
    if not match:
        return None
    parts = [match.group(1).strip()]
    for line in content[match.end():].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^(?:[-*•]|\d+[.、])\s*", stripped):
            parts.append(stripped)
        else:
            break
    return "\n".join(part for part in parts if part).strip()


def looks_grayscale(image: Image.Image, tolerance: float = 1.5) -> bool:
    return pixel_channel_spread(image) <= tolerance


def storyboard_color_fraction(image: Image.Image) -> float:
    """Sparse color can be motion annotations; their meaning still needs visual review."""
    import numpy as np
    pixels = np.asarray(image.convert("RGB"), dtype=np.int16)
    return float(((pixels.max(axis=2) - pixels.min(axis=2)) > 24).mean())


def budget_record_errors(content: str, stage: str, final_count: int | None = None) -> list[str]:
    """Check recorded escalation, not the visual feasibility/truth of each packing step."""
    record = read_field_block(content, "九图优化记录") or ""
    original = re.search(r"原始总图数\s*[：:=＝]\s*(\d+)", record)
    final = re.search(r"最终总图数\s*[：:=＝]\s*(\d+)", record)
    required = ["道具", "配角", "主角"]
    if stage in ("scene", "storyboard"):
        required.append("主配")
    if stage == "storyboard":
        required.append("场景")
    errors = []
    if not original or int(original.group(1)) <= 9 or any(term not in record for term in required):
        errors.append(f"{stage} consolidation requires 九图优化记录 with 原始总图数>9 and preceding stages: {'、'.join(required)}")
    if not final or not 1 <= int(final.group(1)) <= 9:
        errors.append("九图优化记录 requires 最终总图数 between 1 and 9")
    elif final_count is not None and int(final.group(1)) != final_count:
        errors.append("九图优化记录 最终总图数 does not match delivered image count")
    return errors


def cell_layout_errors(content: str, required: dict[str, tuple[tuple[int, int], int | None]]) -> list[str]:
    """Validate declared picture rectangles; a human must compare them to actual pixels."""
    mapping = read_field_block(content, "图格布局") or ""
    if not mapping:
        return ["requires 图格布局 for every storyboard and local/packed scene image"]
    errors, bound = [], []
    for line in mapping.splitlines():
        match = re.fullmatch(r"[-*•]?\s*([^：:]+)[：:]\s*(.+)", line.strip())
        if not match:
            errors.append("图格布局 requires '- filename.png：x,y,width,height；...' pixel rectangles")
            continue
        filename, value = match.group(1).strip(), match.group(2)
        bound.append(filename)
        if filename not in required:
            errors.append(f"图格布局 names an unexpected or missing image: {filename}")
            continue
        (width, height), count = required[filename]
        rectangles = []
        for raw in re.split(r"[；;]", value):
            if not re.fullmatch(r"\s*\d+\s*[,，]\s*\d+\s*[,，]\s*\d+\s*[,，]\s*\d+\s*", raw):
                errors.append(f"{filename}: invalid 图格布局 rectangle: {raw}")
                continue
            x, y, w, h = map(int, re.split(r"\s*[,，]\s*", raw.strip()))
            if not is_16_9(w, h):
                errors.append(f"{filename}: individual picture cell {w}x{h} is not 16:9")
            if w <= 0 or h <= 0 or x + w > width or y + h > height:
                errors.append(f"{filename}: picture cell is empty or outside the image canvas")
            for px, py, pw, ph in rectangles:
                if min(x + w, px + pw) > max(x, px) and min(y + h, py + ph) > max(y, py):
                    errors.append(f"{filename}: picture cells overlap")
            rectangles.append((x, y, w, h))
        if count is not None and len(rectangles) != count:
            errors.append(f"{filename}: 图格布局 has {len(rectangles)} cells but filename declares {count} panels")
    if set(bound) != set(required) or len(bound) != len(set(bound)):
        errors.append("图格布局 must cover every storyboard and local/packed scene image exactly once")
    return errors


def scene_colorfulness(image: Image.Image) -> float:
    """Simple Hasler-Susstrunk style colorfulness estimate."""
    rgb = image.convert("RGB")
    import numpy as np
    arr = np.asarray(rgb, dtype=float)
    rg = arr[..., 0] - arr[..., 1]
    yb = 0.5 * (arr[..., 0] + arr[..., 1]) - arr[..., 2]
    std_root = (rg.std() ** 2 + yb.std() ** 2) ** 0.5
    mean_root = (rg.mean() ** 2 + yb.mean() ** 2) ** 0.5
    return float(std_root + 0.3 * mean_root)


def image_entropy(image: Image.Image) -> float:
    return image.convert("L").entropy()


def dynamic_range(image: Image.Image) -> float:
    gray = image.convert("L")
    extrema = gray.getextrema()
    return float(extrema[1] - extrema[0])


def mostly_blank_or_placeholder(image: Image.Image) -> bool:
    return image_entropy(image) < 1.0 and dynamic_range(image) < 35


def has_affirmative_hud(value: str) -> bool:
    """Check structured visual/asset records, keeping negation local to UI use."""
    term = r"(?:HUD|界面|\binterface\b)"
    for clause in re.split(r"[；;，,。\n]|但是|然而|但", value):
        for match in re.finditer(term, clause, re.IGNORECASE):
            before, after = clause[:match.start()], clause[match.end():]
            negation = r"(?:没有|不含|未包含|不涉及|不出现|不显示|未显示|未出现|无需|不需要|禁止(?:出现|显示)?|不得(?:出现|显示)?|无须|无)"
            modifiers = r"(?:任何|其他|可见的?|额外的?|可用的?|本组的?)?"
            # Only UI objects/connectors may intervene; '没有人物遮挡HUD' is affirmative.
            if re.search(negation + r"\s*" + modifiers + r"\s*(?:" + term + r"|或|和|及|与|等|、|\s)*$", before, re.IGNORECASE):
                continue
            if re.match(r"\s*[：:]\s*(?:无|没有|none|absent)\s*$", after, re.IGNORECASE):
                continue
            if re.match(r"\s*(?:不存在|没有显示|没有出现|未显示|未出现|不显示|不在画面|不入画)(?:\s|$)", after):
                continue
            if re.search(r"\b(?:no|without|never|not)\s+(?:visible\s+|any\s+)?$", before, re.IGNORECASE):
                continue
            return True
    return False


def has_recorded_hud_coverage(manifest: str, prop_files: list[Path]) -> bool:
    """Require a declared delivered prop-sheet binding, not an unfulfilled HUD note."""
    for record in re.split(r"[；;\n]", manifest):
        if not has_affirmative_hud(record):
            continue
        if re.search(r"待补|未交付|缺失|待生成|尚未|需要补|\b(?:missing|pending|todo)\b", record, re.IGNORECASE):
            continue
        if any(asset.name in record or asset.stem in record for asset in prop_files):
            return True
        if re.search(r"道具(?:合集|资产|图)|\bprops\b", record, re.IGNORECASE):
            return True
    return False


def inline_field(content: str, field: str) -> str | None:
    match = re.search(rf"^{re.escape(field)}[^\S\r\n]*[：:][^\S\r\n]*(.*)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None


def protagonist_coverage_errors(content: str, files: list[Path], *, legacy: bool) -> list[str]:
    """Check declared identities and file bindings; image content still needs review."""
    roster_value = inline_field(content, "主角清单")
    mapping_value = read_field_block(content, "主角资产映射")
    if legacy and roster_value is None and mapping_value is None:
        return []
    errors = []
    if not roster_value:
        errors.append("requires non-empty 主角清单")
    if not mapping_value:
        errors.append("requires non-empty 主角资产映射")
    if errors:
        return errors
    roster = [] if roster_value == "无" else [n.strip() for n in re.split(r"[；;、，,]", roster_value) if n.strip()]
    if len(roster) != len(set(roster)):
        errors.append("主角清单 contains duplicate identities")
    if any(not re.search(r"[\u3400-\u9fff]", name) for name in roster):
        errors.append("主角清单 must use canonical Chinese identity names")
    protagonist_files = {
        p.name: p for p in files
        if any(token in p.name.lower() for token in ("protagonist", "main_character", "主角"))
    }
    if not roster:
        if mapping_value != "无" or protagonist_files:
            errors.append("主角清单：无 requires 主角资产映射：无 and no protagonist assets")
        verdict = inline_field(content, "主角判定") or ""
        if not any(token in verdict for token in ("无角色型实体", "无人物或角色型实体", "纯场景")):
            errors.append("主角清单：无 requires a no-character exception in 主角判定")
        return errors
    covered, bound, sizes = [], [], []
    for line in mapping_value.splitlines():
        record = re.sub(r"^[-*•]\s*", "", line.strip())
        match = re.fullmatch(r"([^：:]+)[：:]\s*(.+)", record)
        if not match:
            errors.append("主角资产映射 must use '- exact_filename.png：姓名；姓名'")
            continue
        filename = match.group(1).strip()
        names = [n.strip() for n in re.split(r"[；;、，,]", match.group(2)) if n.strip()]
        bound.append(filename)
        covered.extend(names)
        sizes.append(len(names))
        if filename not in protagonist_files:
            errors.append(f"主角资产映射 file is missing or is not a protagonist asset: {filename}")
        if "protagonist_with_support" in filename.lower():
            if len(names) != 1:
                errors.append(f"mixed sheet must bind exactly one protagonist in 主角资产映射: {filename}")
        elif "main_characters" in filename.lower():
            if len(names) != 2:
                errors.append(f"main_characters must cover exactly two protagonists: {filename}")
        elif "protagonist" in filename.lower():
            if len(names) != 1:
                errors.append(f"independent protagonist sheet must cover one identity: {filename}")
        else:
            errors.append(f"主角资产映射 requires protagonist or main_characters naming: {filename}")
    if len(bound) != len(set(bound)):
        errors.append("主角资产映射 repeats a file")
    if set(bound) != set(protagonist_files):
        errors.append("主角资产映射 must bind every delivered protagonist file exactly once")
    if sorted(covered) != sorted(roster):
        errors.append("主角资产映射 must cover every 主角清单 identity exactly once without extras")
    mixed_files = {name for name in protagonist_files if "protagonist_with_support" in name.lower()}
    mixed_mapping = read_field_block(content, "混合人物资产映射") or "无"
    mixed_bound, supports = [], []
    if mixed_files:
        errors.extend(budget_record_errors(content, "mixed"))
    if mixed_mapping != "无":
        for line in mixed_mapping.splitlines():
            record = re.sub(r"^[-*•]\s*", "", line.strip())
            match = re.fullmatch(r"([^：:]+)[：:]\s*(.+)", record)
            if not match:
                errors.append("混合人物资产映射 requires '- exact_filename.png：主角姓名；配角姓名'")
                continue
            filename = match.group(1).strip()
            names = [n.strip() for n in re.split(r"[；;、，,]", match.group(2)) if n.strip()]
            mixed_bound.append(filename)
            primary = re.search(rf"^[-*•]?\s*{re.escape(filename)}[：:]\s*(.+)$", mapping_value, re.MULTILINE)
            if (filename not in mixed_files or len(names) != 2 or names[0] not in roster
                    or names[1] in roster or not primary or primary.group(1).strip() != names[0]):
                errors.append(f"mixed sheet requires exactly one mapped protagonist then one distinct supporting identity: {filename}")
            elif not re.search(r"[\u3400-\u9fff]", names[1]):
                errors.append("mixed supporting identity must use its canonical Chinese name")
            else:
                supports.append(names[1])
                boundary_name = rf"(?:^|[_与及和、；]){re.escape(names[1])}(?:$|[_与及和、；])"
                if any(re.search(boundary_name, p.stem) for p in files if "other_characters" in p.name.lower()):
                    errors.append(f"mixed supporting identity is duplicated in other_characters: {names[1]}")
    if set(mixed_bound) != mixed_files or len(mixed_bound) != len(set(mixed_bound)):
        errors.append("混合人物资产映射 must bind every mixed sheet exactly once without extras")
    if len(supports) != len(set(supports)):
        errors.append("mixed supporting identities must not be duplicated across sheets")
    return errors


def shot_records(content: str, *, sd2: bool, group_id: str) -> list[tuple[str, str]]:
    pattern = (r"^分镜编号[^\S\r\n]*[：:][^\S\r\n]*([^\r\n]*)" if sd2 else
               r"^分镜(?:[^\S\r\n]*[：:][^\S\r\n]*|[^\S\r\n]+)([^\r\n]*)")
    matches = list(re.finditer(pattern, content, re.MULTILINE))
    result = []
    for index, match in enumerate(matches):
        identity = match.group(1).strip()
        if re.fullmatch(r"\d+[A-Za-z]?", identity):
            identity = f"{group_id}-{identity}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        result.append((identity, content[match.end():end]))
    return result


def normalized_dialogue(value: str | None) -> list[tuple[str, str]]:
    if not value or value in {"无", "None", "NONE"}:
        return []
    result = []
    for record in split_dialogue_records(value):
        parts = re.split(r"[：:]", record, maxsplit=1)
        if len(parts) != 2:
            result.append(("", record.strip()))
            continue
        speaker, spoken = parts[0].strip(), parts[1].strip()
        for opening, closing in (("“", "”"), ('"', '"'), ("「", "」"), ("『", "』")):
            if spoken.startswith(opening) and spoken.endswith(closing):
                spoken = spoken[1:-1]
                break
        result.append((speaker, re.sub(r"\s+", " ", spoken).strip()))
    return result


def count_audible_characters(values: list[str]) -> int:
    """Count spoken fragments, excluding speakers, IDs, punctuation and whitespace.

    Continuations contribute only their actually written fragment. Do not dedupe
    matching text: an explicitly repeated utterance consumes speaking time too.
    """
    return sum(
        len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff0-9A-Za-z]", spoken))
        for value in values
        for _, spoken in normalized_dialogue(value)
    )


def dialogue_panel_target(character_count: int, dialogue_spec: str, allow_legacy: bool = False) -> int | None:
    """Historical four-panel override is available only for explicit legacy checks."""
    if allow_legacy and character_count > 100:
        return 4
    if dialogue_spec in {"1-2句短对白", "1—2句短对白", "1–2句短对白"}:
        return 8
    if dialogue_spec in {"三句以上或长对白", "3句以上或长对白"}:
        return 6
    return None


def normalized_quantity(value: str | None) -> list[str]:
    # Compare declared values, allowing whitespace and delimiter formatting only.
    cleaned = re.sub(r"\s+", "", value or "")
    cleaned = re.sub(r"[xX](?=\d)", "×", cleaned)
    return sorted(part for part in re.split(r"[；;、，,]", cleaned) if part)


def cross_file_errors(production: str, sd2: str, group_id: str) -> list[str]:
    errors = []
    source = shot_records(production, sd2=False, group_id=group_id)
    prompts = shot_records(sd2, sd2=True, group_id=group_id)
    for label, records in (("production TXT", source), ("SD2 prompt", prompts)):
        ids = [identity for identity, _ in records]
        if any(not identity for identity in ids) or len(ids) != len(set(ids)):
            errors.append(f"{label} requires non-empty unique shot IDs")
    if [i for i, _ in source] != [i for i, _ in prompts]:
        errors.append("SD2 shot IDs/order must match the production TXT")
    for (source_id, record), (prompt_id, prompt) in zip(source, prompts):
        if normalized_dialogue(inline_field(record, "对白")) != normalized_dialogue(inline_field(prompt, "对白")):
            errors.append(f"shot {source_id}: SD2 dialogue/speaker differs from production TXT")
        if normalized_quantity(inline_field(record, "唯一角色数量锁定")) != normalized_quantity(inline_field(prompt, "人物数量限制")):
            errors.append(f"shot {source_id}: SD2 quantity lock differs from production TXT")
    return errors


def sd2_global_constraint_errors(sd2: str) -> list[str]:
    errors = []
    prefix = re.split(r"^分镜编号[^\S\r\n]*[：:]", sd2, maxsplit=1, flags=re.MULTILINE)[0]
    for field in ("视频上色约束", "视频文字约束"):
        occurrences = re.findall(rf"^{field}[^\S\r\n]*[：:]", sd2, re.MULTILINE)
        value = inline_field(prefix, field) or ""
        if len(occurrences) != 1 or not value:
            errors.append(f"SD2 prompt requires {field} exactly once before the shots")
        elif field == "视频上色约束":
            if not ("彩色" in value and re.search(r"(?:禁止|不得|不允许|不出现|不含)[^。\n]*黑白", value)):
                errors.append("SD2 视频上色约束 must require color assets and forbid black-and-white final frames")
        elif re.search(r"(?:禁止|不得|不允许|不出现|不含)[^。\n;；]*中文|(?:只|仅)允许英文", value):
            errors.append("SD2 视频文字约束 must allow Chinese final-video text")
    return errors


def validate(root: Path, *, allow_legacy: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        return [f"Not a directory: {root}"], warnings

    groups = sorted(
        path for path in root.iterdir()
        if path.is_dir() and path.name.startswith("SB")
    )
    if not groups:
        errors.append("No SBxx_* group directories found")

    if not (root / "README.txt").is_file():
        warnings.append("Top-level README.txt is missing")

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if path.suffix.lower() in TEMPORARY_SUFFIXES or path.name.startswith(".~"):
            errors.append(
                f"Temporary or unfinished file must not be packaged: {path.relative_to(root)}"
            )
        if any(token in lower for token in PLACEHOLDER_TOKENS):
            errors.append(
                f"Placeholder-style filename is forbidden: {path.relative_to(root)}"
            )

    for group in groups:
        images = sorted(
            path for path in group.iterdir()
            if path.suffix.lower() in IMAGE_EXTENSIONS
        )
        txt_files = sorted(group.glob("*.txt"))
        sd2_prompt_files = [p for p in txt_files if p.name.lower() == "sd2_prompt.txt"]
        production_txt_files = [p for p in txt_files if p.name.lower() != "sd2_prompt.txt"]
        storyboards = [p for p in images if "storyboard" in p.name.lower()]
        scene_files = [p for p in images if "_scene_" in p.name.lower() or p.name.lower().startswith("scene_")]
        hud_files = [
            p for p in images
            if any(token in p.name.lower() for token in ("hud", "interface_overlay"))
            and "storyboard" not in p.name.lower()
        ]
        prop_files = [
            p for p in images
            if any(token in p.name.lower() for token in ("props", "hud", "interface_overlay"))
            and "storyboard" not in p.name.lower()
        ]
        character_files = [
            p for p in images
            if any(token in p.name.lower() for token in (
                "character", "protagonist", "main_character", "kyle", "vera", "zoe",
                "oren", "niko", "marlowe", "adapt", "resident", "guard", "miner",
                "worker", "follower", "creature", "monster", "人物", "主角", "角色", "怪物"
            ))
            and p not in storyboards + scene_files + prop_files
        ]

        if len(images) > 9:
            errors.append(
                f"{group.name}: {len(images)} final upload images exceed the nine-image limit; "
                "consolidate props, supporting characters, protagonists, permitted 1+1 mixed sheets, scenes, then storyboards; split only if no readable packing works"
            )

        # Final delivery convention: protagonist status comes from the current arc,
        # not a hard-coded character pair. Every other character-like asset belongs
        # in numbered other_characters sheets. Manual review verifies turnaround depth.
        allowed_character_tokens = (
            "protagonist", "main_character", "main_characters", "other_characters",
            "主角", "其他人物",
        )
        for path in character_files:
            lower_name = path.name.lower()
            if not any(token in lower_name for token in allowed_character_tokens):
                errors.append(
                    f"{group.name}/{path.name}: character asset must use a protagonist/main_characters "
                    "or numbered other_characters_XX filename with a Chinese semantic identity name"
                )

        formal_assets = list(dict.fromkeys(character_files + prop_files + scene_files))
        for path in formal_assets:
            if not re.search(r"[\u3400-\u9fff]", path.stem):
                errors.append(
                    f"{group.name}/{path.name}: formal asset filename must include its canonical Chinese semantic name"
                )

        if not storyboards:
            errors.append(f"{group.name}: storyboard image is missing")
        if not production_txt_files:
            errors.append(f"{group.name}: authoritative production TXT is missing")
        if len(production_txt_files) > 1:
            errors.append(f"{group.name}: multiple production TXT files found; keep one authoritative <group>_shot_details.txt")
        if not sd2_prompt_files:
            errors.append(f"{group.name}: SD2_prompt.txt is missing")
        if len(sd2_prompt_files) > 1:
            errors.append(f"{group.name}: multiple SD2_prompt.txt files found")
        if not scene_files:
            errors.append(f"{group.name}: no formal scene assets found")

        for path in hud_files:
            if "props" not in path.name.lower():
                errors.append(
                    f"{group.name}/{path.name}: HUD/UI belongs to the prop-asset category; "
                    "use a props or props_hud filename and count it with the group's props"
                )

        group_text = production_txt_files[0].read_text(encoding="utf-8-sig", errors="replace") if production_txt_files else ""
        errors.extend(f"{group.name}: {error}" for error in protagonist_coverage_errors(group_text, character_files, legacy=allow_legacy))
        if any("protagonist_with_support" in p.name.lower() for p in character_files):
            errors.extend(f"{group.name}: {e}" for e in budget_record_errors(group_text, "mixed", len(images)))
        compact_mode = bool(re.search(r"^场景资产模式\s*[：:]\s*多场景局部\s*$", group_text, re.MULTILINE))
        packed_mode = inline_field(group_text, "场景资产模式") == "九图合并"
        if packed_mode:
            errors.extend(f"{group.name}: {e}" for e in budget_record_errors(group_text, "scene", len(images)))
            scenes = [s.strip() for s in re.split(r"[；;、,，]", inline_field(group_text, "场景清单") or "") if s.strip()]
            if not scenes or len(scenes) != len(set(scenes)):
                errors.append(f"{group.name}: packed scene mode requires distinct 场景清单 entries")
            numbers = []
            for asset in scene_files:
                match = PACKED_SCENE_RE.fullmatch(asset.stem)
                if not match:
                    errors.append(f"{group.name}/{asset.name}: packed mode requires scene_九图合并_XX_16x9 naming")
                else:
                    numbers.append(int(match.group(1)))
            if sorted(numbers) != list(range(1, len(scene_files) + 1)):
                errors.append(f"{group.name}: packed scene numbers must begin at 01 and be consecutive")
            source = inline_field(group_text, "场景合并来源") or "常规"
            if source not in ("常规", "多场景局部") or source == "多场景局部" and len(scenes) < 2:
                errors.append(f"{group.name}: packed scene source must be 常规 or 多场景局部 with at least two scenes")
            mapping = read_field_block(group_text, "场景视图映射") or ""
            layout_records = {}
            for line in (read_field_block(group_text, "图格布局") or "").splitlines():
                match = re.fullmatch(r"[-*•]?\s*([^：:]+)[：:]\s*(.+)", line.strip())
                if match:
                    layout_records[match.group(1).strip()] = re.split(r"[；;]", match.group(2))
            bound, views = [], defaultdict(set)
            for line in mapping.splitlines():
                record = re.sub(r"^[-*•]\s*", "", line.strip())
                match = re.fullmatch(r"([^：:]+)[：:]\s*(.+)", record)
                if not match:
                    errors.append(f"{group.name}: 场景视图映射 requires '- filename.png：场景/main；场景/reverse；场景/details'")
                    continue
                filename, value = match.groups()
                bound.append(filename.strip())
                view_items = re.split(r"[；;]", value)
                if len(view_items) != len(layout_records.get(filename.strip(), [])):
                    errors.append(f"{group.name}/{filename}: 场景视图映射 items must correspond one-to-one to 图格布局 rectangles in reading order")
                for item in view_items:
                    parts = item.strip().rsplit("/", 1)
                    if len(parts) != 2 or parts[0] not in scenes or parts[1] not in ("main", "reverse", "details"):
                        errors.append(f"{group.name}: invalid packed scene view mapping: {item}")
                    else:
                        views[parts[0]].add(parts[1])
            if set(bound) != {p.name for p in scene_files} or len(bound) != len(set(bound)):
                errors.append(f"{group.name}: 场景视图映射 must bind every scene file exactly once")
            needed = {"details"} if source == "多场景局部" else {"main", "reverse", "details"}
            if any(not needed <= views[name] for name in scenes):
                errors.append(f"{group.name}: packed scene mapping omits required scene views")
        elif compact_mode:
            scenes_match = re.search(r"^场景清单\s*[：:]\s*(.*?)\s*$", group_text, re.MULTILINE)
            scene_names = [s.strip() for s in re.split(r"[；;、,，]", scenes_match.group(1)) if s.strip()] if scenes_match else []
            if len(scene_names) < 2 or len(set(scene_names)) < 2:
                errors.append(f"{group.name}: compact scene mode requires at least two distinct scenes in 场景清单")
            mapping_match = re.search(
                r"^场景局部对应表\s*[：:].*?(?=^资产清单|^禁止事项|\Z)",
                group_text, re.MULTILINE | re.DOTALL,
            )
            mapping = mapping_match.group(0) if mapping_match else ""
            for scene_name in scene_names:
                if scene_name not in mapping:
                    errors.append(f"{group.name}: compact 场景局部对应表 lacks listed scene '{scene_name}'")
            if not 1 <= len(scene_files) <= 3:
                errors.append(f"{group.name}: compact scene mode requires one to three local scene-detail sheets")
            compact_numbers = []
            for path in scene_files:
                match = COMPACT_SCENE_RE.match(path.stem)
                if not match:
                    errors.append(f"{group.name}/{path.name}: compact mode permits only scene_多场景局部_details_01..03_16x9 files, no main/reverse")
                else:
                    compact_numbers.append(int(match.group(1)))
            if sorted(compact_numbers) != list(range(1, len(compact_numbers) + 1)):
                errors.append(f"{group.name}: compact scene-detail sheet numbers must begin at 01 and be consecutive")
        else:
            scene_sets: dict[str, set[str]] = defaultdict(set)
            scene_counts: dict[str, int] = defaultdict(int)
            unmatched_scene_files: list[str] = []
            for path in scene_files:
                match = SCENE_RE.match(path.stem)
                if not match:
                    unmatched_scene_files.append(path.name)
                    continue
                scene_id = match.group("scene").lower()
                scene_sets[scene_id].add(match.group("kind").lower())
                scene_counts[scene_id] += 1

            for name in unmatched_scene_files:
                errors.append(
                    f"{group.name}/{name}: scene filename does not follow "
                    "scene_<id>_(main|reverse|details)_16x9 naming"
                )

            for scene_id, kinds in scene_sets.items():
                missing = {"main", "reverse", "details"} - kinds
                if missing:
                    errors.append(
                        f"{group.name}: scene '{scene_id}' is missing {', '.join(sorted(missing))}"
                    )
                if scene_counts[scene_id] != 3:
                    errors.append(
                        f"{group.name}: scene '{scene_id}' has {scene_counts[scene_id]} formal scene images; exactly main, reverse, and details are required"
                    )

        cell_images = {}
        for path in images:
            try:
                with Image.open(path) as image:
                    image.load()
                    width, height = image.size
                    if path in storyboards or path in scene_files and ("details" in path.name.lower() or packed_mode):
                        declared_count = re.search(r"(\d+)panel", path.name, re.IGNORECASE) if path in storyboards else None
                        cell_images[path.name] = ((width, height), int(declared_count.group(1)) if declared_count else None)
                    if not is_16_9(width, height):
                        errors.append(
                            f"{group.name}/{path.name}: {width}x{height} is not 16:9"
                        )
                    if path in storyboards and not looks_grayscale(image):
                        color_fraction = storyboard_color_fraction(image)
                        marks = read_field_block(group_text, "故事板运动标注") or ""
                        if color_fraction > 0.08 or not marks or marks == "无":
                            errors.append(f"{group.name}/{path.name}: storyboard is not grayscale line art with declared sparse colored motion annotations (color fraction={color_fraction:.1%})")
                        else:
                            warnings.append(f"{group.name}/{path.name}: verify colored marks are motion guides only, agree with action, and never appear in final video")
                    if path in storyboards:
                        if image_entropy(image) < 2.0 or dynamic_range(image) < 80:
                            warnings.append(
                                f"{group.name}/{path.name}: storyboard may be too faint/simple; "
                                "manual readability check required"
                            )
                    if path in character_files + prop_files + scene_files:
                        if mostly_blank_or_placeholder(image):
                            errors.append(
                                f"{group.name}/{path.name}: asset appears blank/placeholder"
                            )
                    if path in scene_files:
                        colorfulness = scene_colorfulness(image)
                        if looks_grayscale(image, tolerance=3.0) or colorfulness < 6.0:
                            errors.append(
                                f"{group.name}/{path.name}: formal scene is effectively grayscale/near-monochrome "
                                f"(colorfulness={colorfulness:.1f}); regenerate with the locked color script"
                            )
                        elif colorfulness < 12.0:
                            warnings.append(
                                f"{group.name}/{path.name}: formal scene may be too desaturated "
                                f"(colorfulness={colorfulness:.1f}); manual color-script review required"
                            )
            except Exception as exc:
                errors.append(
                    f"{group.name}/{path.name}: unreadable image ({exc})"
                )

        if not allow_legacy:
            errors.extend(f"{group.name}: {e}" for e in cell_layout_errors(group_text, cell_images))

        for path in prop_files:
            try:
                with Image.open(path) as image:
                    image.load()
                    if image_entropy(image) < 2.5:
                        warnings.append(
                            f"{group.name}/{path.name}: prop sheet may be schematic/simple; "
                            "manual 3D-production-asset review required"
                        )
            except Exception:
                pass

        for path in production_txt_files:
            content = path.read_text(encoding="utf-8-sig", errors="replace")

            english_heading = FORBIDDEN_ENGLISH_HEADINGS.search(content)
            if english_heading:
                errors.append(
                    f"{group.name}/{path.name}: English production heading is not allowed "
                    f"({english_heading.group(1)})"
                )

            if "中文对白" in content or "英文对白" in content:
                errors.append(
                    f"{group.name}/{path.name}: use one 对白 field formatted as Chinese speaker name plus approved spoken line"
                )

            forbidden_video_prompt_phrases = (
                "故事板不得添加彩色、灰洗或任何色块",
            )
            for phrase in forbidden_video_prompt_phrases:
                if phrase in content:
                    errors.append(
                        f"{group.name}/{path.name}: workflow-only restriction must not enter the video TXT ({phrase})"
                    )

            for field in REQUIRED_CHINESE_FIELDS:
                if field not in content:
                    errors.append(
                        f"{group.name}/{path.name}: missing Chinese field {field}"
                    )

            for state_field in ("本组进入状态", "本组退出状态"):
                state_match = re.search(
                    rf"^{state_field}\s*[：:]\s*(.*?)\s*$", content, flags=re.MULTILINE
                )
                if state_match and not state_match.group(1).strip():
                    errors.append(
                        f"{group.name}/{path.name}: {state_field} must describe the chronological handoff state"
                    )

            color_match = re.search(
                r"^视频上色约束\s*[：:]\s*(.+?)\s*$", content, flags=re.MULTILINE
            )
            if color_match:
                color_value = color_match.group(1)
                if "彩色" not in color_value or "黑白" not in color_value:
                    errors.append(
                        f"{group.name}/{path.name}: 视频上色约束 must require color asset rendering and forbid black-and-white final frames"
                    )

            video_text_match = re.search(
                r"^视频文字约束\s*[：:]\s*(.+?)\s*$", content, flags=re.MULTILINE
            )
            if video_text_match:
                video_text_value = video_text_match.group(1)
                if re.search(r"(?:禁止|不得|不允许|不出现|不含)[^。\n;；]*中文|(?:只|仅)允许英文", video_text_value):
                    errors.append(
                        f"{group.name}/{path.name}: 视频文字约束 must allow Chinese final-video text"
                    )

            protagonist_match = re.search(
                r"^主角判定\s*[：:]\s*(.+?)\s*$", content, flags=re.MULTILINE
            )
            if protagonist_match:
                protagonist_value = protagonist_match.group(1).strip()
                if not protagonist_value:
                    errors.append(
                        f"{group.name}/{path.name}: 主角判定 must not be empty"
                    )
                no_entity = any(
                    token in protagonist_value
                    for token in ("无角色型实体", "无人物或角色型实体", "纯场景")
                )
                protagonist_files = [
                    p for p in character_files
                    if any(token in p.name.lower() for token in ("protagonist", "main_character", "主角"))
                ]
                if not no_entity and not protagonist_files:
                    errors.append(
                        f"{group.name}/{path.name}: 主角判定 names an established/shot protagonist but no protagonist three-view asset is delivered"
                    )

            weapon_axis_match = re.search(
                r"^武器轴线核对\s*[：:]\s*(.*?)\s*$", content, flags=re.MULTILINE
            )
            if weapon_axis_match and not weapon_axis_match.group(1).strip():
                errors.append(
                    f"{group.name}/{path.name}: 武器轴线核对 must be non-empty; use 无 when no aiming/firing occurs"
                )

            group_audit_fields = (
                ("对白保全核对", "无对白"),
                ("镜头节奏核对", None),
                ("空间合理性核对", None),
                ("群像差异化核对", "无群像"),
                ("追击节奏核对", "无追击"),
                ("场景局部对应表", None),
            )
            for field_name, allowed_none in group_audit_fields:
                value = read_field_block(content, field_name)
                if value is None or not value:
                    errors.append(
                        f"{group.name}/{path.name}: {field_name} must contain a concrete audit result"
                        + (f" or use {allowed_none}" if allowed_none else "")
                    )

            format_match = re.search(
                r"^画面格式\s*[：:]\s*(.+?)\s*$", content, flags=re.MULTILINE
            )
            if format_match:
                format_value = format_match.group(1)
                if "彩色" not in format_value or "线稿故事板" in format_value:
                    errors.append(
                        f"{group.name}/{path.name}: 画面格式 must describe the final 16:9 color video, not the monochrome storyboard production format"
                    )

            other_match = re.search(r"^其他人物合集\s*[：:]\s*(.+?)\s*$", content, flags=re.MULTILINE)
            if other_match:
                other_value = other_match.group(1).strip()
                other_files = [p for p in images if "other_characters" in p.name.lower()]
                if other_value not in {"无", "None", "NONE"} and not other_files:
                    errors.append(
                        f"{group.name}/{path.name}: TXT lists other characters ({other_value}) "
                        "but other_characters sheet is missing"
                    )
                if other_value in {"无", "None", "NONE"} and other_files:
                    warnings.append(
                        f"{group.name}: other_characters exists although TXT says none; manual review required"
                    )

            # Canon continuity guard: a dead named ADAPT-17 should not be used as the
            # current residual-subject label when the text describes generic ADAPT units.
            if re.search(r"(残存|其他|generic|residual).{0,20}ADAPT", content, flags=re.IGNORECASE) \
               and re.search(r"ADAPT-?17", content, flags=re.IGNORECASE):
                errors.append(
                    f"{group.name}/{path.name}: generic/residual ADAPT is mixed with the named ADAPT-17 identity; relabel the current asset generically"
                )

            declared_match = re.search(r"格数\s*[：:]\s*(\d+)", content)
            panel_count = len(
                re.findall(r"^分镜(?:\s|[：:])", content, flags=re.MULTILINE)
            )
            if declared_match and int(declared_match.group(1)) != panel_count:
                errors.append(
                    f"{group.name}/{path.name}: declared {declared_match.group(1)} panels "
                    f"but found {panel_count} panel records"
                )
            if panel_count > 10:
                errors.append(
                    f"{group.name}/{path.name}: {panel_count} panels exceed the 10-panel maximum"
                )

            quantity_locks = re.findall(
                r"^唯一角色数量锁定\s*[：:]\s*(.*?)\s*$", content, flags=re.MULTILINE
            )
            if len(quantity_locks) != panel_count:
                errors.append(
                    f"{group.name}/{path.name}: found {len(quantity_locks)} unique-character quantity locks for {panel_count} panels; every panel needs one"
                )
            for index, value in enumerate(quantity_locks, start=1):
                if not value.strip():
                    errors.append(
                        f"{group.name}/{path.name}: unique-character quantity lock {index} is empty"
                    )

            for panel_field in ("本格新增叙事功能", "情绪/表演", "环境威胁/视觉副线", "机位空间", "可见范围", "动作起止", "声源位置"):
                panel_values = re.findall(
                    rf"^{panel_field}[^\S\r\n]*[：:][^\S\r\n]*(.*?)[^\S\r\n]*$", content, flags=re.MULTILINE
                )
                if len(panel_values) != panel_count:
                    errors.append(
                        f"{group.name}/{path.name}: found {len(panel_values)} {panel_field} fields for {panel_count} panels; every panel needs one"
                    )
                for index, value in enumerate(panel_values, start=1):
                    if not value.strip():
                        errors.append(
                            f"{group.name}/{path.name}: {panel_field} {index} is empty"
                        )

            panel_records = re.split(r"^分镜(?:\s|[：:])", content, flags=re.MULTILINE)[1:]
            dialogue_values: list[str] = []
            spoken_parts: list[str] = []
            unique_dialogue_ids: set[str] = set()
            id_seen: set[str] = set()
            id_speakers: dict[str, str] = {}
            id_mode_used = not allow_legacy or any(re.search(r"^对白(?:编号|衔接)[^\S\r\n]*[：:]", rec, re.MULTILINE) for rec in panel_records)
            for panel_index, rec in enumerate(panel_records, 1):
                dm = re.search(r"^对白[^\S\r\n]*[：:][^\S\r\n]*(.*)$", rec, re.MULTILINE)
                value = dm.group(1).strip() if dm else ""
                dialogue_values.append(value)
                parts = [] if value in {"无", "None", "NONE"} else split_dialogue_records(value)
                spoken_parts.extend(parts)
                if not value:
                    errors.append(f"{group.name}/{path.name}: panel {panel_index} requires a non-empty 对白 field")
                if id_mode_used:
                    im = re.search(r"^对白编号[^\S\r\n]*[：:][^\S\r\n]*(.*)$", rec, re.MULTILINE)
                    cm = re.search(r"^对白衔接[^\S\r\n]*[：:][^\S\r\n]*(.*)$", rec, re.MULTILINE)
                    raw_ids = im.group(1).strip() if im else ""
                    raw_cues = cm.group(1).strip() if cm else ""
                    for field_name, match, raw_value in (("对白编号", im, raw_ids), ("对白衔接", cm, raw_cues)):
                        if match is None or not raw_value:
                            errors.append(f"{group.name}/{path.name}: panel {panel_index} requires non-empty {field_name}; silent panels must explicitly use 无")
                    ids = [] if raw_ids == "无" else [v.strip() for v in re.split(r"[；;、,，]", raw_ids) if v.strip()]
                    cues = dict(re.findall(r"([A-Za-z][A-Za-z0-9_-]*)\s*[=＝]\s*(首说|续说)", raw_cues))
                    if not parts:
                        if raw_ids != "无" or raw_cues != "无":
                            errors.append(f"{group.name}/{path.name}: silent panel {panel_index} needs 对白编号/对白衔接：无")
                    elif len(ids) != len(parts) or len(set(ids)) != len(ids) or set(cues) != set(ids):
                        errors.append(f"{group.name}/{path.name}: panel {panel_index} dialogue IDs/cues must map one-to-one to spoken records")
                    else:
                        for dialogue_id, part in zip(ids, parts):
                            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", dialogue_id):
                                errors.append(f"{group.name}/{path.name}: invalid source dialogue ID {dialogue_id}")
                                continue
                            cue = cues[dialogue_id]
                            if dialogue_id in id_seen and cue != "续说":
                                errors.append(f"{group.name}/{path.name}: repeated dialogue ID {dialogue_id} must be 续说; a deliberate new repetition needs a new ID")
                            # A group may open on a line continued from the previous group.
                            if dialogue_id not in id_seen and cue == "续说":
                                handoff = read_field_block(content, "对白保全核对") or ""
                                if dialogue_id not in handoff or not any(t in handoff for t in ("跨组", "上一组")):
                                    errors.append(f"{group.name}/{path.name}: first 续说 {dialogue_id} must document its cross-group source in 对白保全核对")
                            speaker = re.split(r"[：:]", part, maxsplit=1)[0].strip()
                            if dialogue_id in id_speakers and id_speakers[dialogue_id] != speaker:
                                errors.append(f"{group.name}/{path.name}: speaker changes for dialogue ID {dialogue_id}")
                            id_speakers[dialogue_id] = speaker
                            id_seen.add(dialogue_id)
                            unique_dialogue_ids.add(dialogue_id)
                else:
                    # Legacy packages remain readable; they cannot deduplicate cross-shot speech.
                    pass
            if spoken_parts and not id_mode_used:
                warnings.append(f"{group.name}/{path.name}: legacy dialogue without source IDs; cross-shot line count requires manual review")
            spoken_count = len(unique_dialogue_ids) if id_mode_used else len(spoken_parts)
            declared_status = read_field_block(content, "分组状态")
            if not declared_status and not allow_legacy:
                errors.append(f"{group.name}/{path.name}: requires non-empty 分组状态")
            tail_status = declared_status or "常规"
            if tail_status not in {"常规", "整集尾组"}:
                errors.append(f"{group.name}/{path.name}: 分组状态 must be 常规 or 整集尾组")
            episode_tail = tail_status == "整集尾组"
            if episode_tail and group != groups[-1]:
                errors.append(f"{group.name}/{path.name}: 整集尾组 must be the final production group")
            if episode_tail and not read_field_block(content, "尾组说明"):
                errors.append(f"{group.name}/{path.name}: 整集尾组 requires a concrete 尾组说明")

            audible_count = count_audible_characters(dialogue_values)
            if audible_count > 100 and not allow_legacy:
                errors.append(f"{group.name}/{path.name}: 总发声字数 {audible_count} exceeds 100; 按语义顺延下一组并重算字数与格数")
            declared_count = inline_field(content, "总发声字数")
            if declared_count is not None:
                match = re.fullmatch(r"(\d+)(?:字)?", declared_count.strip())
                if not match or int(match.group(1)) != audible_count:
                    errors.append(f"{group.name}/{path.name}: 总发声字数 must match actual audible fragments ({audible_count})")

            dialogue_spec_match = re.search(
                r"^对白规格\s*[：:]\s*(.+?)\s*$", content, flags=re.MULTILINE
            )
            if dialogue_spec_match:
                dialogue_spec = dialogue_spec_match.group(1).strip()
                valid_specs = {"无对白", "1-2句短对白", "1—2句短对白", "1–2句短对白", "三句以上或长对白", "3句以上或长对白"}
                if allow_legacy:
                    valid_specs.add("超过100字对白")
                if dialogue_spec not in valid_specs:
                    errors.append(f"{group.name}/{path.name}: 对白规格 must be 无对白, 1-2句短对白, or 三句以上或长对白; 超过100字对白 is legacy-only")
                elif dialogue_spec == "无对白":
                    if spoken_parts:
                        errors.append(f"{group.name}/{path.name}: 对白规格 says 无对白 but spoken lines are present")
                    if panel_count > 10:
                        errors.append(f"{group.name}/{path.name}: no-dialogue task exceeds the 10-panel maximum")
                    elif not allow_legacy and not episode_tail and panel_count < 9:
                        errors.append(f"{group.name}/{path.name}: regular no-dialogue task requires 9–10 panels; merge coherent material or defer a batch remainder, never pad")
                else:
                    if not spoken_parts:
                        errors.append(f"{group.name}/{path.name}: dialogue group contains no spoken line")
                    if dialogue_spec in {"1-2句短对白", "1—2句短对白", "1–2句短对白"} and not 1 <= spoken_count <= 2:
                        errors.append(f"{group.name}/{path.name}: 1-2句短对白 group must contain one or two spoken lines")
                    if dialogue_spec == "超过100字对白" and audible_count <= 100:
                        errors.append(f"{group.name}/{path.name}: 超过100字对白 requires more than 100 actual audible characters")
                    target = dialogue_panel_target(audible_count, dialogue_spec, allow_legacy=allow_legacy)
                    if target is not None and not (panel_count == target or episode_tail and 1 <= panel_count < target):
                        errors.append(f"{group.name}/{path.name}: {audible_count} audible characters with {dialogue_spec} requires {target} panels, or 1–{target-1} in a documented 整集尾组")

            named_storyboard_counts: list[int] = []
            for storyboard in storyboards:
                count_match = re.search(r"(\d+)panel", storyboard.name, flags=re.IGNORECASE)
                if count_match:
                    named_storyboard_counts.append(int(count_match.group(1)))
            if named_storyboard_counts and sum(named_storyboard_counts) != panel_count:
                errors.append(
                    f"{group.name}: storyboard filenames declare {sum(named_storyboard_counts)} total panels "
                    f"but TXT contains {panel_count} panel records"
                )
            if panel_count == 10:
                packed_board = inline_field(content, "故事板排版模式") == "九图合并"
                if packed_board:
                    errors.extend(f"{group.name}: {e}" for e in budget_record_errors(content, "storyboard", len(images)))
                    if len(storyboards) != 1 or named_storyboard_counts != [10]:
                        errors.append(f"{group.name}: packed storyboard mode requires one 10panel sheet preserving all ten shots")
                elif len(storyboards) != 2 or sorted(named_storyboard_counts) != [4, 6]:
                    errors.append(
                        f"{group.name}: a 10-panel task must use exactly two storyboard sheets named as 6panel + 4panel in the same folder"
                    )
            elif 1 <= panel_count < 10 and len(storyboards) != 1:
                errors.append(
                    f"{group.name}: a {panel_count}-panel task should use one storyboard sheet; only a 10-panel task uses 6+4"
                )

            # Only actual visual-shot fields and the asset manifest imply HUD use.
            # General constraints/audit notes and negated statements are not assets.
            hud_values = []
            for rec in panel_records:
                for field in ("画面/事件", "可见范围", "视频模型约束"):
                    value = read_field_block(rec, field)
                    if value:
                        hud_values.append(value)
            manifest = read_field_block(content, "资产清单")
            if manifest:
                hud_values.append(manifest)
            hud_required = any(has_affirmative_hud(value) for value in hud_values)
            hud_covered = bool(prop_files) and (
                any(re.search(r"HUD|界面|interface", asset.stem, re.IGNORECASE) for asset in prop_files)
                or bool(manifest and has_recorded_hud_coverage(manifest, prop_files))
            )
            if hud_required and not hud_covered:
                errors.append(
                    f"{group.name}/{path.name}: HUD/UI appears in actual shot/asset records but no prop-category HUD coverage is recorded; "
                    "deliver a HUD prop asset or document its coverage in the delivered prop sheet's 资产清单"
                )

            for value in dialogue_values:
                if value in {"无", "None", "NONE"}:
                    continue

                dialogue_parts = [
                    part.strip() for part in split_dialogue_records(value) if part.strip()
                ]
                if not dialogue_parts:
                    errors.append(
                        f"{group.name}/{path.name}: empty dialogue must be written as 对白：无"
                    )
                    continue

                for dialogue_part in dialogue_parts:
                    speaker_match = re.match(
                        r"^([^：:]{1,24})\s*[：:]\s*[“\"「『]?(.*?)[”\"」』]?\s*$",
                        dialogue_part,
                    )
                    if not speaker_match:
                        errors.append(
                            f"{group.name}/{path.name}: dialogue must name the Chinese speaker before the approved spoken line ({dialogue_part})"
                        )
                        continue

                    speaker = speaker_match.group(1).strip()
                    spoken_line = speaker_match.group(2).strip()
                    if not re.search(r"[\u3400-\u9fff]", speaker):
                        errors.append(
                            f"{group.name}/{path.name}: dialogue speaker name must be Chinese ({speaker})"
                        )
                    if not spoken_line:
                        errors.append(
                            f"{group.name}/{path.name}: dialogue line is empty for speaker {speaker}"
                        )


            # Prohibitions and approved character normalization are not crop-lineage evidence.
            # Text alone cannot prove how a file was made. Flag affirmative scene/prop
            # lineage for manual inspection rather than reject every matching keyword.
            for line in content.splitlines():
                if not re.search(r"(裁切|裁剪|crop|cropped).{0,30}(场景|道具|scene|prop)", line, re.IGNORECASE):
                    continue
                if re.search(r"不得|禁止|严禁|不可|不允许|未裁|没有裁|未从|不从|不得从|\b(?:never|not|no|forbid|prohibit)\b", line, re.IGNORECASE):
                    continue
                warnings.append(f"{group.name}/{path.name}: inspect possible scene/prop crop lineage manually: {line.strip()}")

        # SD2_prompt.txt is intentionally concise and is validated separately from the
        # archival production record. It should be copy-ready, not a second audit log.
        if sd2_prompt_files:
            sd2_path = sd2_prompt_files[0]
            sd2 = sd2_path.read_text(encoding="utf-8-sig", errors="replace")
            if not allow_legacy:
                errors.extend(f"{group.name}/{sd2_path.name}: {error}" for error in sd2_global_constraint_errors(sd2))
            if (read_field_block(group_text, "故事板运动标注") or "无") != "无":
                marker_constraint = inline_field(sd2, "辅助标记约束") or inline_field(sd2, "公共限制") or ""
                if not (re.search(r"辅助线|箭头|轨迹", marker_constraint) and re.search(r"(?:不得|不允许|禁止|不)[^\n。]{0,40}(?:成片|视频|出现)", marker_constraint)):
                    errors.append(f"{group.name}/{sd2_path.name}: motion guides require an explicit final-video exclusion constraint")
            if group_text:
                group_id = inline_field(group_text, "分组") or group.name
                errors.extend(f"{group.name}/{sd2_path.name}: {error}" for error in cross_file_errors(group_text, sd2, group_id))
            forbidden_sd2_fields = (
                "源镜号", "原稿剪辑参考", "对白编号", "对白衔接", "中文参考",
                "对白保全核对", "镜头节奏核对", "空间合理性核对", "群像差异化核对",
                "追击节奏核对", "人物资产分表", "场景局部对应表", "资产清单",
                "主角清单", "主角资产映射", "混合人物资产映射", "总发声字数", "组间镜头衔接核对",
                "九图优化记录", "图格布局", "图格比例核对", "故事板运动标注", "场景视图映射",
                "ZIP", "CRC",
            )
            for field in forbidden_sd2_fields:
                if re.search(rf"^{re.escape(field)}[^\S\r\n]*[：:]", sd2, re.MULTILINE | re.IGNORECASE):
                    errors.append(f"{group.name}/{sd2_path.name}: archival field {field} must not be copied into the SD2 prompt")

            sd2_records = re.split(r"^分镜编号[^\S\r\n]*[：:]", sd2, flags=re.MULTILINE)[1:]
            if not sd2_records:
                errors.append(f"{group.name}/{sd2_path.name}: no 分镜编号 records found")
            required_sd2_fields = (
                "景别", "机位/角度", "人物数量限制", "人物位置", "动作",
                "运镜", "场景/环境", "对白", "声音/音效", "本镜必要限制",
            )
            for idx, rec in enumerate(sd2_records, 1):
                for field in required_sd2_fields:
                    field_pattern = (r"(?:本镜必要限制|连续性限制)" if field == "本镜必要限制" else re.escape(field))
                    m = re.search(rf"^{field_pattern}[^\S\r\n]*[：:][^\S\r\n]*(.*)$", rec, re.MULTILINE)
                    if m is None or not m.group(1).strip():
                        errors.append(f"{group.name}/{sd2_path.name}: shot {idx} requires non-empty {field}")

            if group_text:
                production_panels = len(re.findall(r"^分镜(?:\s|[：:])", group_text, flags=re.MULTILINE))
                if production_panels and len(sd2_records) != production_panels:
                    errors.append(
                        f"{group.name}/{sd2_path.name}: contains {len(sd2_records)} shot prompts but production TXT has {production_panels} panels"
                    )

            # Size is not a hard character cap, but an SD2 prompt that is as large as
            # the production record is usually evidence that audit boilerplate leaked in.
            if group_text and len(sd2) > max(7000, int(len(group_text) * 0.75)):
                warnings.append(
                    f"{group.name}/{sd2_path.name}: prompt is unusually verbose relative to the production TXT; manual deduplication review required"
                )

    return errors, warnings


def validate_zip(zip_path: Path, delivery: Path | None = None) -> list[str]:
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
                if any(token in member.name.lower() for token in PLACEHOLDER_TOKENS):
                    return [
                        f"ZIP contains placeholder-style file: {info.filename}"
                    ]
            bad_member = archive.testzip()
            if bad_member:
                return [f"ZIP contains a corrupt member: {bad_member}"]
            if delivery is None:
                return []
            members = [info for info in archive.infolist() if not info.is_dir()]
            names = [info.filename for info in members]
            if len(set(names)) != len(names):
                return ["ZIP contains duplicate file paths"]
            # Accept either bare delivery-relative paths or one delivery-name wrapper.
            prefix = delivery.name + "/"
            wrapped = bool(names) and all(name.startswith(prefix) for name in names)
            indexed = {(info.filename[len(prefix):] if wrapped else info.filename): info for info in members}
            local = {path.relative_to(delivery).as_posix(): path for path in delivery.rglob("*") if path.is_file()}
            errors = []
            if len(indexed) != len(local):
                errors.append(f"ZIP file count differs from validated directory: {len(indexed)} vs {len(local)}")
            for missing in sorted(local.keys() - indexed.keys()):
                errors.append(f"ZIP is missing validated file: {missing}")
            for extra in sorted(indexed.keys() - local.keys()):
                errors.append(f"ZIP has an extra file: {extra}")
            for name in sorted(local.keys() & indexed.keys()):
                with local[name].open("rb") as source:
                    local_hash = hashlib.file_digest(source, "sha256").digest()
                with archive.open(indexed[name]) as source:
                    zip_hash = hashlib.file_digest(source, "sha256").digest()
                if local_hash != zip_hash:
                    errors.append(f"ZIP content differs from validated file: {name}")
            return errors
    except zipfile.BadZipFile:
        return [f"Invalid ZIP file: {zip_path}"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("delivery", type=Path, help="Top-level delivery directory")
    parser.add_argument("--zip", dest="zip_path", type=Path, help="Optional ZIP to test")
    parser.add_argument("--allow-legacy", action="store_true",
                        help="Explicitly allow legacy groups without status/dialogue IDs; default is strict")
    args = parser.parse_args()

    errors, warnings = validate(args.delivery.resolve(), allow_legacy=args.allow_legacy)
    if args.zip_path:
        errors.extend(validate_zip(args.zip_path.resolve(), args.delivery.resolve()))

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    print(f"RESULT: {len(errors)} error(s), {len(warnings)} warning(s)")
    if not errors:
        print(
            "MANUAL REVIEW STILL REQUIRED: each folder is one coherent task of variable duration, grouped by dialogue and narrative continuity rather than estimated seconds; current-arc protagonists use approved independent/paired sheets or documented 1+1 protagonist/support sheets under ordered nine-image optimization, with at most two protagonists per pure protagonist sheet, shared ground line, consistent scale, credible relative height, and complete Chinese-labeled front/side/back coverage; supporting-character sheets are single-row horizontal lineups, not stacked grids or card mosaics; recognizable crowd identities do not reuse one face/body template and every action-bearing identity has asset coverage; shot scale and angle progression are intentional; every struck creature, person, or robot with a consequential hit has an explicit injury, fall, disablement, or death reaction; dialogue includes concrete performance and active threat/task counterlines; pursuit distance, obstacles, route choices, and tactical state escalate; blocking is plausible relative to danger, cover, exits, obstacles, and firing lines; supporting-character view coverage follows actual group and direct next-group action needs, regardless of identity count; protagonists keep complete turnarounds; every exactly-three-unit composite avoids a single vertical stack; final-video visible text follows approved Chinese project copy; weapon muzzle lines stay on intended targets and clear of allies across reverse angles; audible-character count is correct (each group is at most 100; excess is carried into the next group at a natural boundary, then recounted under the original dialogue classes); dialogue class and panel allocation are correct; previous-last to next-first handoffs are continuous and avoid undesigned same-person/same-scale/similar-composition jump cuts; reaction cutaways preserve continuous off-screen speech; combat-state wide shots contain the current relevant roster and objectives; named/stable unique identities appear exactly once unless explicitly scripted otherwise; HUD is audited as a labeled prop without replacing physical props; no more than four labeled identities appear per character sheet; props are limited to storyboard-used items; every storyboard and local/packed scene picture cell is 16:9 and matches declared pixel rectangles; colored storyboard marks are motion guides only and never appear in final video; packing order preserves storyboards > scenes > protagonists > supporting characters > props, stops as soon as the count reaches nine, and never deletes required views; standard mode has genuine reverse geometry and matching scene color; documented packed-scene mode retains all source-mode views; compact mode is used only for two or more coherent scenes with one to three labeled local sheets and no main/reverse; every listed scene and panel is covered by a clean color local composite preserving the actual cameras, fixed architecture and persistent damage; prioritize one-call final-composite generation or matching approved plates, supplementing only unclear or structurally wrong essential areas; no crop lineage remains; and props are production quality."
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
