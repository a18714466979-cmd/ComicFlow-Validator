"""Prepare batch requests with the same provider adapters and rules as the single-group editor."""

import json
import re
from datetime import datetime, timezone
from hashlib import sha256

from .camera_preflight import boundary_camera_cuts, camera_findings_text
from .image_api import REFERENCE, TEXT
from .production_drafting import (
    SD2_TASK, SHOT_TASK, build_context, checked_output, instructions_for, read_candidate,
)
from .production_images import prepare_job, storyboard_job_page
from .production_project import ProductionProject, identifier
from .text_api import build_text_request


TEXT_KINDS = ("shot", "prompt")
IMAGE_KINDS = ("board", "plate", "asset")
ASSET_KINDS = ("角色", "道具 / HUD", "场景")


def target_shot(project, shot_id):
    for shot in project.shots:
        if shot.id == shot_id:
            return shot
    raise ValueError("目标镜头已经改变，请核对分组。")


def prepare_text(project, plan, row, settings, *, include_neighbors=True):
    shot = target_shot(project, row["shot_id"])
    source = next((item for item in project.sources if item.id == shot.source), None)
    record = next((item for item in plan["shots"] if item["id"] == shot.id), None)
    if source is None or record is None:
        raise ValueError("镜头缺少批准源稿或源段映射。")
    number = record["line_no"]
    task = SHOT_TASK if row["kind"] == "shot" else SD2_TASK
    # The episode planner binds every request to one stable shot, even when a long
    # source line supplies several shots. Only that shot's exact excerpt may be staged.
    context, payload = build_context(project, source, task, number, number, shot.id)
    data = json.loads(payload)
    data["approved_source"]["lines"] = {str(number): record["text"]}
    data.pop("existing_shots", None)
    data["target"] = {"id": shot.id, "scene": shot.scene, "anchor": shot.anchor, "fields": shot.fields}
    if task == SHOT_TASK and include_neighbors:
        index = project.shots.index(shot)
        context["camera_neighbors"] = True
        data["adjacent_shots"] = [
            {"ordinal": other + 1, "id": project.shots[other].id,
             "fields": {key: project.shots[other].fields[key] for key in
                        ("景别", "机位/角度", "机位空间", "动作起止", "连续性")
                        if project.shots[other].fields.get(key)}}
            for other in (index - 1, index + 1) if 0 <= other < len(project.shots)
        ]
    lines = {line.id: line for line in project.lines}
    data["approved_dialogue"] = [{"speaker": lines[i].speaker, "approved": lines[i].text[a:b]}
                                 for i, a, b in shot.dialogue]
    instructions = instructions_for(task, project.rules)
    if task == SHOT_TASK:
        instructions += "\n只给所选源镜一个分镜建议，镜号和批准对白保持不变。"
    body = json.dumps(data, ensure_ascii=False, sort_keys=True)
    context["fingerprint"] = sha256(body.encode()).hexdigest()
    if settings is not None:
        build_text_request(settings, instructions, body)
    return task, context, instructions, body


def text_result(task, context, reply, settings):
    value = read_candidate(task, context, reply.text)
    if task == SHOT_TASK and len(value["shots"]) != 1:
        raise ValueError("该批量任务绑定一镜，模型应返回一个镜头。")
    return {"id": identifier(), "task": task, "context": context, "output": value,
            "provider": settings.provider, "model": reply.model or settings.model, "request_id": reply.request_id,
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def apply_fields(project, row, candidate):
    output = checked_output(candidate["task"], candidate["context"], candidate["output"])
    shot = target_shot(project, row["shot_id"])
    additions = output["prompt"] if row["kind"] == "prompt" else output["shots"][0]["fields"]
    shot.fields = {**shot.fields, **additions}


def check_neighbor_cameras(workspace, episode, project):
    paths = workspace.group_paths(episode)
    for before, after in zip(paths, paths[1:]):
        if before.stem == project.group:
            findings = boundary_camera_cuts(project, ProductionProject.open(after))
        elif after.stem == project.group:
            findings = boundary_camera_cuts(ProductionProject.open(before), project)
        else:
            continue
        if findings:
            raise ValueError(camera_findings_text(findings))


def prepare_image(workspace, project, path, row, settings, spec):
    if row["kind"] == "board":
        check_neighbor_cameras(workspace, row["episode"], project)
    kind = {"asset": spec.get("kind"), "board": "故事板", "plate": "净板"}[row["kind"]]
    target = row["shot_id"]
    references = []
    prompt = ""
    if row["kind"] == "asset":
        prompt = f"身份／地点／物件：{spec['title']}\n本次状态：{spec['state']}\n批准描述：{spec['brief']}"
    elif row["kind"] == "plate":
        # Chinese ten-shot pages have two different approved boards.
        first, last, _ = storyboard_job_page(project, target)
        board_pattern = rf"storyboard.*(?<!\d){last - first + 1}panel"
        boards = [item for item in project.images if not item.reference_only
                  and re.search(board_pattern, item.filename, re.IGNORECASE)]
        if len(boards) != 1:
            raise ValueError("请先批准该镜所在的故事板页。")
        references = [boards[0].id]
    else:
        references = workspace.group_reference_ids(row["episode"], row["group_id"])
    return prepare_job(project, path, settings, REFERENCE if references else TEXT, kind, target,
                       prompt, references, ())
