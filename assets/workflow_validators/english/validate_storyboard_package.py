#!/usr/bin/env python3
"""Validate complete SD2 package declarations, files, and limited pixel properties.

Strict v14.10.3 includes one-shot/one-clean-plate mapping and formal-asset reuse
ledger checks. Partial deliverables require scope-specific manual review. Image
identity, actual camera geometry, real plate slots, readability, physical contact,
and source dialogue semantics remain manual checks in package-template.md P-QA.
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

from plan_english_dialogue import MAX_ENGLISH_WORDS, english_word_count

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
    "连续性", "视频模型约束", "视频上色约束", "视频文字约束", "武器轴线核对", "镜头节奏核对",
    "空间合理性核对", "群像差异化核对", "追击节奏核对", "本格新增叙事功能", "情绪/表演", "环境威胁/视觉副线",
    "机位空间", "可见范围", "动作起止", "声源位置", "对白保全核对",
    "场景局部对应表", "资产清单",
)

SCENE_RE = re.compile(
    r"^(?P<prefix>\d+_)?scene_(?P<scene>.+?)_(?P<kind>main|reverse|details)(?:_(?P<page>0[1-9]))?_16x9$",
    re.IGNORECASE,
)
COMPACT_SCENE_RE = re.compile(
    r"^(?:\d+_)?scene_多场景局部_details_(0[1-3])_16x9$",
    re.IGNORECASE,
)

COMPOSITE_SCENE_RE = re.compile(r"^(?:\d+_)?scene_场景合辑_(0[1-9])_16x9$", re.IGNORECASE)

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


def sparse_color_annotations(image: Image.Image, *, declared: bool) -> bool:
    """Heuristic screening only: sparse color may be marks or erroneous colored art.

    Declaration is required; manual P-QA must verify actual arrows/lines, direction,
    legend and monochrome subjects. The 12% screen is not a visual pass criterion.
    """
    if looks_grayscale(image):
        return True
    if not declared:
        return False
    import numpy as np
    pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
    spread = pixels.max(axis=2) - pixels.min(axis=2)
    colored = spread > 16
    return bool(colored.any() and colored.mean() <= 0.12 and spread[~colored].mean() <= 1.5)


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
    covered, bound = [], []
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
        if filename not in protagonist_files:
            errors.append(f"主角资产映射 file is missing or is not a protagonist asset: {filename}")
        if "main_characters" in filename.lower():
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
    return errors


def character_asset_errors(content: str, files: list[Path], *, legacy: bool) -> list[str]:
    """Validate a single character table; required image views remain visual checks."""
    table = read_field_block(content, "人物资产表")
    if table is None and legacy:
        return protagonist_coverage_errors(content, files, legacy=True)
    if not table:
        return ["requires non-empty 人物资产表; use 无 only for no character-like entity"]
    errors = []
    if not legacy:
        for field in ("主角清单", "主角资产映射", "主角判定", "人物资产核对", "人物资产分表", "其他人物合集"):
            if read_field_block(content, field) is not None:
                errors.append(f"new records use 人物资产表 only; remove duplicate legacy character field {field}")
    verdict = inline_field(content, "人物判定") or ""
    if not verdict:
        errors.append("requires non-empty 人物判定 with approved arc/shot-protagonist basis")
    by_name = {path.name: path for path in files}
    if table == "无":
        if files:
            errors.append("人物资产表：无 requires no character assets")
        if not any(token in verdict for token in ("无角色型实体", "无人物或角色型实体", "纯场景")):
            errors.append("人物资产表：无 requires an explicit no-character exception in 人物判定")
        rows = []
    else:
        rows = table.splitlines()
    identities, bindings, categories = [], defaultdict(list), []
    for index, line in enumerate(rows, 1):
        parts = [part.strip() for part in re.sub(r"^[-*•]\s*", "", line.strip()).split("|")]
        if len(parts) != 5 or any(not part for part in parts):
            errors.append(f"人物资产表 row {index} requires identity | category | filename | views | current state")
            continue
        identity, category, filename, views, state = parts
        identities.append(identity)
        categories.append(category)
        bindings[filename].append((identity, category))
        if not re.search(r"[\u3400-\u9fff]", identity):
            errors.append("人物资产表 requires canonical Chinese identity names")
        if category not in {"篇章主角", "镜头主角", "配角"}:
            errors.append(f"人物资产表 unsupported category: {category}")
        if filename not in by_name:
            errors.append(f"人物资产表 binds a missing or non-character file: {filename}")
        if category == "篇章主角" and not all(token in views for token in ("正", "侧", "背", "全身", "特写")):
            errors.append(f"人物资产表 arc protagonist needs front/side/back full bodies and face close-up: {identity}")
    if len(identities) != len(set(identities)):
        errors.append("人物资产表 must cover every identity exactly once without duplicates")
    if set(bindings) != set(by_name):
        errors.append("人物资产表 must bind every delivered character file exactly once without extras")
    if categories:
        shot_count = categories.count("镜头主角")
        arc_count = categories.count("篇章主角")
        if (arc_count and shot_count) or (not arc_count and shot_count != 1):
            errors.append("人物资产表 requires exactly one temporary 镜头主角 only when no arc protagonist appears")
    for filename, people in bindings.items():
        lower = filename.lower()
        if "main_characters" in lower:
            if len(people) != 2 or any(category != "篇章主角" for _, category in people):
                errors.append(f"main_characters must cover exactly two arc protagonists: {filename}")
        elif "mixed_characters" in lower:
            roles = [category for _, category in people]
            if len(people) != 2 or roles.count("配角") != 1 or sum(role in {"篇章主角", "镜头主角"} for role in roles) != 1:
                errors.append(f"mixed_characters requires exactly one protagonist and one supporting identity: {filename}")
        elif "protagonist" in lower:
            if len(people) != 1 or people[0][1] not in {"篇章主角", "镜头主角"}:
                errors.append(f"independent protagonist sheet must cover one protagonist: {filename}")
        elif "other_characters" in lower:
            if not 1 <= len(people) <= 4 or any(category != "配角" for _, category in people):
                errors.append(f"other_characters requires one to four supporting identities: {filename}")
            if not re.search(r"other_characters_\d{2}_", lower):
                errors.append(f"other_characters requires a two-digit sheet number: {filename}")
        else:
            errors.append(f"人物资产表 requires protagonist/main_characters/mixed_characters/other_characters naming: {filename}")
    declared = set(identities)
    for value in re.findall(r"^唯一角色数量锁定[^\S\r\n]*[：:][^\S\r\n]*(.*)$", content, re.MULTILINE):
        for item in re.split(r"[；;、，,]", value):
            match = re.match(r"\s*(.+?)\s*[×xX]\s*\d", item)
            if match and match.group(1).strip() not in declared:
                errors.append(f"人物资产表 lacks visible identity: {match.group(1).strip()}")
    return errors


def image_budget_errors(content: str, images: list[Path], *, legacy: bool) -> list[str]:
    """Check staged counts; real merge order, feasibility and readability need review."""
    value = inline_field(content, "图片预算核对")
    if value is None and legacy:
        return []
    if legacy and value and "初始" not in value:
        final = re.search(r"最终\s*[=＝]\s*(\d+)", value)
        return [] if final and int(final.group(1)) == len(images) else ["图片预算核对 final count must equal actual uploaded image count"]
    stages = ("初始", "道具后", "配角后", "主角后", "场景后") + (("故事板后",) if legacy and "故事板后" in (value or "") else ()) + ("最终",)
    counts = []
    for stage in stages:
        matches = re.findall(re.escape(stage) + r"\s*[=＝]\s*(\d+)", value or "")
        if len(matches) != 1:
            return ["图片预算核对 requires 初始=N；道具后=N；配角后=N；主角后=N；场景后=N；最终=N；说明=reason"]
        counts.append(int(matches[0]))
    errors = []
    if not re.search(r"说明\s*[=＝]\s*\S", value or ""):
        errors.append("图片预算核对 requires a concrete merge/skip reason")
    if counts[-1] != len(images) or counts[-2] != counts[-1]:
        errors.append("图片预算核对 final count must equal actual uploaded image count and 场景后")
    if any(after > before for before, after in zip(counts, counts[1:])):
        errors.append("图片预算核对 staged counts cannot increase")
    if any(before <= 9 and after != before for before, after in zip(counts, counts[1:])):
        errors.append("图片预算核对 stop merging once count is at most nine")
    obsolete = re.search(r"故事板后\s*[=＝]\s*(\d+)", value or "")
    if obsolete and not legacy and int(obsolete.group(1)) != counts[4]:
        errors.append("图片预算核对 storyboard is one sheet from the initial budget; no storyboard-stage reduction")
    old_pairs = set()
    for line in (read_field_block(content, "资产复用核对") or "").splitlines():
        parts = [part.strip() for part in re.sub(r"^[-*•]\s*", "", line.strip()).split("|")]
        if len(parts) == 4:
            filename, action, origin, explanation = parts
            retained = action == "直接复用" or (action in {"必要规范排版", "局部补缺/修复"} and any(token in explanation for token in ("保留既有双主角合图", "保留既有人物合图", "保留既有场景合辑")))
            if retained and origin not in {"无", "none", "None", "未提供"}:
                old_pairs.add(filename)
    pairs = {path.name for path in images if any(token in path.name.lower() for token in ("main_characters", "mixed_characters"))}
    new_pairs = pairs - old_pairs
    if counts[2] - counts[3] != len(new_pairs):
        errors.append("图片预算核对 protagonist-stage saving must equal one slot per newly combined protagonist pair")
    if new_pairs and counts[2] <= 9:
        errors.append("new protagonist merging is permitted only when 道具后/配角后 still exceeds nine")
    new_scene_composites = {path.name for path in images if COMPOSITE_SCENE_RE.fullmatch(path.stem)} - old_pairs
    if new_scene_composites and (counts[3] <= 9 or counts[4] >= counts[3]):
        errors.append("new scene composites require 主角后 still above nine and an actual 场景后 reduction")
    return errors


def image_review_errors(content: str, images: list[Path], *, legacy: bool) -> list[str]:
    """Verify actual dimension declarations; this cannot prove effective detail."""
    table = read_field_block(content, "图像验收记录")
    if table is None and legacy:
        return []
    if not table:
        return ["requires 图像验收记录 with one actual dimension/result row per image"]
    errors, bound = [], []
    by_name = {path.name: path for path in images}
    for index, line in enumerate(table.splitlines(), 1):
        parts = [part.strip() for part in re.sub(r"^[-*•]\s*", "", line.strip()).split("|")]
        if len(parts) != 3 or any(not part for part in parts):
            errors.append(f"图像验收记录 row {index} requires filename | actual WIDTHxHEIGHT | concrete inspection result")
            continue
        filename, dimensions, result = parts
        bound.append(filename)
        match = re.fullmatch(r"(\d+)\s*[xX×]\s*(\d+)", dimensions)
        if not match:
            errors.append(f"图像验收记录 requires actual numeric width and height: {filename}")
        elif filename in by_name:
            try:
                with Image.open(by_name[filename]) as image:
                    if image.size != (int(match.group(1)), int(match.group(2))):
                        errors.append(f"图像验收记录 dimensions differ from actual file: {filename}")
            except OSError as exc:
                errors.append(f"图像验收记录 cannot inspect {filename}: {exc}")
        if result.strip("。，；; ") in {"已核对", "合格", "通过", "高清", "4K"}:
            errors.append(f"图像验收记录 needs a concrete inspection result: {filename}")
    if sorted(bound) != sorted(by_name) or len(bound) != len(set(bound)):
        errors.append("图像验收记录 must cover every actual image exactly once without extras")
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


def cross_group_dialogue_errors(group_dialogue, source_rows, groups, pending: str) -> list[str]:
    errors = []
    pending_rows = {
        tuple(re.sub(r"\s+", " ", field).strip() for field in match.groups())
        for match in re.finditer(r"^- +([A-Za-z][A-Za-z0-9_-]*) *\| *([^|\r\n]+) *\| *(.+)$", pending, re.MULTILINE)
    }
    for source_id in group_dialogue.keys() | source_rows.keys():
        delivery = group_dialogue.get(source_id, {})
        declared = source_rows.get(source_id, {})
        if not declared and len(delivery) <= 1 and all(
            fragments[0][0] == "首说" for fragments in delivery.values()
        ):
            continue
        if delivery.keys() != declared.keys():
            errors.append(f"{source_id}: each cross-group fragment needs a matching 跨组对白原文 row")
            continue

        previous = None
        for group, fragments in delivery.items():
            speaker, start, end, original = declared[group]
            expected_cue = "首说" if start == 0 else "续说"
            if fragments[0][0] != expected_cue or any(name != speaker for _, name, _ in fragments):
                errors.append(f"{group}/{source_id}: cross-group cue or speaker differs from the declared source")
            chunk = re.sub(r"\s+", " ", original[start:end]).strip()
            pattern = r"\s*".join(re.escape(spoken) for _, _, spoken in fragments)
            if not 0 <= start < end <= len(original) or not chunk or not re.fullmatch(pattern, chunk):
                errors.append(f"{group}/{source_id}: spoken fragments differ from the declared source span")
            if previous is None:
                if start and group != groups[0].name:
                    errors.append(f"{group}/{source_id}: missing opening fragment before this group")
            else:
                last_speaker, last_end, last_original = previous
                if (speaker, original) != (last_speaker, last_original) or start != last_end:
                    errors.append(f"{group}/{source_id}: cross-group source changed or spans overlap/leave a gap")
            previous = (speaker, end, original)

        last_group = next(reversed(delivery))
        speaker, _, end, original = declared[last_group]
        if end < len(original):
            remaining = re.sub(r"\s+", " ", original[end:]).strip()
            if last_group != groups[-1].name or (source_id, speaker, remaining) not in pending_rows:
                errors.append(f"{last_group}/{source_id}: incomplete source dialogue without a matching pending handoff")
    return errors


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


def scene_composite_rows(content: str, scene_files: list[Path]) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """Validate bindings only; each real pane's ratio, geometry and clarity are manual."""
    composites = {path.name for path in scene_files if COMPOSITE_SCENE_RE.fullmatch(path.stem)}
    names = {name.strip() for name in re.split(r"[；;、，,]", inline_field(content, "场景清单") or "") if name.strip()}
    rows, errors, slots = [], [], set()
    for line in (read_field_block(content, "场景拼接对应表") or "").splitlines():
        if line.strip() == "无":
            continue
        parts = [part.strip() for part in re.sub(r"^[-*•]\s*", "", line.strip()).split("|")]
        if len(parts) != 4 or any(not part for part in parts):
            errors.append("场景拼接对应表 requires scene | main/reverse/details | actual composite filename | slot")
            continue
        scene, kind, filename, slot = parts
        if scene not in names or kind not in {"main", "reverse", "details"} or filename not in composites:
            errors.append("场景拼接对应表 binds an unknown scene, type or composite file")
        if (filename, slot) in slots:
            errors.append("场景拼接对应表 repeats a composite slot")
        slots.add((filename, slot))
        rows.append((scene, kind, filename, slot))
    if {row[2] for row in rows} != composites:
        errors.append("场景拼接对应表 must bind every delivered composite file")
    numbers = sorted(int(COMPOSITE_SCENE_RE.fullmatch(Path(name).stem).group(1)) for name in composites)
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append("scene composite numbers must begin at 01 and be consecutive")
    return rows, errors


def supplemental_main_errors(content: str, scene_files: list[Path]) -> list[str]:
    """Check declared supplemental main files; need/geometry/HD require visual review."""
    errors = []
    block = read_field_block(content, "补充正打核对") or ""
    lines = [line for line in block.splitlines() if line.strip()]
    if lines and not any("|" in line for line in lines) and not block.strip().startswith("无"):
        errors.append("补充正打核对 requires scene | delivered main filename | missing spatial context")
    scene_names = {
        name.strip() for name in re.split(r"[；;、，,]", inline_field(content, "场景清单") or "")
        if name.strip()
    }
    composite_rows, _ = scene_composite_rows(content, scene_files)
    composite_mains = {(scene, filename) for scene, kind, filename, _ in composite_rows if kind == "main"}
    declared_files, declared_scenes = [], []
    for line in lines:
        if "|" not in line:
            continue
        parts = [part.strip() for part in re.sub(r"^[-*•]\s*", "", line.strip()).split("|")]
        if len(parts) != 3 or any(not part for part in parts):
            errors.append("补充正打核对 requires scene | delivered main filename | missing spatial context")
            continue
        scene, filename, _reason = parts
        declared_scenes.append(scene)
        declared_files.append(filename)
        match = SCENE_RE.match(Path(filename).stem)
        if (scene, filename) not in composite_mains and (Path(filename).name != filename or not match
                or match.group("kind").lower() != "main" or match.group("scene") != scene):
            errors.append(f"补充正打核对 requires a same-location scene_<scene>_main_16x9 file: {filename}")
        if scene not in scene_names:
            errors.append(f"补充正打核对 scene is absent from 场景清单: {scene}")
    if len(set(declared_scenes)) != len(declared_scenes):
        errors.append("补充正打核对 permits one unique main file per qualifying location")
    actual = {
        (match.group("scene"), path.name) for path in scene_files
        if (match := SCENE_RE.match(path.stem)) and match.group("kind").lower() == "main"
    } | composite_mains
    if set(zip(declared_scenes, declared_files)) != actual:
        errors.append("补充正打核对 must bind every delivered supplemental main exactly once; missing or undeclared main file")
    return errors


def scene_mapping_errors(content: str, scene_files: list[Path], *, legacy: bool) -> list[str]:
    """Validate declared one-shot/one-plate bindings, not image geometry or slots."""
    mapping = read_field_block(content, "场景局部对应表") or ""
    lines = [line for line in mapping.splitlines() if "|" in line]
    errors = []
    modes = re.findall(r"^场景资产模式[^\S\r\n]*[：:][^\S\r\n]*(.*)$", content, re.MULTILINE)
    if (not legacy or modes) and (len(modes) != 1 or modes[0].strip() not in {"常规", "多场景局部"}):
        errors.append("场景资产模式 requires exactly one value: 常规 or 多场景局部")
    if legacy and not lines:
        return errors
    if not lines:
        return errors + ["场景局部对应表 requires one structured row per shot (N格=N块)"]
    scene_value = inline_field(content, "场景清单") or ""
    scene_names = [name.strip() for name in re.split(r"[；;、，,]", scene_value) if name.strip()]
    if not scene_names or len(scene_names) != len(set(scene_names)):
        errors.append("场景清单 requires non-empty unique actual location names")
    if not legacy and not read_field_block(content, "场景身份判定"):
        errors.append("requires non-empty 场景身份判定 with approved source and spatial basis")
    compact = inline_field(content, "场景资产模式") == "多场景局部"
    composite_rows, composite_errors = scene_composite_rows(content, scene_files)
    errors.extend(composite_errors)
    composite_details = {(filename, slot, scene) for scene, kind, filename, slot in composite_rows if kind == "details"}
    details = {filename: None for filename, _, _ in composite_details}
    for asset in scene_files:
        match = SCENE_RE.match(asset.stem)
        if match and match.group("kind").lower() == "details":
            details[asset.name] = match.group("scene")
        elif COMPACT_SCENE_RE.match(asset.stem):
            details[asset.name] = None
    if not compact and {name.casefold() for name in scene_names} != {
        name.casefold() for name in details.values() if name is not None
    } | {scene.casefold() for _, _, scene in composite_details}:
        errors.append("场景清单 must match the actual standard-mode details location names")
    group_id = inline_field(content, "分组") or ""
    expected_ids = [identity for identity, _ in shot_records(content, sd2=False, group_id=group_id)]
    bound_ids, plate_ids, used_files, bound_scenes = [], [], set(), set()
    bound_composite_details = set()
    for index, line in enumerate(lines, 1):
        parts = [part.strip() for part in re.sub(r"^[-*•]\s*", "", line.strip()).split("|")]
        if len(parts) != 5 or any(not part for part in parts):
            errors.append(f"场景局部对应表 row {index} requires shot | details filename | 局部NN | scene | camera/clean-plate description")
            continue
        shot_id, filename, plate_id, scene_name, _description = parts
        if re.fullmatch(r"\d+[A-Za-z]?", shot_id):
            shot_id = f"{group_id}-{shot_id}"
        bound_ids.append(shot_id)
        plate_ids.append(plate_id)
        used_files.add(filename)
        bound_scenes.add(scene_name)
        if plate_id != f"局部{index:02}":
            errors.append(f"场景局部对应表 row {index} requires ordered unique 局部{index:02}")
        if filename not in details:
            errors.append(f"场景局部对应表 binds a missing or non-details file: {filename}")
        elif COMPOSITE_SCENE_RE.fullmatch(Path(filename).stem):
            binding = (filename, plate_id, scene_name)
            bound_composite_details.add(binding)
            if binding not in composite_details:
                errors.append("场景局部对应表 differs from composite details scene/slot binding")
        elif not compact and details[filename] is not None and details[filename].casefold() != scene_name.casefold():
            errors.append(f"场景局部对应表 scene/file identity differs: {scene_name} / {filename}")
        if scene_name not in scene_names:
            errors.append(f"场景局部对应表 scene is absent from 场景清单: {scene_name}")
    if bound_composite_details != composite_details:
        errors.append("场景拼接对应表 details must bind actual shot-local slots exactly once")
    if bound_ids != expected_ids or len(set(bound_ids)) != len(bound_ids):
        errors.append("场景局部对应表 must bind every shot exactly once in shot order (N格=N块); merged, missing, extra, or duplicate shot IDs are forbidden")
    if len(set(plate_ids)) != len(plate_ids):
        errors.append("场景局部对应表 cannot reuse one plate ID for multiple shots")
    if used_files != set(details):
        errors.append("场景局部对应表 must cover every delivered details file and no other file")
    if bound_scenes != set(scene_names) or compact and len(bound_scenes) < 2:
        errors.append("场景局部对应表 must exactly cover 场景清单; compact mode needs at least two bound actual locations")
    return errors


def reuse_ledger_errors(content: str, formal_files: list[Path], *, legacy: bool) -> list[str]:
    """Check the declared formal-asset ledger and accessible direct-copy bytes."""
    ledger = read_field_block(content, "资产复用核对") or ""
    if legacy and not ledger:
        return []
    if not ledger:
        return ["requires 资产复用核对 with approved sources and processing reasons"]
    errors, bound = [], []
    files = {asset.name: asset for asset in formal_files}
    actions = {"直接复用", "必要规范排版", "局部补缺/修复", "新生成"}
    for index, line in enumerate(ledger.splitlines(), 1):
        parts = [part.strip() for part in re.sub(r"^[-*•]\s*", "", line.strip()).split("|")]
        if len(parts) != 4 or any(not part for part in parts):
            errors.append(f"资产复用核对 row {index} requires filename | action | approved source | concrete reason")
            continue
        filename, action, origin, reason = parts
        bound.append(filename)
        if filename not in files:
            errors.append(f"资产复用核对 binds a missing or non-formal file: {filename}")
        if action not in actions:
            errors.append(f"资产复用核对 uses an unsupported processing action: {action}")
        if action != "新生成" and origin in {"无", "none", "None", "未提供"}:
            errors.append(f"资产复用核对 {action} requires an approved original source: {filename}")
        if reason.strip("。，；; ") in {"统一格式", "美化", "统一", "调整", "按要求"}:
            errors.append(f"资产复用核对 requires the specific incompatibility or missing item, not a generic reason: {filename}")
        origins = [part.strip() for part in re.split(r"[；;]", origin) if part.strip()]
        if action == "直接复用" and len(origins) != 1:
            errors.append(f"直接复用 must identify one complete approved original: {filename}")
        for origin_item in origins:
            source = Path(origin_item).expanduser()
            if not source.is_absolute():
                continue  # Cloud/asset IDs are resolved and verified by production review.
            if not source.is_file():
                errors.append(f"资产复用核对 approved local source is missing: {origin_item}")
                continue
            if action == "直接复用" and filename in files:
                try:
                    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(files[filename].read_bytes()).digest():
                        errors.append(f"直接复用 bytes differ from the approved original: {filename}")
                except OSError as exc:
                    errors.append(f"cannot verify direct reuse bytes for {filename}: {exc}")
    if sorted(bound) != sorted(files) or len(set(bound)) != len(bound):
        errors.append("资产复用核对 must bind every formal character/prop/scene file exactly once without extras")
    return errors

def explicitly_forbids(value: str, term: str) -> bool:
    """Accept documented equivalent prohibitions without accepting '不禁止'."""
    return bool(re.search(
        r"(?<!不)(?<!未)(?<!没有)(?:禁止|不得|不允许|不出现|不含)[^。\n]*" + re.escape(term),
        value,
    ))


def sd2_global_constraint_errors(sd2: str) -> list[str]:
    errors = []
    prefix = re.split(r"^分镜编号[^\S\r\n]*[：:]", sd2, maxsplit=1, flags=re.MULTILINE)[0]
    for field in ("视频上色约束", "视频文字约束"):
        occurrences = re.findall(rf"^{field}[^\S\r\n]*[：:]", sd2, re.MULTILINE)
        value = inline_field(prefix, field) or ""
        if len(occurrences) != 1 or not value:
            errors.append(f"SD2 prompt requires {field} exactly once before the shots")
        elif field == "视频上色约束":
            if not ("彩色" in value and explicitly_forbids(value, "黑白")):
                errors.append("SD2 视频上色约束 must require color assets and forbid black-and-white final frames")
        elif not (explicitly_forbids(value, "中文") and ("英文" in value or "通用符号" in value)):
            errors.append("SD2 视频文字约束 must forbid Chinese and allow English or universal symbols")
    return errors


def group_order(path: Path) -> tuple[int, str]:
    number = re.match(r"SB([0-9]+)", path.name)
    return (int(number[1]) if number else 0, path.name)


def validate(root: Path, *, allow_legacy: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not root.is_dir():
        return [f"Not a directory: {root}"], warnings

    groups = sorted(
        (path for path in root.iterdir() if path.is_dir() and path.name.startswith("SB")),
        key=group_order,
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

    group_dialogue = defaultdict(dict)
    source_rows = defaultdict(dict)
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
                "character", "protagonist", "main_character", "resident", "guard", "miner",
                "worker", "follower", "creature", "monster", "人物", "主角", "角色", "怪物"
            ))
            and p not in storyboards + scene_files + prop_files
        ]

        if len(images) > 9:
            errors.append(
                f"{group.name}: {len(images)} final upload images exceed the nine-image limit; "
                "storyboard is one sheet initially; consolidate props, supporting characters, protagonists, then same-class scenes; preserve clarity or split the task"
            )

        # Final delivery convention: protagonist status comes from the current arc,
        # not a hard-coded character pair. Mixed pairs retain each character
        # category; manual review verifies required views and readability.
        allowed_character_tokens = (
            "protagonist", "main_character", "main_characters", "mixed_characters", "other_characters",
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
        if not allow_legacy and len(storyboards) != 1:
            errors.append(f"{group.name}: requires exactly one storyboard image per group")
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
        errors.extend(f"{group.name}: {error}" for error in character_asset_errors(group_text, character_files, legacy=allow_legacy))
        errors.extend(f"{group.name}: {error}" for error in scene_mapping_errors(group_text, scene_files, legacy=allow_legacy))
        errors.extend(f"{group.name}: {error}" for error in reuse_ledger_errors(group_text, formal_assets, legacy=allow_legacy))
        errors.extend(f"{group.name}: {error}" for error in image_budget_errors(group_text, images, legacy=allow_legacy))
        errors.extend(f"{group.name}: {error}" for error in image_review_errors(group_text, images, legacy=allow_legacy))
        if allow_legacy and "|" not in (read_field_block(group_text, "场景局部对应表") or ""):
            warnings.append(f"{group.name}: legacy scene mapping is not a verified N格=N块 binding; review images under v14.10.3 manually")
        compact_mode = bool(re.search(r"^场景资产模式\s*[：:]\s*多场景局部\s*$", group_text, re.MULTILINE))
        composite_rows, _ = scene_composite_rows(group_text, scene_files)
        if not allow_legacy:
            errors.extend(f"{group.name}: {error}" for error in supplemental_main_errors(group_text, scene_files))
            declared_locations = {name.strip().casefold() for name in re.split(r"[；;、，,]", inline_field(group_text, "场景清单") or "") if name.strip()}
            views = [(scene.casefold(), kind) for scene, kind, _, _ in composite_rows if kind in {"main", "reverse"}]
            for view_file in scene_files:
                match = SCENE_RE.match(view_file.stem)
                if match and match.group("kind").lower() in {"main", "reverse"}:
                    views.append((match.group("scene").casefold(), match.group("kind").lower()))
            if any(scene not in declared_locations for scene, _ in views):
                errors.append(f"{group.name}: main/reverse location is absent from 场景清单")
            if len(set(views)) != len(views):
                errors.append(f"{group.name}: duplicate main/reverse view for one location")
            for filename in {row[2] for row in composite_rows}:
                kinds = {kind for _, kind, name, _ in composite_rows if name == filename}
                if "details" in kinds and kinds & {"main", "reverse"}:
                    errors.append(f"{group.name}/{filename}: scene composite must not mix main/reverse with details")
        if compact_mode:
            if allow_legacy:
                errors.extend(f"{group.name}: {error}" for error in supplemental_main_errors(group_text, scene_files))
            scenes_match = re.search(r"^场景清单\s*[：:]\s*(.*?)\s*$", group_text, re.MULTILINE)
            scene_names = [s.strip() for s in re.split(r"[；;、,，]", scenes_match.group(1)) if s.strip()] if scenes_match else []
            if len(scene_names) < 2 or len(set(scene_names)) < 2:
                errors.append(f"{group.name}: compact scene mode requires at least two distinct scenes in 场景清单")
            mapping = read_field_block(group_text, "场景局部对应表") or ""
            if allow_legacy and "|" not in mapping:
                for scene_name in scene_names:
                    if scene_name not in mapping:
                        errors.append(f"{group.name}: legacy compact 场景局部对应表 lacks listed scene '{scene_name}'")
            compact_files = [path for path in scene_files if COMPACT_SCENE_RE.match(path.stem) or any(filename == path.name and kind == "details" for _, kind, filename, _ in composite_rows)]
            if not 1 <= len(compact_files) <= 3:
                errors.append(f"{group.name}: compact scene mode requires one to three local scene-detail sheets")
            compact_numbers = []
            for path in scene_files:
                match = COMPACT_SCENE_RE.match(path.stem)
                if not match:
                    if COMPOSITE_SCENE_RE.fullmatch(path.stem):
                        if allow_legacy and any(kind == "reverse" for _, kind, filename, _ in composite_rows if filename == path.name):
                            errors.append(f"{group.name}: compact scene composite must not contain reverse")
                        continue
                    standard = SCENE_RE.match(path.stem)
                    if not standard or standard.group("kind").lower() not in ({"main"} if allow_legacy else {"main", "reverse"}):
                        errors.append(f"{group.name}/{path.name}: compact mode permits local details plus required main/reverse files (legacy mode: no reverse)")
                else:
                    compact_numbers.append(int(match.group(1)))
            if sorted(compact_numbers) != list(range(1, len(compact_numbers) + 1)):
                errors.append(f"{group.name}: compact scene-detail sheet numbers must begin at 01 and be consecutive")
        else:
            scene_sets: dict[str, set[str]] = defaultdict(set)
            unmatched_scene_files: list[str] = []
            roles_by_scene = defaultdict(list)
            for scene, kind, filename, slot in composite_rows:
                scene_sets[scene.lower()].add(kind)
                roles_by_scene[scene.lower()].append((kind, slot))
            for path in scene_files:
                match = SCENE_RE.match(path.stem)
                if not match:
                    if COMPOSITE_SCENE_RE.fullmatch(path.stem):
                        continue
                    unmatched_scene_files.append(path.name)
                    continue
                scene_id = match.group("scene").lower()
                scene_sets[scene_id].add(match.group("kind").lower())
                roles_by_scene[scene_id].append((match.group("kind").lower(), match.group("page")))

            for name in unmatched_scene_files:
                errors.append(
                    f"{group.name}/{name}: scene filename does not follow "
                    "scene_<id>_(main|reverse|details)_16x9 naming"
                )

            for scene_id, kinds in scene_sets.items():
                missing = ({"main", "reverse", "details"} if allow_legacy else {"details"}) - kinds
                if missing:
                    errors.append(
                        f"{group.name}: scene '{scene_id}' is missing {', '.join(sorted(missing))}"
                    )
                roles = roles_by_scene[scene_id]
                for role in ("main", "reverse"):
                    if (sum(kind == role for kind, _ in roles) != 1 if allow_legacy else sum(kind == role for kind, _ in roles) > 1):
                        errors.append(f"{group.name}: scene '{scene_id}' has a missing or duplicate {role} view")
                pages = [page for kind, page in roles if kind == "details" and (page is None or str(page).isdigit())]
                if pages and pages != [None] and (None in pages or sorted(int(page) for page in pages) != list(range(1, len(pages) + 1))):
                    errors.append(f"{group.name}: numbered details pages must begin at 01 and be consecutive; do not mix unnumbered and numbered details")


        for path in images:
            try:
                with Image.open(path) as image:
                    image.load()
                    if not allow_legacy and "transparency" in image.info:
                        alpha = image.convert("RGBA").getchannel("A")
                        if alpha.getextrema()[0] < 255:
                            errors.append(f"{group.name}/{path.name}: final image must be opaque with a solid background")
                    elif not allow_legacy and "A" in image.getbands() and image.getchannel("A").getextrema()[0] < 255:
                        errors.append(f"{group.name}/{path.name}: final image must be opaque with a solid background")
                    width, height = image.size
                    if not is_16_9(width, height):
                        errors.append(
                            f"{group.name}/{path.name}: {width}x{height} is not 16:9"
                        )
                    if path in storyboards and not looks_grayscale(image):
                        note = read_field_block(group_text, "动作辅助标注") or ""
                        declared = bool(note and note != "无")
                        if not sparse_color_annotations(image, declared=declared):
                            errors.append(f"{group.name}/{path.name}: storyboard is not grayscale with declared sparse motion marks; review actual art and annotations")
                        else:
                            warnings.append(f"{group.name}/{path.name}: sparse annotation color precheck only; manually verify arrows/lines, directions, legend and uncolored subjects")
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
                        if looks_grayscale(image, tolerance=0.0):
                            errors.append(
                                f"{group.name}/{path.name}: formal scene is grayscale "
                                f"(colorfulness={colorfulness:.1f}); repair against the approved color script"
                            )
                        elif looks_grayscale(image, tolerance=3.0) or colorfulness < 12.0:
                            warnings.append(
                                f"{group.name}/{path.name}: formal scene may be too desaturated "
                                f"(colorfulness={colorfulness:.1f}); compare with approved color script manually; statistics alone do not require recoloring"
                            )
            except Exception as exc:
                errors.append(
                    f"{group.name}/{path.name}: unreadable image ({exc})"
                )

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

            if re.search(r"^(?:中文对白|英文对白)[^\S\r\n]*[：:]", content, re.MULTILINE):
                errors.append(
                    f"{group.name}/{path.name}: use one 对白 field formatted as Chinese speaker name plus English spoken line"
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

            color_value = inline_field(content, "视频上色约束") or ""
            if "彩色" not in color_value or not explicitly_forbids(color_value, "黑白"):
                errors.append(
                    f"{group.name}/{path.name}: 视频上色约束 must require color asset rendering and forbid black-and-white final frames"
                )
            video_text_value = inline_field(content, "视频文字约束") or ""
            if not (explicitly_forbids(video_text_value, "中文") and
                    ("英文" in video_text_value or "通用符号" in video_text_value)):
                errors.append(
                    f"{group.name}/{path.name}: 视频文字约束 must forbid Chinese in the final video and allow only English or universal symbols"
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

            declared_match = re.search(r"格数\s*[：:]\s*(\d+)", content)
            panel_count = len(
                re.findall(r"^分镜(?:\s|[：:])", content, flags=re.MULTILINE)
            )
            if declared_match and int(declared_match.group(1)) != panel_count:
                errors.append(
                    f"{group.name}/{path.name}: declared {declared_match.group(1)} panels "
                    f"but found {panel_count} panel records"
                )
            pure_fight = inline_field(content, "内容类型") == "纯打斗"
            max_panels = 12 if pure_fight and inline_field(content, "对白规格") == "无对白" else 10
            if panel_count > max_panels:
                errors.append(f"{group.name}/{path.name}: {panel_count} panels exceed the {max_panels}-panel maximum")

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
                fields = re.findall(r"^对白[^\S\r\n]*[：:][^\S\r\n]*(.*)$", rec, re.MULTILINE)
                if len(fields) > 1:
                    errors.append(f"{group.name}/{path.name}: panel {panel_index} must have only one 对白 field")
                value = fields[0].strip() if fields else ""
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
                            if not allow_legacy:
                                for name, spoken in normalized_dialogue(part):
                                    group_dialogue[dialogue_id].setdefault(group.name, []).append((cue, name, spoken))
                            id_speakers[dialogue_id] = speaker
                            id_seen.add(dialogue_id)
                            unique_dialogue_ids.add(dialogue_id)
                else:
                    # Legacy packages remain readable; they cannot deduplicate cross-shot speech.
                    pass
            if spoken_parts and not id_mode_used:
                warnings.append(f"{group.name}/{path.name}: legacy dialogue without source IDs; cross-shot line count requires manual review")
            spoken_count = len(unique_dialogue_ids) if id_mode_used else len(spoken_parts)
            spoken_words = sum(english_word_count(spoken) for value in dialogue_values
                               for _, spoken in normalized_dialogue(value))
            if spoken_words > MAX_ENGLISH_WORDS:
                errors.append(f"{group.name}/{path.name}: {spoken_words} spoken English words "
                              f"exceed the {MAX_ENGLISH_WORDS}-word limit; regroup at sentence boundaries")

            source_block = read_field_block(content, "跨组对白原文")
            if source_block and not allow_legacy:
                for row in source_block.splitlines():
                    fields = [field.strip() for field in row[2:].split("|", 3)]
                    if not row.startswith("- ") or len(fields) != 4:
                        errors.append(f"{group.name}: invalid 跨组对白原文 row: {row}")
                        continue
                    source_id, speaker, span, original = fields
                    if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", source_id) or not speaker
                            or not re.fullmatch(r"[0-9]+:[0-9]+", span) or not original
                            or group.name in source_rows[source_id]):
                        errors.append(f"{group.name}: invalid or duplicate 跨组对白原文 row: {row}")
                        continue
                    start, end = map(int, span.split(":"))
                    source_rows[source_id][group.name] = (speaker, start, end, original)

            declared_status = read_field_block(content, "分组状态")
            if not declared_status and not allow_legacy:
                errors.append(f"{group.name}/{path.name}: requires non-empty 分组状态")
            tail_status = declared_status or "常规"
            if tail_status not in {"常规", "整集尾组", "对白容量拆组"}:
                errors.append(f"{group.name}/{path.name}: 分组状态 must be 常规, 整集尾组, or 对白容量拆组")
            episode_tail = tail_status == "整集尾组"
            capacity_split = tail_status == "对白容量拆组"
            if capacity_split:
                note = inline_field(content, "对白容量拆组说明") or ""
                evidence = re.fullmatch(r"([0-9]+)\s*\|\s*(.+)", note)
                target = {"1-2句短对白": 8, "1—2句短对白": 8, "1–2句短对白": 8,
                          "三句以上或长对白": 6, "3句以上或长对白": 6}.get(inline_field(content, "对白规格"), 0)
                if (not evidence or int(evidence[1]) <= MAX_ENGLISH_WORDS
                        or not 1 <= spoken_words <= MAX_ENGLISH_WORDS
                        or not 1 <= panel_count < target):
                    errors.append(f"{group.name}/{path.name}: 对白容量拆组 requires a documented over-cap "
                                  "original plan, 1–60 spoken English words, and fewer than the standard panels")

            if episode_tail and group != groups[-1]:
                errors.append(f"{group.name}/{path.name}: 整集尾组 must be the final production group")
            if episode_tail and not read_field_block(content, "尾组说明"):
                errors.append(f"{group.name}/{path.name}: 整集尾组 requires a concrete 尾组说明")

            dialogue_spec_match = re.search(
                r"^对白规格\s*[：:]\s*(.+?)\s*$", content, flags=re.MULTILINE
            )
            if dialogue_spec_match:
                dialogue_spec = dialogue_spec_match.group(1).strip()
                if dialogue_spec == "无对白":
                    if spoken_parts:
                        errors.append(
                            f"{group.name}/{path.name}: 对白规格 says 无对白 but spoken lines are present"
                        )
                    allowed = range(9, 13) if pure_fight else range(9, 11)
                    if pure_fight and (not inline_field(content, "打斗节奏依据") or inline_field(content, "打斗节奏依据") == "无"):
                        errors.append(f"{group.name}/{path.name}: pure fight requires concrete 打斗节奏依据")
                    if not (panel_count in allowed or episode_tail and 1 <= panel_count < 9):
                        band = "9–12" if pure_fight else "9–10"
                        errors.append(f"{group.name}/{path.name}: no-dialogue requires {band} panels, or 1–8 in a documented 整集尾组")
                elif dialogue_spec in {"1-2句短对白", "1—2句短对白", "1–2句短对白"}:
                    # Without legacy source IDs, fragments across cuts cannot be
                    # counted as distinct source lines; the warning above owns review.
                    if not spoken_parts or (id_mode_used and not 1 <= spoken_count <= 2):
                        errors.append(
                            f"{group.name}/{path.name}: 1-2句短对白 group must contain one or two spoken lines"
                        )
                    if not (panel_count == 8 or (episode_tail or capacity_split) and 1 <= panel_count < 8):
                        errors.append(
                            f"{group.name}/{path.name}: 1-2句短对白 requires 8 panels, or 1–7 in a documented 整集尾组/对白容量拆组"
                        )
                elif dialogue_spec in {"三句以上或长对白", "3句以上或长对白"}:
                    if not spoken_parts:
                        errors.append(
                            f"{group.name}/{path.name}: dialogue-heavy/long-dialogue group contains no spoken line"
                        )
                    if not (panel_count == 6 or (episode_tail or capacity_split) and 1 <= panel_count < 6):
                        errors.append(
                            f"{group.name}/{path.name}: three-or-more/long-dialogue requires 6 panels, or 1–5 in a documented 整集尾组/对白容量拆组"
                        )
                else:
                    errors.append(
                        f"{group.name}/{path.name}: 对白规格 must be 无对白, 1-2句短对白, or 三句以上或长对白"
                    )

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
            if len(named_storyboard_counts) != len(storyboards) or any(not 1 <= count <= (8 if allow_legacy else 12) for count in named_storyboard_counts):
                errors.append(f"{group.name}: storyboard filename must declare the actual panel count (1–12 in the current schema); keep one sheet and every pane 16:9")

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
                            f"{group.name}/{path.name}: dialogue must name the Chinese speaker before the English line ({dialogue_part})"
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
                    elif re.search(r"[\u3400-\u9fff]", spoken_line):
                        errors.append(
                            f"{group.name}/{path.name}: spoken dialogue content must remain English with no Chinese translation ({dialogue_part})"
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
            if "故事板不得添加彩色、灰洗或任何色块" in sd2:
                errors.append(f"{group.name}/{sd2_path.name}: workflow-only storyboard restriction must not enter the SD2 prompt")
            if not allow_legacy:
                errors.extend(f"{group.name}/{sd2_path.name}: {error}" for error in sd2_global_constraint_errors(sd2))
            if group_text:
                group_id = inline_field(group_text, "分组") or group.name
                errors.extend(f"{group.name}/{sd2_path.name}: {error}" for error in cross_file_errors(group_text, sd2, group_id))
            forbidden_sd2_fields = (
                "源镜号", "原稿剪辑参考", "对白编号", "对白衔接", "中文参考",
                "对白保全核对", "镜头节奏核对", "空间合理性核对", "群像差异化核对",
                "追击节奏核对", "人物资产分表", "场景局部对应表", "资产清单",
                "主角清单", "主角资产映射", "人物资产表", "人物判定", "内容类型", "打斗节奏依据", "动作辅助标注", "图片预算核对", "场景拼接对应表", "图像验收记录", "资产复用核对", "场景身份判定",
                "ZIP", "CRC",
            )
            annotation_note = read_field_block(group_text, "动作辅助标注") or ""
            if annotation_note and annotation_note != "无":
                if not (any(word in sd2 for word in ("辅助线", "辅助标记", "运动箭头")) and any(word in sd2 for word in ("不进入成片", "不得出现在成片", "不出现在成片", "不生成到视频"))):
                    errors.append(f"{group.name}/{sd2_path.name}: declared motion marks require a public constraint excluding annotations from final video")
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
                if len(re.findall(r"^对白[^\S\r\n]*[：:]", rec, re.MULTILINE)) > 1:
                    errors.append(f"{group.name}/{sd2_path.name}: shot {idx} must have only one 对白 field")
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

    if not allow_legacy:
        pending_file = root / "待制作分镜.txt"
        pending = pending_file.read_text(encoding="utf-8-sig", errors="replace") if pending_file.is_file() else ""
        errors.extend(cross_group_dialogue_errors(group_dialogue, source_rows, groups, pending))
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
                        help="Historical packages only; supports old record layouts")
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
            "MANUAL REVIEW STILL REQUIRED: complete the scope-specific P-QA checklist in references/package-template.md; declarations and byte checks do not prove real scene identities, camera geometry, image plate slots, readable details, character identity, contact anatomy, source-dialogue semantics, or video motion."
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
