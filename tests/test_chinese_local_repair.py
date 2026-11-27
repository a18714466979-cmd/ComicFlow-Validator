from copy import deepcopy

import pytest
from PIL import Image, ImageChops

from src.image_api import EDIT, IMAGE_PROVIDERS, ImageReply, ImageSettings
from src.production_images import approve_candidate, local_patch, png_bytes, prepare_job, store_candidate, store_reply
from src.production_layout import apply_layout, bind_window, windows_for_shots
from src.production_project import ProductionProject
from test_chinese_production_layout import example, render


def config():
    name = "火山方舟 Seedream"
    provider = IMAGE_PROVIDERS[name]
    return ImageSettings(name, provider.base, provider.model, "local-fixture")


def ready_patch(project, path, kind, target, asset, box):
    job, request = prepare_job(project, path, config(), EDIT, kind, target, "合成局部返修", [asset.id], box)
    mock = Image.new("RGB", (asset.width, asset.height), "chartreuse")
    store_reply(path, job, ImageReply((png_bytes(mock),), request_id="synthetic-local-repair"))
    project.image_jobs.append(job)
    local_patch(project, path, job, job["outputs"][0])
    return job, request, mock


def inside(box):
    return box[0] + 8, box[1] + 8, box[0] + 28, box[1] + 28


def test_chinese_repair_revalidates_pixels_and_preserves_all_shared_windows(tmp_path):
    project, path = example(tmp_path, distinct=1, local=3)
    apply_layout(project, path, render(project, path, tmp_path), "合成正反打及净板核对")
    project.structure_review = project.fingerprint()
    windows = windows_for_shots(project)
    shot = project.shots[3]
    plate, box = windows[shot.id]["plate"]
    assert windows[project.shots[0].id]["plate"] == (plate, box)
    original = project.checked_image(path, plate).read_bytes()
    area = inside(box)
    job, _, mock = ready_patch(project, path, "净板", shot.id, plate, area)
    assert "SB01-04，局部01" in job["prompt"]
    with pytest.raises(ValueError, match="替换同名"):
        approve_candidate(project, path, job, 0, plate.filename, "R2", "修复合成小灯", "核对窗体边界")
    forged = deepcopy(job)
    forged["outputs"][0]["patch_sha"] = store_candidate(path, png_bytes(mock))
    with pytest.raises(ValueError, match="差异超出"):
        approve_candidate(project, path, forged, 0, plate.filename, "R2", "修复合成小灯", "核对窗体边界", replace_original=True)
    assert not project.impacts()
    new = approve_candidate(project, path, job, 0, plate.filename, "R2", "修复合成小灯", "核对窗体边界", replace_original=True)
    reopened = ProductionProject.open(path)
    assert reopened.impacts()
    archived = next(image for image in reopened.images if image.id == plate.id)
    assert archived.reference_only and reopened.checked_image(path, archived).read_bytes() == original
    updated = windows_for_shots(reopened)
    share = {shot.id for shot in reopened.shots if windows[shot.id]["plate"] == (plate, box)}
    assert set(reopened.layout["rebind"]) == share
    assert all(updated[identity]["plate"][0].id == new.id and updated[identity]["plate"][1] == box for identity in share)
    assert all(updated[identity]["board"][0].id == windows[identity]["board"][0].id
               and updated[identity]["board"][1] == windows[identity]["board"][1] for identity in updated)
    with Image.open(reopened.checked_image(path, archived)) as old, Image.open(reopened.checked_image(path, new)) as revised:
        assert ImageChops.difference(old.convert("RGBA"), revised.convert("RGBA")).getbbox(alpha_only=False) == area
    assert bind_window(reopened, path, shot.id, "plate", new.id) == box
    assert shot.id not in reopened.layout["rebind"]


def test_chinese_combined_storyboard_and_packed_scene_repair_target_actual_windows(tmp_path):
    project, path = example(tmp_path, distinct=1, local=6, extras=6)
    budget = "道具：无需再并；配角：各自清晰；主角：不丢特写；主配：无可安全组合"
    draft = render(project, path, tmp_path, pack_scenes=True, pack_board=True, budget_note=budget)
    apply_layout(project, path, draft, "核对 10 格和打包场景视图")
    windows = windows_for_shots(project)
    shot = project.shots[7]
    board, box = windows[shot.id]["board"]
    another = windows[project.shots[0].id]["board"][1]
    with pytest.raises(ValueError, match="对应的故事板格"):
        prepare_job(project, path, config(), EDIT, "故事板", shot.id, "合成局部", [board.id], inside(another))
    job, _, _ = ready_patch(project, path, "故事板", shot.id, board, inside(box))
    assert "第 08 镜选区" in job["prompt"]
    revised = approve_candidate(project, path, job, 0, board.filename, "R2", "修复单格", "实际局部核对", replace_original=True)
    assert "10panel" in revised.filename and windows_for_shots(project)[shot.id]["board"] == (revised, box)

    sheet = next(row for row in project.layout["output"]["sheets"] if row["kind"] == "plate")
    cell = next(item for item in sheet["cells"] if item["view"][1] == "main")
    packed = next(image for image in project.images if image.id == sheet["asset"])
    job, _, _ = ready_patch(project, path, "场景", "", packed, inside(cell["box"]))
    scene = approve_candidate(project, path, job, 0, packed.filename, "R2", "修复主视窗内灯罩", "窗边及方位核对", replace_original=True)
    assert sheet["asset"] == scene.id and cell["view"][1] == "main"
