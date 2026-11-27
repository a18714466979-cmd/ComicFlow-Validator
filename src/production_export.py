"""Render both storyboarding records from one project, then use strict delivery validation."""

import json
import re
from pathlib import Path
from shutil import copyfile, copyfileobj
from tempfile import TemporaryDirectory

from .asset_registry import AssetRegistry, sha256_file
from .production_dialogue import handoff_rows
from .production_handoff import active_scope, adjacent, boundary_report, pending_record, reviewed_boundary
from .production_images import provenance_rows
from .production_layout import exact_box, mark_ledger, overlap, valid_box, windows_for_shots
from .production_project import (
    CHINESE_CHARACTER_FIELDS, CHINESE_TEXT_FIELDS, CHINESE_TEXT_OPTIONAL, GROUP_FIELDS, GROUP_OPTIONAL, OPTIONAL_SHOT_FIELDS,
    PROMPT_FIELDS, SHOT_FIELDS, ProductionProject,
)
from .production_rules import CHINESE
from .repair_package import pack_repair, write_delivery_zip
from .storyboard_preflight import CHINESE_SPEECH_LIMIT, IMAGE_LIMIT, chinese_speech_length, plan_dialogue


COLOR = "黑白故事板仅作镜头、构图、站位和动作参考；成片按本组实际交付的彩色资产上色，禁止黑白、灰度或线稿成片。"
LANGUAGE = "成片中的画面文字、字幕、标牌和 HUD 禁止中文，仅允许英文或通用符号。"
CHINESE_LANGUAGE = "成片字幕、标牌、UI/HUD、系统提示和拟声字允许中文，按本剧已批准文案呈现。参考标签仅用于制作定位。"
MARKS = "故事板的彩色辅助线、箭头、序号和图例仅作动作参考，不得出现在成片中。"
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


def shot_records(shot, name, dialogue, sources):
    if shot.source not in sources or not shot.anchor.strip() or any(char in shot.anchor for char in "|\n\r"):
        raise ValueError(f"{name} 请绑定批准剧本和源段位置。")
    fields = shot.fields
    try:
        format_fields(fields, SHOT_FIELDS, OPTIONAL_SHOT_FIELDS)
    except ValueError as exc:
        raise ValueError(f"{name} {exc}") from exc
    ids, cues, spoken = dialogue
    notes_text = format_fields(fields, PRODUCTION_SHOT_FIELDS)
    production = (f"分镜 {name}\n源镜ID：{shot.id}\n源段：{shot.anchor}\n时间码：待剪辑\n"
                  f"{notes_text}\n对白编号：{ids}\n对白衔接：{cues}\n对白：{spoken}")
    prompt = {"景别": fields["景别"], "机位/角度": f"{fields['机位/角度']}；{fields['机位空间']}",
              "人物数量限制": fields["唯一角色数量锁定"], "人物位置": fields["人物站位"],
              "动作": fields.get("成片动作", "").strip() or fields["动作起止"], "运镜": fields["运镜"],
              "场景/环境": fields["场景/环境"], "对白": spoken,
              "声音/音效": f"{fields['声源位置']}；{fields.get('成片声音', '').strip() or fields['声音']}",
              "本镜必要限制": fields["视频模型约束"]}
    return production, f"分镜编号：{name}\n" + format_fields(prompt, tuple(prompt))


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
        f"{project.name} · {project.episode}\n制作规则：{project.rules}\n组号：{group}\n"
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
                  f"对白保全核对：{dialogue_ledger}\n视频上色约束：{COLOR}\n视频文字约束：{LANGUAGE}"]
    if cross_rows:
        production.append("跨组对白原文：\n" + "\n".join(cross_rows))
    common = dict(project.prompt)
    common["公共限制"] = (common.get("公共限制", "").strip() + " " + MARKS).strip()
    sd2 = [f"分组：{group_id}\n视频上色约束：{COLOR}\n视频文字约束：{LANGUAGE}", format_fields(common, PROMPT_FIELDS)]
    plate_rows, shot_rows, window_rows = [], [], []
    for number, (shot, dialogue) in enumerate(zip(project.shots, dialogues), 1):
        name = f"{group_id}-{number:02d}"
        record, model_prompt = shot_records(shot, name, dialogue, sources)
        plate = assets.get(shot.plate)
        if not plate or ("_details" not in plate.filename.lower() and "场景合辑" not in plate.filename):
            raise ValueError(f"{name} 缺少正式净板绑定。")
        if not shot.scene.strip() or not shot.plate_note.strip() or any(
            char in shot.scene + shot.plate_note for char in "|\n\r"
        ):
            raise ValueError(f"{name} 缺少单行地点和净板机位说明。")
        plate_rows.append(f"- {name} | {plate.filename} | 局部{number:02d} | {shot.scene} | {shot.plate_note}")
        production.append(record)
        sd2.append(model_prompt)
        shot_rows.append(f"- {name} | {shot.id} | {sources[shot.source].name} {sources[shot.source].version} | {shot.anchor} | 局部{number:02d}")
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
    (group_folder / f"{group_id}_shot_details.txt").write_text("\n\n".join(production) + "\n", encoding="utf-8-sig")
    (group_folder / "SD2_prompt.txt").write_text("\n\n".join(sd2) + "\n", encoding="utf-8-sig")
    readme = (
        f"{project.name} · {project.episode}\n制作规则：{project.rules}\n组号：{group_id}\n"
        f"镜头数：{len(project.shots)}\n图片数：{len(images)}\n本组进入状态：{notes['本组进入状态']}\n"
        f"本组退出状态：{notes['本组退出状态']}\n镜头与来源：\n" + "\n".join(shot_rows) + "\n"
    )
    if write_root:
        write_summary(folder, readme, pending, len(project.pending_shots))
    return readme, pending


def write_summary(folder, summary, pending, count):
    if pending:
        summary += f"\n待制作镜头数：{count}\n未完成内容见顶层待制作分镜.txt，下一批优先接续。\n"
        (folder / "待制作分镜.txt").write_text(pending, encoding="utf-8-sig")
    (folder / "README.txt").write_text(summary, encoding="utf-8-sig")


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
    summaries, boundaries = [], []
    for index, (project, path) in enumerate(groups):
        if index:
            previous = groups[index - 1][0]
            adjacent(previous, project)
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
