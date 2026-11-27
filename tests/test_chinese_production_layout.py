"""Chinese layout checks based on the actual output PNGs and review archive."""

import os
import runpy
from io import BytesIO
from zipfile import ZipFile

import pytest
from PIL import Image, ImageChops, ImageOps

from src.asset_registry import sha256_file
from src.production_export import preview_chinese_layout, write_chinese_layout
from src.production_images import image_prompt
from src.production_layout import apply_layout, render_layout
from src.production_project import ProductionProject
from src.shot_review import load_shots
from src.storyboard_review import ReviewResult, index_members
from test_chinese_production_text import project_with_shots
from windows_smoke import attach_chinese_layout


def example(tmp_path, distinct=2, local=3, extras=0):
    project = project_with_shots("SB01", "无对白", 10, [])
    path = tmp_path / "中文项目.cfproject"
    source = tmp_path / "inputs"
    source.mkdir()
    attach_chinese_layout(project, path, source, distinct=distinct, local=local, extras=extras)
    return project, path


def render(project, path, tmp_path, **options):
    directory = tmp_path / "draft"
    directory.mkdir(exist_ok=True)
    return render_layout(project, path, directory, **options)


def verify_preview(project, path, temporary):
    archive = preview_chinese_layout(project, path, temporary)
    with ZipFile(archive) as packed:
        assert packed.testzip() is None
        members = index_members(packed)
        rows = load_shots(ReviewResult(0, "", archive, members, []))
        assert [row.shot for row in rows] == [f"SB01-{n:02d}" for n in range(1, 11)]
        assets = {image.id: image for image in project.images}
        for shot, row in zip(project.shots, rows):
            assert not row.notices, row.notices
            for kind, name, box in (("board", row.storyboard, row.board_box),
                                    ("plate", f"{row.group}/{row.plate.filename}", row.plate_box)):
                assert box
                with Image.open(BytesIO(packed.read(members[name]))) as picture:
                    picture.load()
                    assert picture.width * 9 == picture.height * 16
                    x, y, r, b = box
                    assert 0 <= x < r <= picture.width and 0 <= y < b <= picture.height
                    assert (r-x)*9 == (b-y)*16
                    bound = project.layout["inputs"][shot.id][kind]
                    with Image.open(project.checked_image(path, assets[bound["image"]])) as source:
                        expected = source.crop(bound["box"]).convert("RGB").resize((r-x, b-y), Image.Resampling.LANCZOS)
                    assert ImageChops.difference(picture.crop(box), expected).getbbox() is None
        record = packed.read(members["SB01/SB01_shot_details.txt"]).decode("utf-8-sig")
        prompt = packed.read(members["SB01/SD2_prompt.txt"]).decode("utf-8-sig")
        assert "图格布局：" in record and "实际画面窗口：" in record
        assert not any(field in prompt for field in ("图格布局", "场景视图映射", "九图优化记录", "实际画面窗口"))
        return rows, record


def test_default_ten_panels_use_six_and_four_and_preserve_original_views(tmp_path):
    project, path = example(tmp_path, distinct=1)
    originals = {item.filename: item.digest for item in project.images if "_main_" in item.filename or "_reverse_" in item.filename}
    draft = render(project, path, tmp_path)
    assert [len(sheet.slots) for sheet in draft.sheets if sheet.kind == "board"] == [6, 4]
    assert draft.chinese["count"] == 5
    apply_layout(project, path, draft, "合成样例逐格看过实际窗口、镜号及正反打")
    project = ProductionProject.open(path)
    rows, record = verify_preview(project, path, tmp_path)
    assert "storyboard_01_6panel" in rows[5].storyboard and "storyboard_02_4panel" in rows[6].storyboard
    assert rows[0].plate.slot == rows[3].plate.slot and rows[0].plate_box == rows[3].plate_box
    assert "最终总图数=5" in record and "本次排版未触发九图优化" in record
    exported = write_chinese_layout(project, path, tmp_path / "实物导出")
    assert {name: sha256_file(exported / name) for name in originals} == originals
    first = image_prompt(project, "故事板", project.shots[5].id, "文生图")
    second = image_prompt(project, "故事板", project.shots[6].id, "文生图")
    assert "SB01-06" in first and "SB01-07" not in first
    assert "SB01-07" in second and "SB01-06" not in second


def test_multiscene_details_are_paged_and_same_camera_is_reused(tmp_path):
    project, path = example(tmp_path, local=5)
    draft = render(project, path, tmp_path, mixed=True)
    assert len([sheet for sheet in draft.sheets if sheet.kind == "plate"]) == 3
    apply_layout(project, path, draft, "合成样例分开核对两地点的 10 个批准机位")
    rows, record = verify_preview(project, path, tmp_path)
    assert "场景资产模式：多场景局部" in record and "场景清单：南厅；北廊" in record
    assert {row.plate.scene for row in rows} == {"南厅", "北廊"}
    assert not any(not asset.reference_only and any(tag in asset.filename for tag in ("_main_", "_reverse_"))
                   for asset in project.images)
    assert "最终总图数=5" in record


def test_scene_packing_precedes_board_packing_and_matches_chinese_geometry_validator(tmp_path):
    project, path = example(tmp_path, distinct=1, local=2, extras=5)
    note = "道具：无可合项；配角：合格原图不能再缩；主角：未新增；主配：无可配对"
    with pytest.raises(ValueError, match="10 张"):
        render(project, path, tmp_path)
    with pytest.raises(ValueError, match="须逐项"):
        render(project, path, tmp_path, pack_scenes=True, budget_note="已尽量合并")
    with pytest.raises(ValueError, match="仅在前序优化后"):
        render(project, path, tmp_path, pack_scenes=True, pack_board=True, budget_note=note)
    draft = render(project, path, tmp_path, pack_scenes=True, budget_note=note)
    assert draft.chinese["count"] == 8 and len(draft.sheets) == 3
    apply_layout(project, path, draft, "逐格核对合成正反打、净板及布局实际坐标")
    _, record = verify_preview(project, path, tmp_path)
    assert "场景合并来源：常规" in record and "南厅/main；南厅/reverse；南厅/details；南厅/details" in record
    assert "原始总图数=10" in record and "最终总图数=8" in record
    validator = os.environ.get("COMICFLOW_TEST_CN_VALIDATOR")
    if validator:
        checks = runpy.run_path(validator)
        layouts = {}
        for sheet in project.layout["output"]["sheets"]:
            asset = next(image for image in project.images if image.id == sheet["asset"])
            count = len(sheet["cells"]) if sheet["kind"] == "board" else None
            layouts[asset.filename] = ((asset.width, asset.height), count)
        assert not checks["cell_layout_errors"](record, layouts)
        assert not checks["budget_record_errors"](record, "scene", 8)


def test_board_packing_needs_remaining_overflow_and_scene_record(tmp_path):
    project, path = example(tmp_path, distinct=1, local=6, extras=6)
    note = "道具：无需再并；配角：各自清晰；主角：不丢特写；主配：无可安全组合"
    draft = render(project, path, tmp_path, pack_scenes=True, pack_board=True, budget_note=note)
    assert draft.chinese["count"] == 9 and sum(s.kind == "board" for s in draft.sheets) == 1
    apply_layout(project, path, draft, "确认 10 格单板可读并核对两张场景合图")
    rows, record = verify_preview(project, path, tmp_path)
    assert "故事板排版模式：九图合并" in record and "最终总图数=9" in record
    assert len({row.storyboard for row in rows}) == 1


def test_chinese_common_scene_rejects_mirror_missing_and_wrong_camera(tmp_path):
    project, path = example(tmp_path, distinct=1)
    reverse = next(a for a in project.images if "_reverse_" in a.filename)
    main = next(a for a in project.images if "_main_" in a.filename)
    project.images.remove(reverse)
    with pytest.raises(ValueError, match="反打"):
        render(project, path, tmp_path)
    mirrored = tmp_path / "mirror.png"
    with Image.open(project.checked_image(path, main)) as original:
        ImageOps.mirror(original).save(mirrored)
    changed = project.import_image(path, mirrored, reverse.filename, action="直接复用",
                                   reason="合成镜像错误样例", inspection="回归测试")
    with pytest.raises(ValueError, match="水平镜像"):
        render(project, path, tmp_path)
    project.images.remove(changed)
    project.images.append(reverse)
    project.shots[3].fields["机位空间"] = "另一个朝向"
    with pytest.raises(ValueError, match="同一地点、机位、可见范围"):
        render(project, path, tmp_path)
