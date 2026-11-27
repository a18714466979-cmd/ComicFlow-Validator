"""Lay out approved image windows and bind them to source shot IDs."""

import json
import math
import os
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .asset_registry import sha256_file
from .production_project import checked_name
from .storyboard_preflight import IMAGE_LIMIT


COLORS = {"人物位移": ("蓝", "#245fcd"), "敌方动作": ("红", "#cc343a"), "道具移动": ("橙", "#c36620")}


@dataclass(frozen=True)
class Sheet:
    kind: str
    path: Path
    sha256: str
    slots: dict
    sources: tuple[str, ...]
    shrunken: bool
    padding: bool


@dataclass(frozen=True)
class LayoutDraft:
    signature: str
    mixed: bool
    sheets: tuple[Sheet, ...]


def square_layout(count):
    """Integer squares give exact 16:9 windows after scaling both axes."""
    if count == 1:
        return 1, [(0, 0, 1)]
    if 2 <= count <= 4:
        return 2, [(i % 2, i // 2, 1) for i in range(count)]
    if count in (5, 6):
        return 3, [(0, 0, 2), (2, 0, 1), (2, 1, 1), (0, 2, 1), (1, 2, 1), (2, 2, 1)][:count]
    if count in (7, 10):
        slots = [(0, 0, 2), (2, 0, 2), (0, 2, 2)]
        if count == 10:
            slots[2:] = [(x, y, 1) for y in (2, 3) for x in (0, 1)]
        return 4, slots + [(x, y, 1) for y in (2, 3) for x in (2, 3)]
    if count in (8, 11):
        slots = [(0, 0, 3), (3, 0, 2), (3, 2, 1), (4, 2, 1), (0, 3, 2), (2, 3, 2), (4, 3, 1), (4, 4, 1)]
        if count == 11:
            slots[5:6] = [(x, y, 1) for y in (3, 4) for x in (2, 3)]
        return 5, slots
    if count == 9:
        return 3, [(i % 3, i // 3, 1) for i in range(9)]
    if count == 12:
        return 6, [(i % 3 * 2, i // 3 * 2, 2) for i in range(8)] + [
            (x, y, 1) for y in (4, 5) for x in (4, 5)]
    raise ValueError("请为一组选择 1 至 12 个实际画面格。")


def valid_box(box, size):
    return (isinstance(box, (list, tuple)) and len(box) == 4 and all(type(value) is int for value in box)
            and 0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1])


def exact_box(box):
    return (box[2] - box[0]) * 9 == (box[3] - box[1]) * 16


def bind_window(project, project_path, shot_id, kind, image_id, region=None):
    if kind not in ("board", "plate") or shot_id not in {shot.id for shot in project.shots}:
        raise ValueError("请选择当前组实际镜头和绑定用途。")
    image = next((item for item in project.images if item.id == image_id), None)
    if image is None:
        raise ValueError("请选择已批准的原图。")
    name = image.filename.lower()
    if kind == "plate" and any(token in name for token in ("storyboard", "_main_", "_reverse_")):
        raise ValueError("逐镜净板须使用批准的同用途净板。")
    if kind == "board" and any(token in name for token in ("_details", "场景合辑", "_main_", "_reverse_")):
        raise ValueError("故事板须使用同镜的黑白板格。")
    project.checked_image(project_path, image)
    size = image.width, image.height
    box = region or (0, 0, *size)
    if not valid_box(box, size):
        raise ValueError("请在原图内框选实际画面。")
    if region is None and not exact_box(box):
        raise ValueError("原图整幅并非精确 16:9，请框选实际有效画面。")
    x, y, right, bottom = box
    units = min((right - x) // 16, (bottom - y) // 9)
    if units < 1:
        raise ValueError("选区过小。")
    x += (right - x - 16 * units) // 2
    y += (bottom - y - 9 * units) // 2
    box = (x, y, x + 16 * units, y + 9 * units)
    row = project.layout.setdefault("inputs", {}).setdefault(shot_id, {})
    row[kind] = {"image": image.id, "sha256": image.digest, "box": list(box)}
    repins = project.layout.get("rebind", {})
    if kind in repins.get(shot_id, []):
        repins[shot_id].remove(kind)
        if not repins[shot_id]:
            del repins[shot_id]
    if kind == "board":
        row.pop("marks", None)
    return box


def add_mark(project, shot_id, color, target, start, end):
    row = project.layout.get("inputs", {}).get(shot_id, {})
    box = row.get("board", {}).get("box")
    if not box or color not in COLORS or not target.strip() or any(char in target for char in "|\n\r"):
        raise ValueError("请先绑定故事板格，再填写运动对象和标注类别。")
    if any(not (box[0] <= x < box[2] and box[1] <= y < box[3]) for x, y in (start, end)) or start == end:
        raise ValueError("箭头两端须位于同一格内且不同。")
    row.setdefault("marks", []).append({"color": color, "target": target.strip(), "start": list(start), "end": list(end)})


def layout_signature(project):
    inputs = project.layout.get("inputs", {})
    data = [(shot.id, shot.source, shot.anchor, shot.scene, shot.plate_note, inputs.get(shot.id))
            for shot in project.shots]
    return sha256(json.dumps([project.group, data], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@lru_cache(maxsize=24)
def layout_font(size):
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for path in [*(windows / name for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc", "YuGothM.ttc")),
                 Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), Path("/System/Library/Fonts/PingFang.ttc")]:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    raise ValueError("排版中文标签需要系统中文字体，例如微软雅黑、宋体或 Noto Sans CJK。")


def caption(draw, x, text, font):
    _, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    pad = max(2, font.size // 5)
    draw.rectangle((x, 0, x + right + 2 * pad, bottom - top + 2 * pad), fill="#20252b")
    draw.text((x + pad, pad - top), text, font=font, fill="white")


def annotate(tile, name, markers, box):
    draw = ImageDraw.Draw(tile)
    font = layout_font(max(8, min(30, tile.height // 17)))
    caption(draw, 0, name, font)
    for marker in markers:
        start, end = [((x - box[0]) * tile.width / (box[2] - box[0]), (y - box[1]) * tile.height / (box[3] - box[1]))
                      for x, y in (marker["start"], marker["end"])]
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        line = max(2, round(tile.height / 145))
        head = min(line * 6, math.dist(start, end) / 2)
        color = COLORS[marker["color"]][1]
        draw.line((start, end), fill=color, width=line)
        draw.polygon([end, *((end[0] - head * math.cos(angle + side), end[1] - head * math.sin(angle + side))
                             for side in (-0.48, 0.48))], fill=color)


def old_visuals(project):
    composite = project.notes.get("场景拼接对应表", "")
    details = {cells[2].strip() for row in composite.splitlines() if len(cells := row.split("|")) == 4
               and cells[1].strip() == "details"}
    return [item for item in project.images if not item.reference_only and (
        "storyboard" in item.filename.lower() or "_details" in item.filename.lower()
        or item.filename in details or any(shot.plate == item.id for shot in project.shots))]


def detail_pages(project, mixed, limit):
    places = {}
    for number, shot in enumerate(project.shots, 1):
        if not shot.scene.strip() or any(char in shot.scene for char in "|；;、，,\r\n"):
            raise ValueError(f"第 {number} 镜请填写单一实际地点。")
        places.setdefault(shot.scene, []).append((number, shot))
    if mixed:
        if len(places) < 2:
            raise ValueError("多场景局部用于实际跨地点的镜头。")
        places = {"多场景局部": list(enumerate(project.shots, 1))}
        limit = min(3, limit)

    def pages(padded):
        rows = []
        for name, shots in places.items():
            groups = [shots[index:index + 4] for index in range(0, len(shots), 4)]
            if not padded and len(groups[-1]) in (2, 3):
                groups.extend([item] for item in groups.pop())
            rows.extend((checked_name(f"scene_{name}_details_{n:02d}_16x9.png"), group)
                        for n, group in enumerate(groups, 1))
        return rows

    result = pages(False)
    if len(result) > limit:
        result = pages(True)
    if len(result) > limit:
        raise ValueError("净板排版将超过本组图数；请核对多场景合辑或在连贯位置分组。")
    return result


def render_layout(project, project_path, directory, mixed=False):
    if not project.shots:
        raise ValueError("没有可排版的正式镜头。")
    if any(shot.id in project.layout.get("rebind", {}) for shot in project.shots):
        raise ValueError("请先重新绑定已返修的最新批准窗口。")
    inputs = project.layout.get("inputs", {})
    images = {asset.id: asset for asset in project.images}
    paths, used = {}, {"board": set(), "plate": set()}
    count = sum(not item.reference_only for item in project.images) - len(old_visuals(project))
    pages = detail_pages(project, mixed, IMAGE_LIMIT - count - 1)
    for number, shot in enumerate(project.shots, 1):
        for kind, title in (("board", "故事板格"), ("plate", "净板")):
            source = inputs.get(shot.id, {}).get(kind, {})
            image = images.get(source.get("image"))
            box = source.get("box")
            if (not image or image.digest != source.get("sha256") or not valid_box(box, (image.width, image.height))
                    or not exact_box(box)):
                raise ValueError(f"{project.group}-{number:02d} 缺少有效的批准{title}绑定。")
            identity = image.digest, tuple(box)
            if identity in used[kind]:
                raise ValueError(f"两镜指向同一{title}窗口，请为每镜选择独立实际画面。")
            used[kind].add(identity)
            if image.id not in paths:
                paths[image.id] = project.checked_image(project_path, image)

    def sheet(filename, kind, shots):
        side, slots = square_layout(len(shots))
        source = [inputs[shot.id][kind] for _, shot in shots]
        colors = {mark["color"] for _, shot in shots for mark in inputs[shot.id].get("marks", [])} if kind == "board" else set()
        units = min((465 if colors else 470) // side, *((item["box"][2] - item["box"][0]) // (16 * size)
                                  for item, (_, _, size) in zip(source, slots)))
        if not units:
            raise ValueError(f"{filename} 存在过小的批准窗口。")
        width, height = 16 * units, 9 * units
        coordinates, resized = {}, False
        legend = " / ".join(f"{COLORS[key][0]} {key}" for key in COLORS if key in colors)
        header = 0
        if legend:
            legend_font = layout_font(max(8, min(24, height // 9)))
            _, top, right, bottom = legend_font.getbbox(legend)
            header = math.ceil((bottom - top + 2 * max(2, legend_font.size // 5)) / 9)
            if right + 2 * max(2, legend_font.size // 5) > side * width:
                raise ValueError("板面分辨率不足以容纳已选运动图例。")
        canvas = Image.new("RGB", (side * width + 16 * header, side * height + 9 * header),
                           "#f6f6f6" if kind == "board" else "#282828")
        if legend:
            caption(ImageDraw.Draw(canvas), 8 * header, legend, legend_font)
        for (number, shot), data, (x, y, span) in zip(shots, source, slots):
            origin = (x * width + 8 * header, y * height + 9 * header)
            with Image.open(paths[data["image"]]) as full:
                tile = full.crop(tuple(data["box"]))
            if tile.convert("RGBA").getchannel("A").getextrema()[0] != 255:
                raise ValueError(f"第 {number} 镜的批准窗口含透明像素。")
            tile = tile.convert("RGB")
            if tile.size != (width * span, height * span):
                tile = tile.resize((width * span, height * span), Image.Resampling.LANCZOS)
                resized = True
            label = f"{number:02d}" if kind == "board" else f"局部{number:02d} · {shot.scene}"
            changes = inputs[shot.id].get("marks", []) if kind == "board" else []
            annotate(tile, label, changes, data["box"])
            canvas.paste(tile, origin)
            coordinates[shot.id] = (*origin, origin[0] + tile.width, origin[1] + tile.height)
        path = directory / filename
        canvas.save(path, format="PNG")
        return Sheet(kind, path, sha256_file(path), coordinates, tuple(dict.fromkeys(item["image"] for item in source)),
                     resized, sum(span**2 for _, _, span in slots) != side**2)

    sheets = [sheet(f"storyboard_{len(project.shots)}panel_bw_16x9.png", "board", list(enumerate(project.shots, 1)))]
    sheets.extend(sheet(filename, "plate", shots) for filename, shots in pages)
    return LayoutDraft(layout_signature(project), mixed, tuple(sheets))


def apply_layout(project, project_path, draft, inspection):
    if draft.signature != layout_signature(project):
        raise ValueError("镜头或选区已变更，请重新预览。")
    if not inspection.strip() or any(char in inspection for char in "|\r\n"):
        raise ValueError("请填写单行实际核图记录。")
    assets = {item.id: item for item in project.images}
    for sheet in draft.sheets:
        for identity in sheet.sources:
            project.checked_image(project_path, assets[identity])
        if sheet.sha256 != sha256_file(sheet.path):
            raise ValueError("排版预览文件已变化。")
    archived = old_visuals(project)
    names = {sheet.path.name.casefold() for sheet in draft.sheets}
    retired = archived + [item for item in project.images if item.reference_only and item.filename.casefold() in names]
    original = project.images[:], dict(project.notes), project.layout.get("output"), [shot.plate for shot in project.shots]
    try:
        for asset in retired:
            name = f"排版前_{asset.id[:12]}_{asset.filename}" if asset.filename.casefold() in names else asset.filename
            project.images[project.images.index(asset)] = replace(asset, filename=name, reference_only=True)
        records = []
        for sheet in draft.sheets:
            asset = project.import_image(project_path, sheet.path, sheet.path.name, action="必要规范排版",
                                         reason="按批准窗口逐镜重排并添加实际编号", inspection=inspection,
                                         originals=sheet.sources, origin_label=f"本地排版 {sheet.sha256}")
            records.append({"kind": sheet.kind, "asset": asset.id, "slots": {key: list(box) for key, box in sheet.slots.items()}})
            if sheet.kind == "plate":
                for shot in project.shots:
                    if shot.id in sheet.slots:
                        shot.plate = asset.id
        project.notes["场景资产模式"] = "多场景局部" if draft.mixed else "常规"
        project.notes["场景清单"] = "；".join(dict.fromkeys(shot.scene for shot in project.shots))
        dropped = {item.filename for item in archived}
        if composite := project.notes.get("场景拼接对应表"):
            project.notes["场景拼接对应表"] = "\n".join(
                row for row in composite.splitlines() if not (len(cells := row.split("|")) == 4 and cells[2].strip() in dropped))
        if inventory := project.notes.get("资产清单"):
            keep = [row for row in inventory.splitlines() if row.removeprefix("- ").split("|", 1)[0].strip() not in dropped]
            project.notes["资产清单"] = "\n".join(keep + [f"- {sheet.path.name} | 必要规范排版" for sheet in draft.sheets])
        project.layout["output"] = {"signature": draft.signature, "sheets": records}
        project.save(project_path)
    except Exception:
        project.images, project.notes, output, plates = original
        if output is None:
            project.layout.pop("output", None)
        else:
            project.layout["output"] = output
        for shot, plate in zip(project.shots, plates):
            shot.plate = plate
        raise


def windows_for_shots(project, formal=None):
    output = project.layout.get("output")
    if not output:
        return {}
    if output["signature"] != layout_signature(project):
        raise ValueError("镜头、窗口或标注已变化，请重新排版复核。")
    formal = formal if formal is not None else {item.id: item for item in project.images if not item.reference_only}
    mapped = {shot.id: {} for shot in project.shots}
    for sheet in output["sheets"]:
        asset, kind = formal.get(sheet["asset"]), sheet["kind"]
        if not asset or kind not in ("board", "plate"):
            raise ValueError("正式排版图已替换或移除，请重新确认实际窗口。")
        occupied = []
        for identity, box in sheet["slots"].items():
            if (identity not in mapped or kind in mapped[identity] or not valid_box(box, (asset.width, asset.height))
                    or not exact_box(box) or any(overlap(box, used) for used in occupied)):
                raise ValueError(f"{asset.filename} 的实际窗口坐标无效或重叠。")
            occupied.append(box)
            mapped[identity][kind] = (asset, tuple(box))
    if any(set(mapped[shot.id]) != {"board", "plate"} or mapped[shot.id]["plate"][0].id != shot.plate for shot in project.shots):
        raise ValueError("实际排版窗口与镜头净板绑定不一致。")
    return mapped


def mark_ledger(project):
    rows = []
    for number, shot in enumerate(project.shots, 1):
        values = [f"{COLORS[item['color']][0]} {item['color']} {item['target']} {tuple(item['start'])}→{tuple(item['end'])}"
                  for item in project.layout["inputs"][shot.id].get("marks", [])]
        rows.append((f"- {project.group}-{number:02d} | ", values))
    return "\n".join(label + ("；".join(text) or "无") for label, text in rows) if any(text for _, text in rows) else "无"


def overlap(first, second):
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(first[3], second[3])


def replace_laid_out_asset(project, original, revised, edited_box):
    for sheet in project.layout.get("output", {}).get("sheets", []):
        if sheet["asset"] != original.id:
            continue
        if (original.width, original.height) != (revised.width, revised.height):
            raise ValueError("局部返修后的画布须保留原排版大小。")
        sheet["asset"] = revised.id
        for identity, box in sheet["slots"].items():
            if overlap(box, edited_box):
                rows = project.layout.setdefault("rebind", {}).setdefault(identity, [])
                if sheet["kind"] not in rows:
                    rows.append(sheet["kind"])
