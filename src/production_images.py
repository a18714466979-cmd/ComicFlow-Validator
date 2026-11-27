"""Keep model images and request evidence separate from approved delivery assets."""

import json
import re
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageChops, ImageDraw, ImageOps

from .asset_registry import sha256_file
from .image_api import EDIT, REFERENCE, MAX_IMAGE_BYTES, MAX_UPLOAD_BYTES, IMAGE_PROVIDERS, ImageReply, ImageSettings, build_image_request
from .production_project import ProductionProject, checked_name, identifier
from .storyboard_preflight import IMAGE_LIMIT


KINDS = ("角色", "道具 / HUD", "场景", "故事板", "净板")
STATUS = {"submitting": "提交待确认", "queued": "已提交，等待查询", "unknown": "结果待核对",
          "failed": "服务未完成", "ready": "待核图", "approved": "已批准", "closed": "已核对后台"}
FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
GUIDANCE = {
    "角色": "同一身份，保持批准的脸、发型、服装、识别装备和具体状态。按需要给正侧背和识别特写，画面清楚。",
    "道具 / HUD": "只列本组实用物件及状态，清楚交代材质、尺度、结构和必要接口，避免无关陈列。",
    "场景": "彩色场景，维持入口、光源、墙面、固定设备的实际位置、可见性和材质。",
    "故事板": "单张16:9黑白线稿故事板，每格16:9，镜头按序各有独立叙事功能；构图紧凑，保留动作因果和空间。",
    "净板": "按所选故事板格重建独立彩色无人净板，保留该机位的高度、朝向、可见范围、固定结构、透视和光向。",
}


def shot_input(project, shot_id):
    return next(((index, shot) for index, shot in enumerate(project.shots, 1) if shot.id == shot_id), (0, None))


def shot_signature(project, kind, target) -> str:
    if kind == "故事板":
        data = [asdict(shot) for shot in project.shots]
        for shot in data:
            shot.pop("plate")
            shot.pop("plate_note")
    elif kind == "净板":
        ordinal, shot = shot_input(project, target)
        if shot is None:
            raise ValueError("请选择有批准资料的目标镜头。")
        data = [ordinal, shot.anchor, shot.source, shot.scene, shot.fields]
    else:
        return ""
    return sha256(json.dumps([project.group, data], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def image_prompt(project, kind, target, mode) -> str:
    lines = [GUIDANCE[kind], "成图为16:9，保留主体有效细节和完整画幅。"]
    if mode == EDIT:
        lines.append("在原图对应选区内完成以下修改，保持该处透视、光影和边缘一致。")
    if kind == "故事板":
        lines.insert(0, f"{project.group}，按已锁定的 {len(project.shots)} 镜排一张。")
        for index, shot in enumerate(project.shots, 1):
            fields = ("景别", "机位/角度", "人物站位", "动作起止", "情绪/表演", "连续性")
            details = "；".join(f"{key} {shot.fields[key]}" for key in fields if shot.fields.get(key))
            lines.append(f"{project.group}-{index:02d} {shot.anchor}。{details}")
    if kind == "净板":
        ordinal, shot = shot_input(project, target)
        if shot:
            fields = ("景别", "机位/角度", "机位空间", "可见范围", "场景/环境", "连续性")
            details = "；".join(f"{key} {shot.fields[key]}" for key in fields if shot.fields.get(key))
            lines.append(f"{project.group}-{ordinal:02d}，局部{ordinal:02d}，地点 {shot.scene}。{details}")
    return "\n".join(lines)


def pin_asset(image):
    return {"id": image.id, "filename": image.filename, "version": image.version, "sha256": image.digest}


def pinned_assets(project, project_path, job):
    current = {image.id: image for image in project.images}
    found = []
    for pin in job["references"]:
        image = current.get(pin["id"])
        if image is None or (image.version, image.digest) != (pin["version"], pin["sha256"]):
            raise ValueError(f"批准参考图版本已变更：{pin['filename']}")
        found.append((image, project.checked_image(project_path, image)))
    return found


def checked_box(box, size):
    if (len(box) != 4 or any(type(value) is not int for value in box)
            or not 0 <= box[0] < box[2] <= size[0] or not 0 <= box[1] < box[3] <= size[1]):
        raise ValueError("请在批准原图内框选有效区域。")
    return tuple(box)


def prepare_job(project, project_path, settings, mode, kind, target, prompt, references, box):
    if kind not in KINDS:
        raise ValueError("请选择候选图的实际用途。")
    if len(set(references)) != len(references):
        raise ValueError("同一张批准参考图只能选择一次。")
    assets = {image.id: image for image in project.images}
    if any(identity not in assets for identity in references):
        raise ValueError("所选批准参考图已移除。")
    sources = [assets[identity] for identity in references]
    if kind == "故事板" and not project.shots:
        raise ValueError("请先保存本组的镜头清单。")
    if kind == "净板" and mode != EDIT:
        _, shot = shot_input(project, target)
        if not shot or not shot.scene.strip() or not (shot.plate_note.strip() or shot.fields.get("机位空间", "").strip()):
            raise ValueError("请选择已填写地点和实际机位的目标镜头。")
        if mode != REFERENCE or not any("storyboard" in item.filename.lower() for item in sources):
            raise ValueError("生成净板需要选择批准故事板作为机位参考。")
    if mode == EDIT:
        if not sources:
            raise ValueError("请先选择要返修的批准原图，参考列表第一张是返修底图。")
        box = checked_box(box, (sources[0].width, sources[0].height))
        if kind == "净板":
            _, shot = shot_input(project, target)
            if not shot or shot.plate != sources[0].id:
                raise ValueError("返修净板时，第一张参考图须为所选镜头当前绑定的净板。")
    else:
        box = ()
    prompt = prompt.strip()
    requirements = image_prompt(project, kind, target, mode)
    if prompt and not prompt.startswith(requirements):
        prompt = requirements + "\n" + prompt
    elif not prompt:
        raise ValueError("请填写具体生图内容或先载入提示模板。")
    job = {
        "id": identifier(), "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "submitting",
        "provider": settings.provider, "base": settings.base.rstrip("/"), "model": settings.model, "mode": mode,
        "kind": kind, "shot": target if kind == "净板" else "", "shot_signature": shot_signature(project, kind, target),
        "prompt": prompt, "references": [pin_asset(item) for item in sources], "box": list(box), "outputs": [],
    }
    return job, request_for_job(project, project_path, settings, job)


def png_bytes(image: Image.Image, **options) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG", **options)
    return stream.getvalue()


def request_for_job(project, project_path, settings, job):
    sources = pinned_assets(project, project_path, job)
    if sum(path.stat().st_size for _, path in sources) > MAX_UPLOAD_BYTES:
        raise ValueError("参考图合计超过本地请求大小限制。")
    mode, box = job["mode"], tuple(job["box"])
    references = tuple(path.read_bytes() for _, path in sources)
    mask = b""
    prompt = job["prompt"] + "\n输出一张图。"
    if mode == EDIT:
        original = sources[0][0]
        prompt += (f"\n第一张是批准底图（{original.width}×{original.height}），"
                   f"修改范围为原图像素坐标 {box}，请与原图对齐。")
        if IMAGE_PROVIDERS[settings.provider].adapter == "openai":
            overlay = Image.new("RGBA", (original.width, original.height), (0, 0, 0, 255))
            ImageDraw.Draw(overlay).rectangle((box[0], box[1], box[2]-1, box[3]-1), fill=(0, 0, 0, 0))
            mask = png_bytes(overlay)
    return build_image_request(settings, mode, prompt, references, edit_box=box or None, mask=mask)


def picture(raw):
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("图片文件超过本地候选文件大小限制。")
    with Image.open(BytesIO(raw)) as source:
        kind = source.format
        if kind not in FORMATS or source.width * source.height > 32_000_000:
            raise ValueError("请选择可复核的 PNG、JPEG 或 WebP 图片，最多 3200 万像素。")
        if getattr(source, "n_frames", 1) != 1:
            raise ValueError("候选图需要单帧图像。")
        source.load()
        rotated = source.getexif().get(274, 1) not in (None, 1)
        return ImageOps.exif_transpose(source), kind, rotated


def store_candidate(project_path: Path, data: bytes, kind="PNG") -> str:
    digest = sha256(data).hexdigest()
    directory = project_path.with_suffix(".candidates")
    directory.mkdir(exist_ok=True)
    target = directory / (digest + FORMATS[kind])
    if not target.exists():
        with NamedTemporaryFile(dir=directory, delete=False) as file:
            temporary = Path(file.name)
            try:
                file.write(data)
                file.close()
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    if sha256_file(target) != digest:
        raise ValueError("候选文件与登记的指纹不符。")
    return digest


def candidate_path(project_path, digest, kind="PNG"):
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("候选图片指纹格式错误。")
    path = project_path.with_suffix(".candidates") / (digest + FORMATS[kind])
    if not path.is_file() or sha256_file(path) != digest:
        raise ValueError("找不到当前候选图片，或内容已变化。")
    return path


def store_reply(project_path, job, reply: ImageReply) -> None:
    if reply.task_id:
        job["task_id"] = reply.task_id
    if reply.request_id:
        job.setdefault("request_id", reply.request_id)
        job["last_request_id"] = reply.request_id
    job["status"] = reply.status
    if reply.status != "ready":
        return
    outputs = []
    for data in reply.results:
        image, original_format, rotated = picture(data)
        native = store_candidate(project_path, data, original_format)
        normalized = (store_candidate(project_path, png_bytes(image, icc_profile=image.info.get("icc_profile")))
                      if original_format != "PNG" or rotated else native)
        outputs.append({"sha256": normalized, "received_sha256": native,
                        "format": original_format, "width": image.width, "height": image.height})
    if not outputs:
        raise ValueError("没有可登记的候选图片。")
    job["outputs"] = outputs
    job.pop("message", None)


def local_patch(project, project_path, job, output, candidate_box=None):
    if job["mode"] != EDIT:
        raise ValueError("此候选不属于局部编辑。")
    base_path = pinned_assets(project, project_path, job)[0][1]
    candidate = candidate_path(project_path, output["sha256"])
    original, _, _ = picture(base_path.read_bytes())
    generated, _, _ = picture(candidate.read_bytes())
    original = original.convert("RGBA")
    generated = generated.convert("RGBA")
    area = checked_box(job["box"], original.size)
    if candidate_box is None:
        if generated.size != original.size:
            raise ValueError("候选与原图尺寸不同，请在候选中框选对应局部。")
        candidate_box = area
    candidate_box = checked_box(candidate_box, generated.size)
    patch = generated.crop(candidate_box)
    size = (area[2] - area[0], area[3] - area[1])
    aligned = patch.size != size
    if aligned:
        if abs(patch.width / patch.height - size[0] / size[1]) > 0.04 * (size[0] / size[1]):
            raise ValueError("两处局部的宽高比例差异过大，请重新框选对应区域。")
        patch = patch.resize(size, Image.Resampling.LANCZOS)
    result = original.copy()
    result.paste(patch, area[:2])
    encoded = png_bytes(result, icc_profile=original.info.get("icc_profile"))
    reopened, _, _ = picture(encoded)
    differences = ImageChops.difference(original, reopened).getbbox(alpha_only=False)
    if differences is None:
        raise ValueError("合成后实际像素无变化，请核对修改目标。")
    x0, y0, x1, y1 = differences
    if not (area[0] <= x0 < x1 <= area[2] and area[1] <= y0 < y1 <= area[3]):
        raise ValueError("局部合成的像素差异超出批准选区。")
    output.update(patch_sha=store_candidate(project_path, encoded), patch_source_box=list(candidate_box),
                  aligned=aligned, outside_pixels_equal=True)


def approve_candidate(project: ProductionProject, project_path: Path, job: dict, output_index: int,
                      filename: str, version: str, reason: str, inspection: str, *, replace_original=False):
    if job["status"] != "ready" or not 0 <= output_index < len(job["outputs"]):
        raise ValueError("请选择还待批准的候选图片。")
    if job["shot_signature"] != shot_signature(project, job["kind"], job["shot"]):
        raise ValueError("镜头或绑定场景已变化，请按当前资料核对后重新起草。")
    sources = pinned_assets(project, project_path, job)
    output = job["outputs"][output_index]
    editing = job["mode"] == EDIT
    digest = output.get("patch_sha", "") if editing else output["sha256"]
    if editing and not output.get("outside_pixels_equal"):
        raise ValueError("局部编辑需先生成合成图，并确认选区外像素核对。")
    path = candidate_path(project_path, digest)
    with Image.open(path) as image:
        if abs(image.width / image.height - 16 / 9) > 0.006:
            raise ValueError(f"候选实际尺寸为 {image.width}×{image.height}。请先核对正式图的 16:9 版式。")
        if image.convert("RGBA").getchannel("A").getextrema()[0] != 255:
            raise ValueError("正式交付要求不透明实底。")
    filename = checked_name(filename.strip())
    if job["kind"] == "故事板" and not re.search(rf"storyboard.*(?<!\d){len(project.shots)}panel", filename, re.I):
        raise ValueError("故事板文件名需含实际格数，例如 storyboard_8panel_bw_16x9.png。")
    if job["kind"] == "净板" and "_details" not in filename.lower() and "场景合辑" not in filename:
        raise ValueError("净板应使用包含 details 的正式场景文件名。")
    if not reason.strip() or not inspection.strip() or any(x in reason + inspection for x in "|\r\n"):
        raise ValueError("请填写单行处理理由和实际核图结果。")
    base_image = sources[0][0] if editing else None
    if replace_original and (base_image is None or base_image.reference_only or base_image.filename != filename):
        raise ValueError("替换需选择同名的现行正式资产，并保留批准原图。")
    if replace_original and version.strip() == base_image.version:
        raise ValueError("替换正式图需要新版本号。")
    formal_count = sum(not item.reference_only for item in project.images)
    if formal_count + (not replace_original) > IMAGE_LIMIT:
        raise ValueError(f"批准后会超出 {IMAGE_LIMIT} 张正式图上限，请先调整资产计划。")
    if job["kind"] == "故事板" and not replace_original and any(
        "storyboard" in item.filename.lower() for item in project.images if not item.reference_only
    ):
        raise ValueError("本组已有正式故事板，可按批准原图走局部返修，或先处理旧图绑定。")

    images = project.images[:]
    bindings = [shot.plate for shot in project.shots]
    previous_job = job.copy()
    try:
        if replace_original:
            preserved = replace(base_image, filename=f"原图_{base_image.id[:12]}.png", reference_only=True)
            project.images[project.images.index(base_image)] = preserved
        asset = project.import_image(
            project_path, path, filename, version=version, reason=reason, inspection=inspection,
            action="局部补缺/修复" if editing else "新生成",
            originals=tuple(item.id for item, _ in sources),
            origin_label=f"AI {job['provider']} / {job['model']} / {job['id']}",
        )
        if replace_original:
            for shot in project.shots:
                if shot.plate == base_image.id:
                    shot.plate = asset.id
        if job["kind"] == "净板":
            shot_input(project, job["shot"])[1].plate = asset.id
        job.update(status="approved", approved_image=asset.id, approved_output=output_index)
        project.save(project_path)
    except Exception:
        project.images = images
        for shot, plate in zip(project.shots, bindings):
            shot.plate = plate
        job.clear()
        job.update(previous_job)
        raise
    return asset


def provenance_rows(project, images):
    approved = {image.id: image for image in images}
    rows = []
    for job in project.image_jobs:
        image = approved.get(job.get("approved_image"))
        if not image:
            continue
        source = "；".join(f"{ref['filename']}@{ref['version']} ({ref['sha256']})" for ref in job["references"]) or "无"
        channel = " / ".join((job["provider"], job["model"], job["mode"]))
        job_id = job.get("task_id") or job.get("request_id") or job["id"]
        details = (image.filename, channel, job_id, source, image.digest)
        rows.append("- " + " | ".join(re.sub(r"[|\r\n]", " ", value) for value in details))
    return rows
