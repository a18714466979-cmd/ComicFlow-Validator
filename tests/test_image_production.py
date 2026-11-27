"""Synthetic image jobs exercise provider contracts and candidate promotion."""

import base64
import json
from io import BytesIO

import pytest
from PIL import Image, ImageChops, ImageDraw

from src.image_api import (
    EDIT, IMAGE_PROVIDERS, REFERENCE, TEXT, ImageReply, ImageRequestError, ImageSettings,
    build_image_request, query_image, submit_image,
)
from src.production_images import approve_candidate, candidate_path, local_patch, prepare_job, store_reply
from src.production_project import ProductionProject, Shot


def render(color, size=(320, 180)):
    stream = BytesIO()
    Image.new("RGB", size, color).save(stream, format="PNG")
    return stream.getvalue()


def settings(provider):
    preset = IMAGE_PROVIDERS[provider]
    base = preset.base or "https://sample.example.com/api/v1"
    return ImageSettings(provider, base, preset.model or "gpt-image-2", "test-secret-key", "demo-id")


@pytest.mark.parametrize("provider", IMAGE_PROVIDERS)
def test_generation_and_reference_contracts(provider):
    adapter = IMAGE_PROVIDERS[provider]
    config = settings(provider)
    request = build_image_request(config, TEXT, "Render a blue signal lamp.")
    body = json.loads(request.data)
    suffix = {"gemini": "/interactions", "dashscope": "/services/aigc/multimodal-generation/generation",
              "tencent": "/", "openrouter": "/images"}.get(adapter.adapter, "/images/generations")
    assert request.full_url == config.base + suffix
    if adapter.adapter == "tencent":
        assert request.get_header("X-tc-action") == "SubmitHunyuanImageJob"
        assert "Credential=demo-id/" in request.get_header("Authorization")
        assert "test-secret-key" not in request.get_header("Authorization")
        assert body["Resolution"] == "1280:720"
    else:
        assert body["model"] == config.model
    picture = render("blue")
    if not adapter.references:
        with pytest.raises(ValueError, match="未提供"):
            build_image_request(config, REFERENCE, "Reference", (picture,))
        return
    request = build_image_request(config, REFERENCE, "Keep identity", (picture,))
    if adapter.adapter == "openai":
        assert request.full_url.endswith("/images/edits")
        assert request.get_header("Content-type").startswith("multipart/form-data")
        assert picture in request.data and b'name="image"' in request.data
    else:
        data = json.loads(request.data)
        paths = {
            "ark": lambda: data["image"].split(",")[1],
            "gemini": lambda: data["input"][1]["data"],
            "dashscope": lambda: data["input"]["messages"][0]["content"][0]["image"].split(",")[1],
            "xai": lambda: data["image"]["url"].split(",")[1],
            "openrouter": lambda: data["input_references"][0]["image_url"]["url"].split(",")[1],
            "tencent": lambda: data["ContentImage"]["ImageBase64"],
        }
        assert base64.b64decode(paths[adapter.adapter]()) == picture
    if adapter.edits:
        edited = build_image_request(config, EDIT, "Localized edit", (picture,), edit_box=(1, 2, 12, 17), mask=b"mask-sample")
        if adapter.adapter == "openai":
            assert b'name="mask"; filename="mask.png"' in edited.data and b"mask-sample" in edited.data
        if provider == "阿里云百炼 万相":
            assert json.loads(edited.data)["parameters"]["bbox_list"] == [[[1, 2, 12, 17]]]


@pytest.mark.parametrize("provider", [key for key in IMAGE_PROVIDERS if key != "腾讯云混元"])
def test_provider_result_shapes_and_secret_free_download(monkeypatch, provider):
    generated = render("wheat")
    image64 = base64.b64encode(generated).decode()
    config = settings(provider)
    adapter = IMAGE_PROVIDERS[provider].adapter
    if adapter == "gemini":
        raw = {"steps": [{"type": "model_output", "content": [{"type": "image", "data": image64}]}]}
    elif adapter == "dashscope":
        raw = {"output": {"choices": [{"message": {"content": [{"image": "data:image/png;base64," + image64}]}}]}}
    elif adapter == "silicon":
        raw = {"images": [{"url": "https://download.example.com/sample.png?temporary=token"}]}
    else:
        raw = {"data": [{"b64_json": image64}]}

    def network(request, limit):
        if request.get_method() == "GET":
            assert not request.has_header("Authorization")
            return generated, ""
        return json.dumps(raw).encode(), "synthetic-request"

    monkeypatch.setattr("src.image_api.read_bytes", network)
    monkeypatch.setattr("src.image_api.socket.getaddrinfo", lambda *_args, **_kwargs: [(0, 0, 0, "", ("8.8.8.8", 443))])
    request = build_image_request(config, TEXT, "候选图")
    assert submit_image(config, request) == ImageReply((generated,), request_id="synthetic-request")


def test_async_image_task_resumes_from_project_without_storing_key(tmp_path, monkeypatch):
    config = settings("腾讯云混元")
    path = tmp_path / "任务.cfproject"
    project = ProductionProject("合成项目", "EP01", "SB01")
    job, request = prepare_job(project, path, config, TEXT, "场景", "", "夜间空试验间", [], ())
    project.image_jobs.append(job)
    states = iter((
        {"JobId": "job-synthetic-01", "RequestId": "accepted"},
        {"JobStatusCode": "2", "RequestId": "running"},
        {"JobStatusCode": "5", "ResultImage": [base64.b64encode(render("wheat")).decode()], "RequestId": "finished"},
    ))

    def network(request, limit):
        action = request.get_header("X-tc-action")
        if action.startswith("Query"):
            assert json.loads(request.data) == {"JobId": "job-synthetic-01"}
        return json.dumps({"Response": next(states)}).encode(), ""

    monkeypatch.setattr("src.image_api.read_bytes", network)
    store_reply(path, job, submit_image(config, request))
    project.save(path)
    saved = path.read_text(encoding="utf-8")
    assert "test-secret-key" not in saved and "demo-id" not in saved
    restored = ProductionProject.open(path)
    job = restored.image_jobs[0]
    assert job["status"] == "queued" and job["task_id"] == "job-synthetic-01"
    store_reply(path, job, query_image(config, job["task_id"]))
    assert job["status"] == "queued"
    store_reply(path, job, query_image(config, job["task_id"]))
    assert job["status"] == "ready" and not restored.images
    assert candidate_path(path, job["outputs"][0]["sha256"]).is_file()


def test_unsafe_or_missing_output_leaves_request_uncertain(monkeypatch):
    config = settings("硅基流动")
    captured = []
    raw = {"images": [{"url": "https://example.com/private.png"}]}

    def network(request, limit):
        captured.append(request.get_method())
        return json.dumps(raw).encode(), ""

    monkeypatch.setattr("src.image_api.read_bytes", network)
    monkeypatch.setattr("src.image_api.socket.getaddrinfo", lambda *_args, **_kwargs: [(0, 0, 0, "", ("127.0.0.1", 443))])
    with pytest.raises(ImageRequestError) as error:
        submit_image(config, build_image_request(config, TEXT, "测试"))
    assert error.value.uncertain and captured == ["POST"]


def test_jpeg_reply_preserves_native_bytes_and_adds_png_candidate(tmp_path):
    stream = BytesIO()
    Image.new("RGB", (320, 180), "wheat").save(stream, format="JPEG")
    jpg = stream.getvalue()
    path = tmp_path / "候选.cfproject"
    job = {}
    store_reply(path, job, ImageReply((jpg,)))
    out = job["outputs"][0]
    assert out["format"] == "JPEG" and out["sha256"] != out["received_sha256"]
    assert candidate_path(path, out["received_sha256"], "JPEG").read_bytes() == jpg
    with Image.open(candidate_path(path, out["sha256"])) as image:
        assert image.size == (320, 180) and image.format == "PNG"


def test_reference_plate_and_local_repair_in_one_project(tmp_path):
    path = tmp_path / "合成测试.cfproject"
    project = ProductionProject("合成场景", "EP01", "SB01")
    source = project.import_source("批准.md", "R1", "值班员看向安装在门左侧的蓝色信号灯。")
    shot = Shot(source=source.id, anchor="门左侧蓝灯", scene="试验间", plate_note="门右侧向左平视",
                fields={"机位空间": "门右侧向左平视", "连续性": "蓝灯固定在门左侧"})
    project.shots.append(shot)
    source_path = tmp_path / "approved.png"
    source_path.write_bytes(render("steelblue"))
    old = project.import_image(path, source_path, "approved_角色.png", version="R3", action="直接复用",
                               reason="合成批准参考", inspection="颜色和像素已核对", reference_only=True)
    source_path.write_bytes(render("gray"))
    board = project.import_image(path, source_path, "storyboard_1panel_bw_16x9.png", action="直接复用",
                                 reason="合成构图", inspection="门左侧信号灯与格号位置已核对")
    config = settings("火山方舟 Seedream")

    def send(mode, purpose, prompt, refs, results, *, box=(), target=""):
        job, request = prepare_job(project, path, config, mode, purpose, target, prompt, refs, box)
        project.image_jobs.append(job)
        store_reply(path, job, ImageReply((results,), request_id="mock-request"))
        project.save(path)
        return job, json.loads(request.data)

    char_job, request = send(REFERENCE, "角色", "批准角色试制", [old.id], render("wheat"))
    assert request["image"].startswith("data:image/png;base64,")
    assert not any(image.filename == "other_characters_值班员_16x9.png" for image in project.images)
    assert char_job["references"][0]["version"] == "R3"
    approve_candidate(project, path, char_job, 0, "other_characters_值班员_16x9.png", "R1", "补缺角色图", "合成身份标记已核对")
    with pytest.raises(ValueError, match="批准故事板"):
        prepare_job(project, path, config, REFERENCE, "净板", shot.id, "重建净板", [old.id], ())
    plate_job, request = send(REFERENCE, "净板", "只生成空场景", [board.id], render("forestgreen"), target=shot.id)
    assert "局部01" in request["prompt"] and "门右侧向左平视" in request["prompt"]
    assert shot.plate == ""
    plate = approve_candidate(project, path, plate_job, 0, "scene_试验间_details_01_16x9.png", "R5",
                              "补缺镜头01净板", "合成机位和门位置已核对")
    assert shot.plate == plate.id
    assert project.checked_image(path, plate).read_bytes() == render("forestgreen")
    original = project.checked_image(path, plate)

    # The mock provider deliberately returns unrelated colors outside the target.
    altered = Image.new("RGB", (320, 180), "red")
    ImageDraw.Draw(altered).rectangle((8, 8, 23, 23), fill="yellow")
    buffer = BytesIO()
    altered.save(buffer, format="PNG")
    patch_job, _ = send(EDIT, "净板", "只更换信号灯颜色", [plate.id], buffer.getvalue(),
                        box=(8, 8, 24, 24), target=shot.id)
    record = patch_job["outputs"][0]
    with pytest.raises(ValueError, match="合成图"):
        approve_candidate(project, path, patch_job, 0, plate.filename, "R6", "修复信号灯", "试验选区", replace_original=True)
    local_patch(project, path, patch_job, record)
    updated = approve_candidate(project, path, patch_job, 0, plate.filename, "R6", "修复信号灯",
                                "选区及边界检查完成", replace_original=True)
    assert original.read_bytes() == render("forestgreen")
    assert updated.originals == (plate.id,) and shot.plate == updated.id and record["outside_pixels_equal"]
    with Image.open(original) as old_pic, Image.open(project.checked_image(path, updated)) as new_pic:
        assert ImageChops.difference(old_pic.convert("RGBA"), new_pic).getbbox(alpha_only=False) == (8, 8, 24, 24)
    assert len([image for image in project.images if not image.reference_only]) == 3
    assert ProductionProject.open(path).image_jobs[-1]["status"] == "approved"
