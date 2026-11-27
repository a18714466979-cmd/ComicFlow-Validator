"""Render both storyboarding records from one project, then use strict delivery validation."""

import json
import re
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from .asset_registry import AssetRegistry, sha256_file
from .production_dialogue import handoff_rows, validated_scope
from .production_project import GROUP_FIELDS, GROUP_OPTIONAL, OPTIONAL_SHOT_FIELDS, PROMPT_FIELDS, SHOT_FIELDS, ProductionProject
from .repair_package import pack_repair, write_delivery_zip
from .storyboard_preflight import IMAGE_LIMIT, plan_dialogue


COLOR = "黑白故事板仅作镜头、构图、站位和动作参考；成片按本组实际交付的彩色资产上色，禁止黑白、灰度或线稿成片。"
LANGUAGE = "成片中的画面文字、字幕、标牌和 HUD 禁止中文，仅允许英文或通用符号。"
MARKS = "故事板的彩色辅助线、箭头、序号和图例仅作动作参考，不得出现在成片中。"


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


def render_dialogue(project: ProductionProject, planner: Path, scope=None) -> tuple[list[tuple[str, str, str]], str, int]:
    if scope is None:
        scope = validated_scope(project, planner)
    lines = {line.id: line for line in project.lines}
    next_offset = {}
    items, output, ledger = [], [], []
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
            text = original.text[start:end].strip()
            if not text:
                raise ValueError(f"{identity} 的片段没有实际发声内容。")
            first_in_group = identity not in next_offset
            next_offset[identity] = end
            ids.append(identity)
            cues.append(f"{identity}={'续说' if start else '首说'}")
            spoken.append(f"{original.speaker}：“{text}”")
            items.append({"id": identity, "speaker": original.speaker, "text": original.text, "start": start, "end": end})
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
    groups = plan_dialogue(json.dumps(items, ensure_ascii=False), planner) if items else []
    if len(groups) > 1:
        raise ValueError("本组实际发声超过 60 个英文词，请按完整句重新分组。")
    return output, "\n" + "\n".join(ledger) if ledger else "无对白", groups[0]["words"] if groups else 0


def build_delivery(project: ProductionProject, project_path: Path, folder: Path, validator: Path,
                   registry_path: Path) -> None:
    project.check_identity()
    if not project.name.strip() or not project.episode.strip() or not project.sources or not project.shots:
        raise ValueError("完整组需要项目名、集次、批准剧本和镜头。")
    images = [image for image in project.images if not image.reference_only]
    if len(images) > IMAGE_LIMIT:
        raise ValueError(f"本组将交付 {len(images)} 张 PNG，超过九图上限。")
    storyboard_files = [image for image in images if "storyboard" in image.filename.lower()]
    if len(storyboard_files) != 1 or not re.search(rf"(?<!\d){len(project.shots)}panel", storyboard_files[0].filename, re.I):
        raise ValueError("请导入一张格数与镜头清单一致的正式故事板，文件名包含实际格数，如 storyboard_8panel。")

    planner = validator.with_name("plan_english_dialogue.py")
    scope = validated_scope(project, planner)
    dialogues, dialogue_ledger, _ = render_dialogue(project, planner, scope)
    cross_rows, pending = handoff_rows(project, scope)
    sources = {source.id: source for source in project.sources}
    assets = {image.id: image for image in images}
    group_id = project.group
    notes = dict(project.notes)
    if pending and notes.get("分组状态") == "整集尾组":
        raise ValueError("仍有跨组对白待续，请核对分组状态。")
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
    plate_rows, shot_rows = [], []
    for number, (shot, dialogue) in enumerate(zip(project.shots, dialogues), 1):
        name = f"{group_id}-{number:02d}"
        if shot.source not in sources or not shot.anchor.strip() or any(char in shot.anchor for char in "|\n\r"):
            raise ValueError(f"{name} 请绑定批准剧本和源段位置。")
        plate = assets.get(shot.plate)
        if not plate or ("_details" not in plate.filename.lower() and "场景合辑" not in plate.filename):
            raise ValueError(f"{name} 缺少正式净板绑定。")
        if not shot.scene.strip() or not shot.plate_note.strip() or any(
            char in shot.scene + shot.plate_note for char in "|\n\r"
        ):
            raise ValueError(f"{name} 缺少单行地点和净板机位说明。")
        plate_rows.append(f"- {name} | {plate.filename} | 局部{number:02d} | {shot.scene} | {shot.plate_note}")
        fields = shot.fields
        try:
            format_fields(fields, SHOT_FIELDS, OPTIONAL_SHOT_FIELDS)
        except ValueError as exc:
            raise ValueError(f"{name} {exc}") from exc
        ids, cues, spoken = dialogue
        notes_text = format_fields(fields, tuple(key for key in SHOT_FIELDS if key not in OPTIONAL_SHOT_FIELDS))
        production.append(f"分镜 {name}\n源镜ID：{shot.id}\n源段：{shot.anchor}\n时间码：待剪辑\n{notes_text}\n对白编号：{ids}\n对白衔接：{cues}\n对白：{spoken}")
        prompt = {"景别": fields["景别"], "机位/角度": f"{fields['机位/角度']}；{fields['机位空间']}",
                  "人物数量限制": fields["唯一角色数量锁定"], "人物位置": fields["人物站位"],
                  "动作": fields.get("成片动作", "").strip() or fields["动作起止"], "运镜": fields["运镜"],
                  "场景/环境": fields["场景/环境"], "对白": spoken,
                  "声音/音效": f"{fields['声源位置']}；{fields.get('成片声音', '').strip() or fields['声音']}",
                  "本镜必要限制": fields["视频模型约束"]}
        sd2.append(f"分镜编号：{name}\n" + format_fields(prompt, tuple(prompt)))
        shot_rows.append(f"- {name} | {shot.id} | {sources[shot.source].name} {sources[shot.source].version} | {shot.anchor} | 局部{number:02d}")

    registry = AssetRegistry(registry_path, create=True)
    references = {}
    image_locations = {}
    for image in project.images:
        path = project.checked_image(project_path, image)
        registered = registry.register(path, image.id, image.version, image.origin)
        references[image.id] = f"asset:{registered.identifier}@{registered.version}"
        image_locations[image.id] = path

    group_folder = folder / group_id
    group_folder.mkdir(parents=True)
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
                origin = "；".join(references[item] for item in (image.originals or [image.id]))
            reuse.append(f"- {image.filename} | {image.action} | {origin} | {image.reason}")
        inspections.append(f"- {image.filename} | {image.width}x{image.height} | {image.inspection}")
        target = group_folder / image.filename
        copyfile(image_locations[image.id], target)
        if sha256_file(target) != image.digest:
            raise ValueError(f"{image.filename} 在复制过程中发生变化。")

    production.extend(["资产复用核对：\n" + "\n".join(reuse), "场景局部对应表：\n" + "\n".join(plate_rows),
                       "图像验收记录：\n" + "\n".join(inspections)])
    (group_folder / f"{group_id}_shot_details.txt").write_text("\n\n".join(production) + "\n", encoding="utf-8-sig")
    (group_folder / "SD2_prompt.txt").write_text("\n\n".join(sd2) + "\n", encoding="utf-8-sig")
    (folder / "README.txt").write_text(
        f"{project.name} · {project.episode}\n制作规则：{project.rules}\n组号：{group_id}\n"
        f"镜头数：{len(project.shots)}\n图片数：{len(images)}\n本组进入状态：{notes['本组进入状态']}\n"
        f"本组退出状态：{notes['本组退出状态']}\n镜头与来源：\n" + "\n".join(shot_rows) + "\n",
        encoding="utf-8-sig",
    )
    if pending:
        (folder / "待制作分镜.txt").write_text(
            f"本组 {group_id} 退出状态：{notes['本组退出状态']}\n"
            "下组承接以上状态，继续分配以下批准对白。\n"
            + "\n".join(pending) + "\n", encoding="utf-8-sig",
        )


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
    if project.impacts():
        raise ValueError("请逐格核对当前镜头顺序和图像布局，再确认本版本画面。")
    with TemporaryDirectory(prefix="comicflow-production-") as temporary:
        sidecar = Path(temporary)
        folder, registry = sidecar / "delivery", project_registry(project_path)
        build_delivery(project, project_path, folder, validator, registry)
        return pack_repair(folder, output, validator, baseline, registry, panel_exception)
