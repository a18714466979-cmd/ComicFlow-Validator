"""Render both storyboarding records from one project, then use strict delivery validation."""

import json
import re
from collections import defaultdict
from pathlib import Path
from shutil import copyfile, copyfileobj
from tempfile import TemporaryDirectory

from .asset_registry import AssetRegistry, sha256_file
from .camera_preflight import boundary_camera_cuts, camera_findings_text, require_camera_rules
from .production_dialogue import handoff_rows
from .production_handoff import active_scope, adjacent, boundary_report, pending_record, reviewed_boundary
from .production_images import provenance_rows
from .production_layout import exact_box, mark_ledger, overlap, valid_box, windows_for_shots
from .production_project import (
    CHINESE_CHARACTER_FIELDS, CHINESE_TEXT_FIELDS, CHINESE_TEXT_OPTIONAL, GROUP_FIELDS, GROUP_OPTIONAL, OPTIONAL_SHOT_FIELDS,
    PARENT_SHOT_FIELD, PROMPT_FIELDS, SHOT_FIELDS, ProductionProject,
)
from .production_rules import CAMERA_ACTION_FIELD, CHINESE, ENGLISH, rule_revision
from .repair_package import pack_repair, write_delivery_zip
from .storyboard_preflight import CHINESE_SPEECH_LIMIT, IMAGE_LIMIT, chinese_speech_length, plan_dialogue


COLOR = "黑白故事板仅作镜头、构图、站位和动作参考；成片按本组实际交付的彩色资产上色，禁止黑白、灰度或线稿成片。"
ENGLISH_COLOR = ("16:9 彩色真人电影。黑白线稿只管机位、构图、站位与动作；颜色、材质、光影用对应彩色参考。"
                 "禁止黑白、灰度和线稿成片。")
LANGUAGE = "成片画面、标牌、界面及拟声字禁止中文，仅允许英文或通用符号。无配乐、无字幕。"
CHINESE_LANGUAGE = "成片字幕、标牌、UI/HUD、系统提示和拟声字允许中文，按本剧已批准文案呈现。参考标签仅用于制作定位。"
MARKS = "故事板的彩色辅助线、箭头、序号和图例仅作动作参考，不得出现在成片中。"
ENGLISH_COMMON = ("一个格号对应一个镜头。按对应格的实际景别和观察角度取景，跨切保持视线、站位和动作阶段。"
                  "只出现指定人物，保持方向、持物手、伤势和设备状态。"
                  "原说话人发声，听者不代说，跨镜续声不从头重念。"
                  "辅助线、标注、运动箭头、格号和参考图标签不得出现在成片。")
ENGLISH_SCENE_PREFIX = re.compile(r"^@图\s*\d+\s*的局部\s*\d+。\s*地点「[^」]+」。\s*")
ENGLISH_REFERENCE_PREFIX = re.compile(r"^\d+_")
ENGLISH_SCENE_VIEW = re.compile(r"^scene_(.+)_(main|reverse)_16x9$", re.IGNORECASE)
ENGLISH_PROP_NAME = re.compile(r"^(?:props(?:_hud)?|hud|interface_overlay)_?(.*?)_16x9$", re.IGNORECASE)
PRODUCTION_SHOT_FIELDS = tuple(key for key in SHOT_FIELDS if key not in OPTIONAL_SHOT_FIELDS)
CHINESE_REQUIRED_REVIEWS = (
    "组间镜头衔接核对", "景别衔接核对", "主角判定", "武器轴线核对",
    "镜头节奏核对", "空间合理性核对", "群像差异化核对", "追击节奏核对",
)


def format_fields(values: dict[str, str], fields: tuple[str, ...], optional=()) -> str:
    pairs = []
    for key in fields:
        value = values.get(key, "").strip()
        if not value:
            if key in optional:
                continue
            raise ValueError(f"请填写「{key}」。")
        if "\n" in value:
            rows = value.splitlines()
            if any(not re.match(r"^[-*•]\s+\S", row) for row in rows[1:]):
                raise ValueError(f"「{key}」的续行请使用「- 」列表。")
            value = ("\n" if re.match(r"^[-*•]\s", rows[0]) else "") + value
        elif re.match(r"^[-*•]\s", value):
            value = "\n" + value
        pairs.append(f"{key}：{value}")
    return "\n".join(pairs)


def render_dialogue(project: ProductionProject, planner: Path | None, scope=None) -> tuple[list[tuple[str, str, str]], str, int]:
    if scope is None:
        scope = active_scope(project, planner)
    lines = {line.id: line for line in project.lines}
    next_offset = {}
    items, output, ledger = [], [], []
    chinese = project.rules == CHINESE
    characters = 0
    for number, shot in enumerate(project.shots, 1):
        ids, cues, spoken = [], [], []
        for identity, start, end in shot.dialogue:
            original = lines.get(identity)
            span = scope.get(identity)
            if original is None or original.source != shot.source:
                raise ValueError(f"{project.group}-{number:02d} 的对白 {identity} 缺少本镜的批准来源。")
            if (not span or identity in ids or start != next_offset.get(identity, span[0])
                    or not span[0] <= start < end <= span[1]):
                raise ValueError(f"{identity} 的对白区间缺字、重复或顺序不符。")
            text = original.text[start:end]
            if not chinese:
                text = text.strip()
            if not text.strip():
                raise ValueError(f"{identity} 的片段没有实际发声内容。")
            first_in_group = identity not in next_offset
            next_offset[identity] = end
            ids.append(identity)
            cues.append(f"{identity}={'续说' if start else '首说'}")
            opening, closing = "“", "”"
            if chinese:
                count = chinese_speech_length(text)
                if not count:
                    raise ValueError(f"{identity} 的片段没有实际发声内容。")
                characters += count
                opening, closing = next(((a, b) for a, b in (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'))
                                         if b not in text), (opening, closing))
            else:
                items.append({"id": identity, "speaker": original.speaker, "text": original.text, "start": start, "end": end})
            spoken.append(f"{original.speaker}：{opening}{text}{closing}")
            origin = f" | 跨组续说，上一组 {project.previous_group}" if first_in_group and start else ""
            ledger.append(f"- {identity} → {project.group}-{number:02d} [{start}:{end}]{origin}")
        output.append(tuple("；".join(parts) or "无" for parts in (ids, cues, spoken)))
    for identity, end in next_offset.items():
        if end != scope[identity][1]:
            raise ValueError(f"{identity} 的批准对白未完整分配，请补全本组发声区间。")
    omitted = scope.keys() - next_offset.keys()
    if omitted:
        raise ValueError("本组已导入的批准对白有遗漏：" + "、".join(sorted(omitted)))
    if list(next_offset) != [line.id for line in project.lines if line.id in scope]:
        raise ValueError("镜头里的对白首说顺序与批准对白清单不一致。")
    if chinese:
        if characters > CHINESE_SPEECH_LIMIT:
            raise ValueError(f"本组实际发声 {characters} 字，超过 100 字。请在批准的自然切点换组。")
        count = characters
    else:
        groups = plan_dialogue(json.dumps(items, ensure_ascii=False), planner) if items else []
        if len(groups) > 1:
            raise ValueError("本组实际发声超过 60 个英文词，请按完整句重新分组。")
        count = groups[0]["words"] if groups else 0
    return output, "\n" + "\n".join(ledger) if ledger else "无对白", count


def check_english_board_input(project: ProductionProject, planner: Path | None) -> None:
    """Check the full English group before committing to a board image request."""
    if project.rules != ENGLISH:
        return
    require_camera_rules(project)
    scope = active_scope(project, planner)
    _, _, words = render_dialogue(project, planner, scope)
    spec = project.notes.get("对白规格", "").strip()
    status = project.notes.get("分组状态", "").strip()
    pure_fight = project.notes.get("内容类型", "").strip() == "纯打斗"
    if status not in {"常规", "整集尾组", "对白容量拆组"}:
        raise ValueError("生成正式故事板前，请先在「项目与组」确认分组状态。")
    if spec == "无对白" and not scope:
        panels = tuple(range(9, 13 if pure_fight else 11))
        if pure_fight and project.notes.get("打斗节奏依据", "").strip() in {"", "无"}:
            raise ValueError("纯打斗无对白组需要具体的「打斗节奏依据」。")
    elif spec in {"1-2句短对白", "1—2句短对白", "1–2句短对白"} and 1 <= len(scope) <= 2:
        panels = (8,)
    elif spec in {"三句以上或长对白", "3句以上或长对白"} and scope:
        panels = (6,)
    else:
        raise ValueError("请核对「对白规格」和已分配的批准对白，再生成正式故事板。")
    count = len(project.shots)
    if status == "整集尾组":
        if pending_record(project, scope) or not project.notes.get("尾组说明", "").strip():
            raise ValueError("整集尾组需填写实际结尾说明，并核完余下镜头和对白。")
        panels = tuple(range(1, max(panels) + 1))
    elif status == "对白容量拆组":
        evidence = re.fullmatch(r"(\d+)\s*\|\s*(\S.*)", project.notes.get("对白容量拆组说明", "").strip())
        if not scope or not words or not evidence or int(evidence[1]) <= 60:
            raise ValueError("对白容量拆组须保留原方案超 60 词的记录及拆组原因。")
        panels = tuple(range(1, panels[0]))
    if count not in panels:
        raise ValueError(f"本组当前 {count} 格，「{spec}／{status}」可用格数为 {'、'.join(map(str, panels))}。")
    required = ("景别", "机位/角度", "机位空间", "可见范围", "画面/事件", "人物站位", "动作起止",
                "唯一角色数量锁定", "本格新增叙事功能")
    for index, shot in enumerate(project.shots, 1):
        missing = [key for key in required if not shot.fields.get(key, "").strip()]
        if missing:
            raise ValueError(f"{project.group}-{index:02d} 的正式故事板缺少：{'、'.join(missing)}。")
    formal = [image for image in project.images if not image.reference_only]
    if len(formal) + int(not any("storyboard" in image.filename.lower() for image in formal)) > IMAGE_LIMIT:
        raise ValueError("计入正式故事板后超过九图上限。请先安排正式图片预算。")


def shot_records(shot, name, dialogue, sources, *, english_scene=None):
    if shot.source not in sources or not shot.anchor.strip() or any(char in shot.anchor for char in "|\n\r"):
        raise ValueError(f"{name} 请绑定批准剧本和源段位置。")
    fields = shot.fields
    try:
        format_fields(fields, SHOT_FIELDS, OPTIONAL_SHOT_FIELDS)
    except ValueError as exc:
        raise ValueError(f"{name} {exc}") from exc
    ids, cues, spoken = dialogue
    notes_text = format_fields(fields, (*PRODUCTION_SHOT_FIELDS, CAMERA_ACTION_FIELD), (CAMERA_ACTION_FIELD,))
    production = (f"分镜 {name}\n源镜ID：{shot.id}\n源段：{shot.anchor}\n时间码：待剪辑\n"
                  f"{notes_text}\n对白编号：{ids}\n对白衔接：{cues}\n对白：{spoken}")
    parent_id = fields.get(PARENT_SHOT_FIELD, "").strip()
    if parent_id:
        if any(char in parent_id for char in "|\r\n"):
            raise ValueError(f"{name} 的批准父镜 ID 需为不含竖线的单行标识。")
        production += f"\n源镜号：{parent_id} → {shot.id}"
    prompt = {"景别": fields["景别"], "机位/角度": f"{fields['机位/角度']}；{fields['机位空间']}",
              "人物数量限制": fields["唯一角色数量锁定"], "人物位置": fields["人物站位"],
              "动作": fields.get("成片动作", "").strip() or fields["动作起止"], "运镜": fields["运镜"],
              "场景/环境": fields["场景/环境"], "对白": spoken,
              "声音/音效": f"{fields['声源位置']}；{fields.get('成片声音', '').strip() or fields['声音']}",
              "本镜必要限制": fields["视频模型约束"]}
    if english_scene is not None:
        previous_scene = ENGLISH_SCENE_PREFIX.sub("", prompt["场景/环境"].strip())
        if re.search(r"@图\s*\d+", previous_scene):
            raise ValueError(f"{name} 的「场景/环境」有另一个图片编号，请保留文字描述并使用已绑定的正式净板。")
        prompt["场景/环境"] = english_scene + previous_scene
        prompt = {key: one_line(value) for key, value in prompt.items()}
        model = "\n".join(f"{key}：{value}" for key, value in prompt.items())
    else:
        model = format_fields(prompt, tuple(prompt))
    return production, f"分镜编号：{name}\n{model}"


def one_line(value: str) -> str:
    """Keep production-record lists out of the model's fixed-field layout."""
    return "；".join(filter(None, (re.sub(r"^[-*•]\s+", "", line.strip()) for line in value.splitlines())))


def english_references(images, storyboard, notes, plate_slots):
    """Number the actual approved PNGs by the intended model upload order."""
    characters = defaultdict(list)
    for line in notes.get("人物资产表", "").splitlines():
        parts = [part.strip() for part in line.lstrip("-*• ").split("|")]
        if len(parts) == 5:
            identity, _, filename, _, state = parts
            characters[filename].append(f"{identity}（{state}）" if state and state != "无" else identity)
    combined_views = defaultdict(list)
    for line in notes.get("场景拼接对应表", "").splitlines():
        parts = [part.strip() for part in line.lstrip("-*• ").split("|")]
        if len(parts) == 4 and parts[1] in {"main", "reverse"}:
            scene, view, filename, slot = parts
            angle = "正打" if view == "main" else "反打"
            combined_views[filename].append(f"{slot}「{scene}」{angle}")

    def asset_usage(image):
        filename = image.filename
        stem = ENGLISH_REFERENCE_PREFIX.sub("", Path(filename).stem)
        lower = stem.casefold()
        if filename in characters:
            role = 2 if lower.startswith(("other_characters_", "其他人物")) else 1
            return role, "只调用本组镜号所列身份：" + "、".join(characters[filename]) + "。"
        if lower.startswith(("protagonist_", "main_character", "mixed_characters_", "other_characters_", "主角", "其他人物")):
            raise ValueError(f"{filename} 请在「人物资产表」绑定实际身份和状态。")
        if prop := ENGLISH_PROP_NAME.fullmatch(stem):
            return 3, f"按本镜阶段调用：{prop[1] or '道具/界面'}参考。"
        if slots := plate_slots.get(image.id):
            return 4, f"使用本页对应镜号的局部{'、'.join(slots)}。"
        if view := ENGLISH_SCENE_VIEW.fullmatch(stem):
            angle = "正打" if view[2].lower() == "main" else "反打"
            return 4, f"地点「{view[1]}」的{angle}彩色参考，保持已批准的空间结构。"
        if filename in combined_views:
            return 4, "本页按实际地点取" + "、".join(combined_views[filename]) + "分区。"
        raise ValueError(f"{filename} 缺少正式图片用途，请核对文件命名和资产绑定。")

    assets = [(0, storyboard, "原批准线稿，按格号取机位、构图、站位和动作；辅助标记不得出现在成片。")]
    for image in images:
        if image.id != storyboard.id:
            order, usage = asset_usage(image)
            assets.append((order, image, usage))
    ordered = sorted(assets, key=lambda item: (item[0], item[1].filename.casefold()))
    manifest, numbers = [], {}
    for number, (_, image, usage) in enumerate(ordered, 1):
        if "）" in image.filename:
            raise ValueError(f"{image.filename} 的全角右括号会截断 @图 引用，请调整文件名。")
        numbers[image.id] = number
        manifest.append(f"@图{number}（{image.filename}）{one_line(usage)}")
    return manifest, numbers


def english_prompt_header(project, storyboard, manifest):
    format_fields(project.prompt, PROMPT_FIELDS)
    common = one_line(project.prompt["公共限制"])
    state = one_line(project.prompt["场景/总体状态"])
    return "\n".join((
        f"分组：{project.group}",
        f"按 @图1（{storyboard.filename}）的格号顺序硬切，逐格使用同号局部。",
        *manifest,
        f"场景/总体状态：{state}",
        f"视频上色约束：{ENGLISH_COLOR}",
        f"视频文字约束：{LANGUAGE}",
        f"公共限制：{ENGLISH_COMMON}{common}",
    ))


def check_chinese_panels(project, spoken_ids, pending):
    spec = project.notes.get("对白规格", "").strip()
    status = project.notes.get("分组状态", "").strip()
    if status not in {"常规", "整集尾组"}:
        raise ValueError("中文分组状态须填「常规」或「整集尾组」。")
    if spec == "无对白" and spoken_ids == 0:
        panels = (9, 10)
    elif spec in {"1-2句短对白", "1—2句短对白", "1–2句短对白"} and 1 <= spoken_ids <= 2:
        panels = (8,)
    elif spec in {"三句以上或长对白", "3句以上或长对白"} and spoken_ids:
        panels = (6,)
    else:
        raise ValueError(f"本组实际有 {spoken_ids} 条源对白，核对「对白规格」和表演长度。")
    if status == "整集尾组":
        if pending or not project.notes.get("尾组说明", "").strip():
            raise ValueError("整集尾组需填写实际结尾说明并核完余下镜头与对白。")
        panels = tuple(range(1, max(panels) + 1))
    if len(project.shots) not in panels:
        target = " 或 ".join(map(str, panels)) if status == "常规" else f"1 至 {max(panels)}"
        raise ValueError(f"{spec}当前有 {len(project.shots)} 格，{status}需要 {target} 格。请重排有效镜头。")


def chinese_layout_fields(project):
    output = project.layout.get("output", {})
    metadata = output.get("chinese")
    if not metadata:
        return {}
    assets = {item.id: item for item in project.images if not item.reference_only}
    if len(assets) != metadata["count"] or len(assets) > IMAGE_LIMIT or not set(metadata["scene_views"]) <= assets.keys():
        raise ValueError("正式图片已变化，请重新确认中文排版和九图预算。")
    windows = windows_for_shots(project, assets)
    figures, views, locations = [], [], {}
    for sheet in output["sheets"]:
        asset = assets[sheet["asset"]]
        rectangles, view_names, boxes = [], [], []
        for cell in sheet["cells"]:
            box = cell["box"]
            if (not valid_box(box, (asset.width, asset.height)) or not exact_box(box)
                    or any(overlap(box, other) for other in boxes)):
                raise ValueError(f"{asset.filename} 的图格布局无效。")
            x, y, right, bottom = box
            boxes.append(box)
            rectangles.append(f"{x},{y},{right-x},{bottom-y}")
            if cell["view"]:
                scene, angle = cell["view"]
                view_names.append(f"{scene}/{angle}")
                for identity in cell["shots"]:
                    locations[identity] = (cell["slot"], scene)
        figures.append(f"- {asset.filename}：{'；'.join(rectangles)}")
        if metadata["mode"] == "九图合并" and view_names:
            views.append(f"- {asset.filename}：{'；'.join(view_names)}")
    plates, pixel_rows = [], []
    for number, shot in enumerate(project.shots, 1):
        name = f"{project.group}-{number:02d}"
        slot, scene = locations[shot.id]
        if scene != shot.scene or not shot.plate_note.strip() or any(char in shot.plate_note for char in "|\n\r"):
            raise ValueError(f"{name} 请填写对应的实际净板机位说明。")
        board, board_box = windows[shot.id]["board"]
        plate, plate_box = windows[shot.id]["plate"]
        plates.append(f"- {name} | {plate.filename} | {slot} | {scene} | {shot.plate_note}")
        a, b = (",".join(map(str, box)) for box in (board_box, plate_box))
        pixel_rows.append(f"- {name} | {board.filename} | {a} | {plate.filename} | {b}")
    values = {
        "场景资产模式": metadata["mode"],
        "场景清单": "；".join(dict.fromkeys(shot.scene for shot in project.shots)),
        "故事板排版模式": metadata["board_mode"],
        "九图优化记录": metadata["budget"],
        "图格布局": "\n".join(figures),
        "图格比例核对": metadata["inspection"],
        "故事板运动标注": mark_ledger(project),
        "场景局部对应表": "\n".join(plates),
        "实际画面窗口": "\n".join(pixel_rows),
    }
    if views:
        values["场景合并来源"] = metadata["source_mode"]
        values["场景视图映射"] = "\n".join(views)
    return values


def chinese_text_records(project: ProductionProject, *, layout_fields=None) -> dict[str, str]:
    """Prepare the standalone text files before image layout and package review."""
    project.check_identity()
    if project.rules != CHINESE or not project.sources:
        raise ValueError("请选择中文项目，并先导入批准剧本。")
    scope = active_scope(project, None)
    dialogues, ledger, count = render_dialogue(project, None, scope)
    pending = pending_record(project, scope)
    check_chinese_panels(project, len(scope), pending)
    cross_rows, _ = handoff_rows(project, scope)
    group = project.group
    production = [
        f"分组：{group}\n格数：{len(project.shots)}\n总发声字数：{count}\n视频任务时长：待剪辑\n画面格式：16:9 彩色视频",
        format_fields(project.notes, CHINESE_TEXT_FIELDS, CHINESE_TEXT_OPTIONAL),
        f"对白保全核对：{ledger}\n视频上色约束：{COLOR}\n视频文字约束：{CHINESE_LANGUAGE}",
    ]
    if cross_rows:
        production.append("跨组对白原文：\n" + "\n".join(cross_rows))
    common = dict(project.prompt)
    common["公共限制"] = (common.get("公共限制", "").strip() + " " + MARKS).strip()
    sd2 = [f"分组：{group}\n视频上色约束：{COLOR}\n视频文字约束：{CHINESE_LANGUAGE}", format_fields(common, PROMPT_FIELDS)]
    sources = {source.id for source in project.sources}
    for ordinal, (shot, dialogue) in enumerate(zip(project.shots, dialogues), 1):
        record, prompt = shot_records(shot, f"{group}-{ordinal:02d}", dialogue, sources)
        production.append(record)
        sd2.append(prompt)
    layout = chinese_layout_fields(project) if layout_fields is None else layout_fields
    if layout:
        production.append(format_fields(layout, tuple(layout)))
    files = {f"{group}_shot_details.txt": "\n\n".join(production) + "\n",
             "SD2_prompt.txt": "\n\n".join(sd2) + "\n"}
    if pending:
        files["待制作分镜.txt"] = pending
    return files


def write_chinese_outputs(folder, files, pictures=()):
    try:
        folder.mkdir()
    except FileExistsError:
        raise ValueError(f"此目录已有 {folder.name}，请选择新的保存位置。") from None
    created = []
    try:
        for name, contents in files.items():
            path = folder / name
            with path.open("x", encoding="utf-8-sig", newline="\n") as stream:
                created.append(path)
                stream.write(contents)
        for image, source in pictures:
            target = folder / image.filename
            with source.open("rb") as original, target.open("xb") as destination:
                created.append(target)
                copyfileobj(original, destination)
            if sha256_file(target) != image.digest:
                raise ValueError(f"{image.filename} 在复制过程中发生变化。")
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        if not any(folder.iterdir()):
            folder.rmdir()
        raise
    return folder


def write_chinese_texts(project: ProductionProject, directory: Path) -> Path:
    return write_chinese_outputs(directory / f"{project.group}_文字稿", chinese_text_records(project))


def write_chinese_layout(project: ProductionProject, project_path: Path, folder: Path) -> Path:
    if not project.layout.get("output", {}).get("chinese"):
        raise ValueError("请生成排版预览，核图后确认本组故事板和净板。")
    files = chinese_text_records(project)
    pictures = [(image, project.checked_image(project_path, image))
                for image in project.images if not image.reference_only]
    return write_chinese_outputs(folder, files, pictures)


def preview_chinese_layout(project: ProductionProject, project_path: Path, directory: Path) -> Path:
    delivery = directory / "layout"
    delivery.mkdir()
    write_chinese_layout(project, project_path, delivery / project.group)
    preview = directory / "layout-review.zip"
    write_delivery_zip(delivery, preview)
    return preview


def register_project_assets(project, project_path, registry_path):
    registry = AssetRegistry(registry_path, create=True)
    references, locations = {}, {}
    for image in project.images:
        source = project.checked_image(project_path, image)
        registered = registry.register(source, image.id, image.version, image.origin)
        if registered.sha256 != image.digest:
            raise ValueError(f"{image.filename} 在登记期间发生变化，请重新核对批准原图。")
        references[image.id] = f"asset:{registered.identifier}@{registered.version}"
        locations[image.id] = source
    return references, locations


def asset_records(images, references, storyboard_files):
    reuse, inspections = [], []
    for image in images:
        if not image.inspection or any(char in image.inspection for char in "|\r\n"):
            raise ValueError(f"{image.filename} 请填写实际核图结果。")
        if image not in storyboard_files:
            if not image.reason or any(char in image.reason for char in "|\r\n"):
                raise ValueError(f"{image.filename} 请说明该文件的实际处理理由。")
            if image.action == "新生成":
                origin = "无"
            else:
                ids = image.originals or [image.id]
                if not all(identity in references for identity in ids):
                    raise ValueError(f"{image.filename} 缺少对应的批准来源。")
                origin = "；".join(references[item] for item in ids)
            reuse.append(f"- {image.filename} | {image.action} | {origin} | {image.reason}")
        inspections.append(f"- {image.filename} | {image.width}x{image.height} | {image.inspection}")
    return reuse, inspections


def chinese_character_notes(project, images):
    notes = project.notes
    missing = [key for key in CHINESE_REQUIRED_REVIEWS if not notes.get(key, "").strip()]
    if missing:
        raise ValueError(f"{project.group} 严格交付前请填写「{'、'.join(missing)}」。")
    no_characters = all(shot.fields.get("唯一角色数量锁定", "").strip() == "无" for shot in project.shots)
    no_character_verdict = any(term in notes["主角判定"] for term in ("无角色型实体", "无人物或角色型实体", "纯场景"))
    if no_characters != no_character_verdict:
        raise ValueError(f"{project.group} 主角判定与实际逐镜人物数量锁定不一致。")
    character_fields = {field: notes.get(field, "").strip() for field in CHINESE_CHARACTER_FIELDS}
    if no_characters:
        if any(value not in ("", "无") for value in character_fields.values()) or any(
            re.search(r"protagonist|main_characters?|other_characters|主角|其他人物", image.filename, re.I) for image in images
        ):
            raise ValueError(f"{project.group} 纯场景记录与批准人物图不一致。")
        return dict.fromkeys(CHINESE_CHARACTER_FIELDS, "无")
    if any(character_fields.get(field) in ("", "无") for field in (
        "主角清单", "主角资产映射", "人物资产核对", "人物资产分表",
    )):
        raise ValueError(f"{project.group} 请填写本组主角清单、映射、人物资产核对和分表。")
    if not character_fields["其他人物合集"]:
        raise ValueError(f"{project.group} 请填写实际其他人物合集。没有时填「无」。")
    character_fields["混合人物资产映射"] = character_fields["混合人物资产映射"] or "无"
    return character_fields


def build_chinese_delivery(project, project_path, folder, registry_path, *, write_root):
    layout = chinese_layout_fields(project)
    if not layout:
        raise ValueError("中文项目的交付模板需要先确认本组故事板和净板排版。")
    files = chinese_text_records(project, layout_fields=layout)
    pending = files.pop("待制作分镜.txt", "")
    images = [image for image in project.images if not image.reference_only]
    character_notes = chinese_character_notes(project, images)
    references, locations = register_project_assets(project, project_path, registry_path)
    storyboards = [image for image in images if "storyboard" in image.filename.lower()]
    reuse, inspections = asset_records(images, references, storyboards)
    approved = "；".join(image.filename for image in images if image.action != "新生成") or "无"
    generated = "；".join(image.filename for image in images if image.action == "新生成") or "无"
    archive = "；".join(image.filename for image in project.images if image.reference_only) or "无"
    inventory = f"- 复用及规范排版资产：{approved}\n- 独立新生成资产：{generated}\n- 仅参考资料：{archive}"
    group = project.group
    details = f"{group}_shot_details.txt"
    supplemental = [format_fields(character_notes, tuple(character_notes)), f"资产清单：\n{inventory}",
                    "资产复用核对：\n" + "\n".join(reuse), "图像验收记录：\n" + "\n".join(inspections)]
    if jobs := provenance_rows(project, images):
        supplemental.append("图像生成和返修来源：\n" + "\n".join(jobs))
    files[details] += "\n" + "\n\n".join(supplemental) + "\n"
    folder.mkdir(parents=True, exist_ok=True)
    write_chinese_outputs(folder / group, files, [(image, locations[image.id]) for image in images])

    sources = {source.id: source for source in project.sources}
    slots = [row.split("|")[2].strip() for row in layout["场景局部对应表"].splitlines()]
    shot_rows = []
    for number, (shot, slot) in enumerate(zip(project.shots, slots), 1):
        source = sources[shot.source]
        shot_rows.append(f"- {group}-{number:02d} | {shot.id} | {source.name} {source.version} | {shot.anchor} | {slot}")
    readme = (
        f"{project.name} · {project.episode}\n制作规则：{rule_revision(project.rules)}\n组号：{group}\n"
        f"镜头数：{len(project.shots)}\n图片数：{len(images)}\n本组进入状态：{project.notes['本组进入状态']}\n"
        f"本组退出状态：{project.notes['本组退出状态']}\n镜头与来源：\n" + "\n".join(shot_rows) + "\n"
    )
    if write_root:
        write_summary(folder, readme, pending, len(project.pending_shots))
    return readme, pending


def build_delivery(project: ProductionProject, project_path: Path, folder: Path, validator: Path,
                   registry_path: Path, *, write_root=True):
    project.check_identity()
    if not project.name.strip() or not project.episode.strip() or not project.sources or not project.shots:
        if project.rules == CHINESE:
            raise ValueError("中文项目的交付模板需要完整的项目名、集次、批准剧本和镜头。")
        raise ValueError("完整组需要项目名、集次、批准剧本和镜头。")
    require_camera_rules(project)
    if project.rules == CHINESE:
        return build_chinese_delivery(project, project_path, folder, registry_path, write_root=write_root)
    images = [image for image in project.images if not image.reference_only]
    if len(images) > IMAGE_LIMIT:
        raise ValueError(f"本组将交付 {len(images)} 张 PNG，超过九图上限。")
    storyboard_files = [image for image in images if "storyboard" in image.filename.lower()]
    windows = windows_for_shots(project)
    if len(storyboard_files) != 1 or not re.search(rf"(?<!\d){len(project.shots)}panel", storyboard_files[0].filename, re.I):
        raise ValueError("请导入一张格数与镜头清单一致的正式故事板，文件名包含实际格数，如 storyboard_8panel。")

    planner = validator.with_name("plan_english_dialogue.py")
    scope = active_scope(project, planner)
    dialogues, dialogue_ledger, _ = render_dialogue(project, planner, scope)
    cross_rows, _ = handoff_rows(project, scope)
    pending = pending_record(project, scope)
    sources = {source.id: source for source in project.sources}
    assets = {image.id: image for image in images}
    group_id = project.group
    notes = dict(project.notes)
    if pending and notes.get("分组状态") == "整集尾组":
        raise ValueError("仍有待制作镜头或对白，请核对分组状态。")
    if windows and (marks := mark_ledger(project)) != "无":
        notes["动作辅助标注"] = marks
    if not notes.get("图片预算核对", "").strip():
        notes["图片预算核对"] = "；".join(f"{stage}={len(images)}" for stage in ("初始", "道具后", "配角后", "主角后", "场景后", "最终")) + "；说明=以本组导入的批准交付图为准，本次输出保持图像文件张数。"
    if not notes.get("资产清单", "").strip():
        notes["资产清单"] = "\n".join(f"- {image.filename} | {image.action}" for image in images)

    production = [f"分组：{group_id}\n格数：{len(project.shots)}\n视频任务时长：待剪辑\n画面格式：16:9 彩色视频",
                  format_fields(notes, GROUP_FIELDS, GROUP_OPTIONAL | {"图片预算核对", "资产清单"}),
                  f"对白保全核对：{dialogue_ledger}\n视频上色约束：{ENGLISH_COLOR}\n视频文字约束：{LANGUAGE}"]
    if cross_rows:
        production.append("跨组对白原文：\n" + "\n".join(cross_rows))
    plate_slots, shot_plates = defaultdict(list), []
    for number, shot in enumerate(project.shots, 1):
        slot = f"{number:02d}"
        name = f"{group_id}-{slot}"
        plate = assets.get(shot.plate)
        if not plate or ("_details" not in plate.filename.lower() and "场景合辑" not in plate.filename):
            raise ValueError(f"{name} 缺少正式净板绑定。")
        if not shot.scene.strip() or not shot.plate_note.strip() or any(
            char in shot.scene + shot.plate_note for char in "|\n\r"
        ):
            raise ValueError(f"{name} 缺少单行地点和净板机位说明。")
        if "」" in shot.scene:
            raise ValueError(f"{name} 的地点名含有右引号，请填写实际地点名。")
        plate_slots[plate.id].append(slot)
        shot_plates.append((name, plate, slot))
    storyboard = storyboard_files[0]
    manifest, picture_numbers = english_references(images, storyboard, notes, plate_slots)
    sd2 = [english_prompt_header(project, storyboard, manifest)]
    plate_rows, shot_rows, window_rows = [], [], []
    for shot, dialogue, (name, plate, slot) in zip(project.shots, dialogues, shot_plates):
        scene_reference = f"@图{picture_numbers[plate.id]} 的局部{slot}。地点「{shot.scene.strip()}」。"
        record, model_prompt = shot_records(shot, name, dialogue, sources, english_scene=scene_reference)
        plate_rows.append(f"- {name} | {plate.filename} | 局部{slot} | {shot.scene} | {shot.plate_note}")
        production.append(record)
        sd2.append(model_prompt)
        shot_rows.append(f"- {name} | {shot.id} | {sources[shot.source].name} {sources[shot.source].version} | {shot.anchor} | 局部{slot}")
        if windows:
            board, board_box = windows[shot.id]["board"]
            _, plate_box = windows[shot.id]["plate"]
            if board.id != storyboard_files[0].id:
                raise ValueError("板格坐标未绑定当前交付故事板。")
            board_position, plate_position = (",".join(map(str, box)) for box in (board_box, plate_box))
            window_rows.append(f"- {name} | {board.filename} | {board_position} | {plate.filename} | {plate_position}")

    references, image_locations = register_project_assets(project, project_path, registry_path)

    group_folder = folder / group_id
    group_folder.mkdir(parents=True)
    reuse, inspections = asset_records(images, references, storyboard_files)
    for image in images:
        target = group_folder / image.filename
        copyfile(image_locations[image.id], target)
        if sha256_file(target) != image.digest:
            raise ValueError(f"{image.filename} 在复制过程中发生变化。")

    production.extend(["资产复用核对：\n" + "\n".join(reuse), "场景局部对应表：\n" + "\n".join(plate_rows),
                       "图像验收记录：\n" + "\n".join(inspections)])
    jobs = provenance_rows(project, images)
    if jobs:
        production.append("图像生成和返修来源：\n" + "\n".join(jobs))
    if window_rows:
        production.append("实际画面窗口：\n" + "\n".join(window_rows))
    (group_folder / f"{group_id}_shot_details.txt").write_text("\n\n".join(production) + "\n", encoding="utf-8-sig", newline="\n")
    (group_folder / "SD2_prompt.txt").write_text("\n\n".join(sd2) + "\n", encoding="utf-8-sig", newline="\n")
    readme = (
        f"{project.name} · {project.episode}\n制作规则：{rule_revision(project.rules)}\n组号：{group_id}\n"
        f"镜头数：{len(project.shots)}\n图片数：{len(images)}\n本组进入状态：{notes['本组进入状态']}\n"
        f"本组退出状态：{notes['本组退出状态']}\n镜头与来源：\n" + "\n".join(shot_rows) + "\n"
    )
    if write_root:
        write_summary(folder, readme, pending, len(project.pending_shots))
    return readme, pending


def write_summary(folder, summary, pending, count):
    if pending:
        summary += f"\n待制作镜头数：{count}\n未完成内容见顶层待制作分镜.txt，下一批优先接续。\n"
        (folder / "待制作分镜.txt").write_text(pending, encoding="utf-8-sig", newline="\n")
    (folder / "README.txt").write_text(summary, encoding="utf-8-sig", newline="\n")


def project_registry(project_path: Path) -> Path:
    return project_path.with_suffix(".assets.sqlite3")


def preview_project(project: ProductionProject, project_path: Path, validator: Path, directory: Path) -> Path:
    staging = directory / "delivery"
    build_delivery(project, project_path, staging, validator, project_registry(project_path))
    draft = directory / "review.zip"
    write_delivery_zip(staging, draft)
    return draft


def publish_project(project: ProductionProject, project_path: Path, validator: Path, output: Path,
                    baseline: Path | None = None, panel_exception: Path | None = None):
    if project.rules == CHINESE and panel_exception is not None:
        raise ValueError("中文制作使用自身的篇末格数规则。")
    if project.impacts():
        raise ValueError("请逐格核对当前镜头顺序和图像布局，再确认本版本画面。")
    with TemporaryDirectory(prefix="comicflow-production-") as temporary:
        sidecar = Path(temporary)
        folder, registry = sidecar / "delivery", project_registry(project_path)
        build_delivery(project, project_path, folder, validator, registry)
        return pack_repair(folder, output, validator, baseline, registry, panel_exception)


def build_batch(groups, folder, validator, registry):
    for (left, _), (right, _) in zip(groups, groups[1:]):
        adjacent(left, right)
        findings = boundary_camera_cuts(left, right)
        if findings:
            raise ValueError(camera_findings_text(findings))
    summaries, boundaries = [], []
    for index, (project, path) in enumerate(groups):
        if index:
            previous = groups[index - 1][0]
            if project.rules == CHINESE:
                if previous.notes.get("分组状态", "").strip() == "整集尾组":
                    raise ValueError(f"{previous.group} 后仍有正式组，请核对整集尾组状态。")
                _, issues = boundary_report(previous, project, None)
                if issues:
                    raise ValueError("\n".join(issues))
            if reviewed_boundary(previous, project):
                boundaries.append(f"{previous.group} → {project.group}\n{previous.handoffs[project.group]['review']}")
        summary, pending = build_delivery(project, path, folder, validator, registry, write_root=False)
        summaries.append(summary)
    if boundaries:
        summaries.extend(("跨组交接记录\n", *boundaries))
    write_summary(folder, "\n\n".join(summaries).rstrip() + "\n", pending, len(groups[-1][0].pending_shots))


def publish_batch(groups, validator, output, baseline=None):
    if len(groups) < 2 or any(project.impacts() for project, _ in groups):
        raise ValueError("请先逐格复核并确认每个待交付的组。")
    if any(not reviewed_boundary(left, right) for (left, _), (right, _) in zip(groups, groups[1:])):
        raise ValueError("请确认当前版本的每处相邻组交接。")
    with TemporaryDirectory(prefix="comicflow-batch-") as temporary:
        folder = Path(temporary) / "delivery"
        registry = project_registry(groups[0][1])
        build_batch(groups, folder, validator, registry)
        return pack_repair(folder, output, validator, baseline, registry)
