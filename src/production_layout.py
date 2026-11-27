"""Lay out approved image windows and bind them to source shot IDs."""

import json
import math
import os
import re
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from .asset_registry import sha256_file
from .production_project import checked_name
from .production_rules import CHINESE
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
    cells: tuple = ()


@dataclass(frozen=True)
class LayoutDraft:
    signature: str
    mixed: bool
    sheets: tuple[Sheet, ...]
    chinese: dict | None = None
    keep_views: tuple[str, ...] = ()
    retire_views: tuple[str, ...] = ()


@dataclass(frozen=True)
class Cell:
    image: str
    box: tuple[int, int, int, int]
    label: str
    shots: tuple[str, ...]
    marks: tuple = ()
    view: tuple[str, str] | None = None
    slot: str = ""


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
    if kind == "plate" and "scene_九图合并_" in name:
        cell = next((cell for sheet in project.layout.get("output", {}).get("sheets", [])
                     if sheet["asset"] == image.id for cell in sheet.get("cells", ())
                     if shot_id in cell["shots"] and list(region or ()) == cell["box"]), None)
        if cell is None:
            raise ValueError("九图场景合图只可重绑该镜记录的净板窗口。请用批准原图或精确框选原局部。")
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
    payload = [project.group, data]
    if project.rules == CHINESE:
        payload.append([(shot.fields.get("机位空间", ""), shot.fields.get("可见范围", "")) for shot in project.shots])
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@lru_cache(maxsize=24)
def layout_font(size):
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for path in [*(windows / name for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc", "YuGothM.ttc")),
                 Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), Path("/System/Library/Fonts/PingFang.ttc")]:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    raise ValueError("排版中文标签需要系统中文字体，例如微软雅黑、宋体或 Noto Sans CJK。")


def caption(draw, x, text, font, y=0):
    _, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    pad = max(2, font.size // 5)
    draw.rectangle((x, y, x + right + 2 * pad, y + bottom - top + 2 * pad), fill="#20252b")
    draw.text((x + pad, y + pad - top), text, font=font, fill="white")


def annotate(tile, name, markers, box):
    draw = ImageDraw.Draw(tile)
    if name:
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
        or "scene_九图合并_" in item.filename
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


SCENE_VIEW = re.compile(r"^(?:\d+_)?scene_(.+)_(main|reverse)_16x9\.png$", re.I)


def chinese_scene_views(project, project_path, places, mixed, paths):
    available = {}
    formal = []
    for image in project.images:
        match = SCENE_VIEW.fullmatch(image.filename)
        if match:
            scene, kind = match[1], match[2].lower()
            available.setdefault((scene, kind), []).append(image)
            if not image.reference_only:
                formal.append(image.id)
    if mixed:
        return {}, (), tuple(formal)
    views = {}
    for place in places:
        pair = []
        for kind, caption_text in (("main", "正打"), ("reverse", "反打")):
            matches = available.get((place, kind), [])
            selected = [image for image in matches if not image.reference_only] or matches
            if len(selected) != 1:
                raise ValueError(f"{place} 需要一张明确批准的{caption_text}，文件名用 scene_{place}_{kind}_16x9.png。")
            asset = selected[0]
            path = project.checked_image(project_path, asset)
            with Image.open(path) as original:
                if not exact_box((0, 0, original.width, original.height)):
                    raise ValueError(f"{asset.filename} 的完整画面需要 16:9。")
                if original.convert("RGBA").getchannel("A").getextrema()[0] != 255:
                    raise ValueError(f"{asset.filename} 含透明像素。")
            paths[asset.id] = path
            pair.append(Cell(asset.id, (0, 0, asset.width, asset.height), f"{place} · {caption_text}", (),
                             view=(place, kind)))
        with Image.open(paths[pair[0].image]) as main, Image.open(paths[pair[1].image]) as reverse:
            if main.size == reverse.size:
                first, second = main.convert("RGB"), reverse.convert("RGB")
                if (ImageChops.difference(first, second).getbbox() is None
                        or ImageChops.difference(ImageOps.mirror(first), second).getbbox() is None):
                    raise ValueError(f"{place} 的正打与反打相同或只是水平镜像，请导入批准的真反打。")
        views[place] = pair
    keep = tuple(cell.image for pair in views.values() for cell in pair)
    return views, keep, tuple(identity for identity in formal if identity not in keep)


def collect_cells(project, paths, project_path):
    inputs = project.layout.get("inputs", {})
    assets = {asset.id: asset for asset in project.images}
    used_boards = set()
    boards, plates = [], {}
    seen = {}
    chinese = project.rules == CHINESE
    for number, shot in enumerate(project.shots, 1):
        row = inputs.get(shot.id, {})
        for kind, title in (("board", "故事板格"), ("plate", "净板")):
            data = row.get(kind, {})
            image = assets.get(data.get("image"))
            box = data.get("box")
            if (not image or image.digest != data.get("sha256") or not valid_box(box, (image.width, image.height))
                    or not exact_box(box)):
                raise ValueError(f"{project.group}-{number:02d} 缺少有效的批准{title}绑定。")
            if image.id not in paths:
                paths[image.id] = project.checked_image(project_path, image)
            identity = image.digest, tuple(box)
            if kind == "board":
                if identity in used_boards:
                    raise ValueError("两镜指向同一故事板格窗口，请分别绑定实际画面。")
                used_boards.add(identity)
                boards.append(Cell(image.id, tuple(box), f"{number:02d}", (shot.id,), tuple(row.get("marks", ()))))
                continue
            if chinese and (not shot.scene.strip() or any(char in shot.scene for char in "|；;、，,/\\：:\r\n")):
                raise ValueError(f"第 {number} 镜请填写单一实际地点。")
            place_cells = plates.setdefault(shot.scene, [])
            camera = (shot.scene, shot.fields.get("机位空间", "").strip(), shot.fields.get("可见范围", "").strip())
            if identity in seen:
                old_camera, first_slot = seen[identity]
                if not chinese or old_camera != camera or not all(camera):
                    raise ValueError("两镜共用净板时，须是同一地点、机位、可见范围和批准画面。")
                cell = place_cells[first_slot]
                place_cells[first_slot] = replace(cell, shots=(*cell.shots, shot.id))
                continue
            seen[identity] = (camera, len(place_cells))
            slot = f"局部{len(seen) if chinese else number:02d}"
            place_cells.append(Cell(image.id, tuple(box), f"{slot} · {shot.scene}", (shot.id,),
                                    view=(shot.scene, "details"), slot=slot))
    return boards, plates


def chinese_layout_plan(project, project_path, paths, boards, plates, mixed, pack_scenes, pack_board, budget_note):
    if len(boards) > 10:
        raise ValueError("中文故事板每组最多 10 格。")
    if mixed and len(plates) < 2:
        raise ValueError("多场景局部模式需要两个或以上实际独立地点。")
    views, keep, retire = chinese_scene_views(project, project_path, plates, mixed, paths)
    if mixed:
        all_plates = sorted((cell for cells in plates.values() for cell in cells), key=lambda cell: cell.slot)
        page_count = math.ceil(len(all_plates) / 4)
        step, extra = divmod(len(all_plates), page_count)
        pages = []
        start = 0
        for index in range(page_count):
            end = start + step + (index < extra)
            pages.append((f"scene_多场景局部_details_{index + 1:02d}_16x9.png", all_plates[start:end]))
            start = end
    else:
        pages = [(checked_name(f"scene_{place}_details_16x9.png"), cells) for place, cells in plates.items()]
    board_pages = [boards[:6], boards[6:]] if len(boards) == 10 else [boards]
    archived = {asset.id for asset in old_visuals(project)} | set(retire) | set(keep)
    fixed = sum(not asset.reference_only and asset.id not in archived for asset in project.images)
    initial = fixed + len(pages) + len(keep) + len(board_pages)
    scene_count, mode = len(pages) + len(keep), "多场景局部" if mixed else "常规"
    source_mode = mode
    required_steps = ("道具", "配角", "主角", "主配")
    if pack_scenes or pack_board:
        if initial <= IMAGE_LIMIT:
            raise ValueError(f"当前方案为 {initial}/{IMAGE_LIMIT} 张，保留常规排版。")
        if not budget_note.strip() or "\n" in budget_note or "\r" in budget_note:
            raise ValueError("请填写单行九图优化记录，说明前序的实际处理与未合并理由。")
        required = (*required_steps, "场景") if pack_board and not pack_scenes else required_steps
        if any(not re.search(rf"(?:^|[；;])\s*{label}[：:]\s*[^；;\s]", budget_note) for label in required):
            raise ValueError(f"九图优化记录须逐项填写 {'、'.join(required)} 的实际处理或跳过理由。")
        if "原始总图数" in budget_note or "最终总图数" in budget_note:
            raise ValueError("原始及最终图数由软件重算，请只填写处理经过。")
    if pack_scenes:
        cells = [cell for place, local in plates.items() for cell in (*views.get(place, ()), *local)]
        packed_pages = [(f"scene_九图合并_{index // 4 + 1:02d}_16x9.png", cells[index:index + 4])
                        for index in range(0, len(cells), 4)]
        if len(packed_pages) >= scene_count:
            raise ValueError("现有场景视图合并后不减图。请保留实际视图，记录原因后继续核对。")
        pages, retire, keep = packed_pages, (*retire, *keep), ()
        scene_count, mode = len(pages), "九图合并"
    count = fixed + scene_count + len(board_pages)
    if pack_board:
        if len(board_pages) != 2 or count <= IMAGE_LIMIT:
            raise ValueError(f"仅在前序优化后仍超九图的 10 格组可合成一张板。当前 {count} 张。")
        board_pages = [boards]
        count -= 1
    if count > IMAGE_LIMIT:
        raise ValueError(f"本组按实际排版为 {count} 张，超过九图上限。请按道具、配角、主角、主配、场景、故事板顺序优化。")
    stages = [f"场景：{len(plates)} 个地点，采用{mode}，交 {scene_count} 张",
              f"故事板：{'九图合并' if pack_board else '常规'}，交 {len(board_pages)} 张"]
    if not pack_scenes and pack_board:
        stages[0] = f"场景图 {scene_count} 张"
    prior = budget_note.strip().rstrip("；;") + "；" if pack_scenes or pack_board else ""
    audit = (f"原始总图数={initial}（故事板 {2 if len(boards) == 10 else 1} 张、"
             f"场景 {initial - fixed - (2 if len(boards) == 10 else 1)} 张、其他批准图 {fixed} 张）；"
             f"{prior}{'；'.join(stages)}；最终总图数={count}；"
             f"{'实际触发九图优化' if pack_scenes or pack_board else '本次排版未触发九图优化'}")
    metadata = {"mode": mode, "source_mode": source_mode, "board_mode": "九图合并" if pack_board else "常规",
                "budget": audit, "count": count, "options": [pack_scenes, pack_board, budget_note]}
    return board_pages, pages, metadata, keep, retire


def render_sheet(directory, filename, kind, cells, paths, external_labels=False):
    side, slots = square_layout(len(cells))
    colors = {mark["color"] for cell in cells for mark in cell.marks}
    gutter = 3 if external_labels else 0
    units = min((465 if colors else 470) // side - gutter,
                *((cell.box[2] - cell.box[0]) // (16 * span) - gutter
                  for cell, (_, _, span) in zip(cells, slots)))
    if units < 1:
        raise ValueError(f"{filename} 存在过小的批准窗口。")
    width, height = 16 * (units + gutter), 9 * (units + gutter)
    coordinates, resized, rendered_cells = {}, False, []
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
    draw = ImageDraw.Draw(canvas)
    if legend:
        caption(draw, 8 * header, legend, legend_font)
    for cell, (x, y, span) in zip(cells, slots):
        centered_x = width // 2 if external_labels and len(cells) == 3 and y == 1 else 0
        centered_y = height // 2 if external_labels and len(cells) == 2 else 0
        origin = (x * width + 8 * header + centered_x, y * height + 9 * (header + gutter) + centered_y)
        size = width * span - 16 * gutter, height * span - 9 * gutter
        with Image.open(paths[cell.image]) as full:
            tile = full.crop(cell.box).convert("RGBA")
        if tile.getchannel("A").getextrema()[0] != 255:
            raise ValueError(f"{filename} 的 {cell.label} 批准窗口含透明像素。")
        tile = tile.convert("RGB")
        if tile.size != size:
            tile = tile.resize(size, Image.Resampling.LANCZOS)
            resized = True
        if external_labels:
            font = layout_font(max(8, min(15, size[1] // 17)))
            _, top, right, bottom = font.getbbox(cell.label)
            pad = max(2, font.size // 5)
            if right + 2 * pad > size[0] or bottom - top + 2 * pad >= 9 * gutter:
                raise ValueError(f"{filename} 的标签空间不足，请使用清晰原图和精简地点名。")
            caption(draw, origin[0], cell.label, font, origin[1] - 9 * gutter)
        annotate(tile, "" if external_labels else cell.label, cell.marks, cell.box)
        canvas.paste(tile, origin)
        box = (*origin, origin[0] + tile.width, origin[1] + tile.height)
        coordinates.update((shot, box) for shot in cell.shots)
        if external_labels:
            rendered_cells.append({"box": list(box), "view": list(cell.view) if cell.view else None,
                                   "slot": cell.slot, "shots": list(cell.shots)})
    path = directory / filename
    canvas.save(path, format="PNG")
    return Sheet(kind, path, sha256_file(path), coordinates, tuple(dict.fromkeys(cell.image for cell in cells)),
                 resized, sum(span**2 for _, _, span in slots) != side**2, tuple(rendered_cells))


def render_layout(project, project_path, directory, mixed=False, *, pack_scenes=False, pack_board=False, budget_note=""):
    if not project.shots:
        raise ValueError("没有可排版的正式镜头。")
    if any(shot.id in project.layout.get("rebind", {}) for shot in project.shots):
        raise ValueError("请先重新绑定已返修的最新批准窗口。")
    paths = {}
    boards, plates = collect_cells(project, paths, project_path)
    chinese = project.rules == CHINESE
    if chinese:
        board_pages, pages, metadata, keep, retire = chinese_layout_plan(
            project, project_path, paths, boards, plates, mixed, pack_scenes, pack_board, budget_note
        )
    else:
        count = sum(not asset.reference_only for asset in project.images) - len(old_visuals(project))
        by_shot = {cell.shots[0]: cell for cells in plates.values() for cell in cells}
        pages = [(name, [by_shot[shot.id] for _, shot in page])
                 for name, page in detail_pages(project, mixed, IMAGE_LIMIT - count - 1)]
        board_pages, metadata, keep, retire = [boards], None, (), ()
    sheets = []
    for index, cells in enumerate(board_pages, 1):
        start = f"_{index:02d}" if len(board_pages) > 1 else ""
        name = f"storyboard{start}_{len(cells)}panel_bw_16x9.png"
        sheets.append(render_sheet(directory, name, "board", cells, paths, chinese))
    sheets.extend(render_sheet(directory, name, "plate", cells, paths, chinese) for name, cells in pages)
    return LayoutDraft(layout_signature(project), mixed, tuple(sheets), metadata, keep, retire)


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
    if draft.chinese:
        retire = set(draft.retire_views)
        keep = set(draft.keep_views)
        archived = [asset for asset in project.images if asset in archived or asset.id in retire]
        if not keep <= assets.keys():
            raise ValueError("已核对的场景图被移除，请重新排版。")
        kept_count = sum(asset.id in keep or not asset.reference_only and asset not in archived
                         for asset in project.images)
        if kept_count + len(draft.sheets) != draft.chinese["count"]:
            raise ValueError("批准图数量已变化，请重新计算九图预算。")
    names = {sheet.path.name.casefold() for sheet in draft.sheets}
    retired = archived + [item for item in project.images if item.reference_only and item.filename.casefold() in names]
    original = project.images[:], dict(project.notes), project.layout.get("output"), [shot.plate for shot in project.shots]
    try:
        for asset in retired:
            name = f"排版前_{asset.id[:12]}_{asset.filename}" if asset.filename.casefold() in names else asset.filename
            project.images[project.images.index(asset)] = replace(asset, filename=name, reference_only=True)
        for identity in draft.keep_views:
            asset = assets[identity]
            project.checked_image(project_path, asset)
            project.images[project.images.index(asset)] = replace(asset, reference_only=False)
        records = []
        for sheet in draft.sheets:
            asset = project.import_image(project_path, sheet.path, sheet.path.name, action="必要规范排版",
                                         reason="按批准窗口逐镜重排并添加实际编号", inspection=inspection,
                                         originals=sheet.sources, origin_label=f"本地排版 {sheet.sha256}")
            record = {"kind": sheet.kind, "asset": asset.id, "slots": {key: list(box) for key, box in sheet.slots.items()}}
            if sheet.cells:
                record["cells"] = list(sheet.cells)
            records.append(record)
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
        if draft.chinese:
            project.notes["场景资产模式"] = draft.chinese["mode"]
            project.layout["output"]["chinese"] = {**draft.chinese, "inspection": inspection,
                                                   "scene_views": list(draft.keep_views)}
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
        shareable = set()
        if project.rules == CHINESE and kind == "plate":
            shareable = {(identity, tuple(cell["box"])) for cell in sheet.get("cells", [])
                         for identity in cell["shots"]}
        for identity, box in sheet["slots"].items():
            if identity not in mapped or kind in mapped[identity] or not valid_box(box, (asset.width, asset.height)) or not exact_box(box):
                raise ValueError(f"{asset.filename} 的实际窗口坐标无效。")
            conflicts = any(overlap(box, used) and (
                tuple(box) != tuple(used) or (identity, tuple(box)) not in shareable
                or (owner, tuple(used)) not in shareable
            ) for owner, used in occupied)
            if conflicts:
                raise ValueError(f"{asset.filename} 的实际窗口重叠。")
            occupied.append((identity, box))
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
