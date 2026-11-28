"""Synthetic layout and adjoining-group export use actual decoded windows."""

import json
from io import BytesIO
from shutil import copytree
from zipfile import ZipFile

import pytest
from PIL import Image, ImageDraw

from src.production_dialogue import plan_project_dialogue, select_scope
from src.production_export import publish_batch, preview_project
from src.production_handoff import boundary_report, confirm_boundary, defer_tail
from src.production_layout import add_mark, apply_layout, bind_window, render_layout, square_layout, windows_for_shots
from src.production_project import ProductionProject, Shot
from src.shot_review import image_windows, load_shots
from src.storyboard_review import ReviewResult, index_members
from test_production_project import production, validator


@pytest.mark.parametrize("count", range(1, 13))
def test_actual_sheet_windows_do_not_overlap(count):
    side, cells = square_layout(count)
    covered = set()
    assert len(cells) == count
    for x, y, size in cells:
        window = {(a, b) for a in range(x, x + size) for b in range(y, y + size)}
        assert not (covered & window)
        assert all(0 <= a < side and 0 <= b < side for a, b in window)
        covered |= window
    if count not in (2, 3, 5):
        assert len(covered) == side * side


def test_read_actual_window_with_windows_line_endings():
    entry = "实际画面窗口：\r\n- SB01-01 | board.png | 0,0,320,180 | plate.png | 0,0,320,180\r\n"
    assert image_windows(entry, "SB01")["SB01-01"] == [
        ("board.png", (0, 0, 320, 180), "plate.png", (0, 0, 320, 180))
    ]


def attach(project, path, shot, number):
    for kind in ("board", "plate"):
        sample = path.parent / "source-test.png"
        layer = Image.new("RGB", (480, 270), "white" if kind == "board" else (35, 90, 170))
        draw = ImageDraw.Draw(layer)
        fill = (number * 9, ) * 3 if kind == "board" else (25 + number * 7, 116, 82)
        draw.rectangle((80, 50, 360, 230), fill=fill, outline="black", width=3)
        draw.line((30 + number, 30, 400, 240), fill="black", width=3)
        layer.save(sample)
        asset = project.import_image(path, sample, f"{kind}_源格{number}.png", action="直接复用",
                                     reason="合成测试的独立16:9批准窗口", inspection="尺寸与边界可读",
                                     reference_only=True)
        bind_window(project, path, shot.id, kind, asset.id)


def lay(project, path, directory, *, mixed=False):
    directory.mkdir()
    draft = render_layout(project, path, directory, mixed)
    apply_layout(project, path, draft, "按实际像素核对合成板格、编号及彩色局部")
    return draft


def test_insert_blocks_export_until_reflow_and_updates_real_files(production, validator, tmp_path):
    project = ProductionProject.open(production)
    for number, shot in enumerate(project.shots, 1):
        attach(project, production, shot, number)
    lay(project, production, tmp_path / "layout-before")
    earlier = project.shots[1]
    inserted = Shot(source=earlier.source, anchor="明确的新增动作", scene=earlier.scene,
                    plate_note=earlier.plate_note, fields={**earlier.fields, "景别": "特写", "本格新增叙事功能": "窗闩回位"})
    project.shots.insert(1, inserted)
    attach(project, production, inserted, 10)
    assert "storyboard_8panel_bw_16x9.png" in project.impacts()
    with pytest.raises(ValueError, match="重新排版"):
        preview_project(project, production, validator, tmp_path)
    layout = lay(project, production, tmp_path / "layout-after")
    assert layout.sheets[0].path.name == "storyboard_9panel_bw_16x9.png"
    preview = preview_project(project, production, validator, tmp_path)
    with ZipFile(preview) as archive:
        shots = load_shots(ReviewResult(0, "", preview, index_members(archive), []))
        assert len(shots) == 9 and inserted.id in shots[1].production
        assert earlier.id in shots[2].production and shots[2].plate.slot == "局部03"
        assert "镜头数：9" in archive.read("README.txt").decode("utf-8-sig")
        with Image.open(BytesIO(archive.read(shots[1].storyboard))) as image:
            x0, y0, x1, y1 = shots[1].board_box
            assert image.getpixel(((x0+x1)//2, (y0+y1)//2)) == (90, 90, 90)
            x0, y0, x1, y1 = shots[2].board_box
            assert image.getpixel(((x0+x1)//2, (y0+y1)//2)) == (18, 18, 18)
        for shot in shots:
            for filename, coordinates in ((shot.storyboard, shot.board_box), (f"SB01/{shot.plate.filename}", shot.plate_box)):
                with Image.open(BytesIO(archive.read(filename))) as picture:
                    assert picture.width * 9 == picture.height * 16
                    assert coordinates and coordinates[2] <= picture.width and coordinates[3] <= picture.height
                    with picture.crop(coordinates) as window:
                        assert window.width * 9 == window.height * 16


def test_two_groups_with_shared_plates_dialogue_and_deferred_tail(production, validator, tmp_path):
    left = ProductionProject.open(production)
    right = ProductionProject.open(production)
    rhs = tmp_path / "后组.cfproject"
    copytree(production.with_suffix(".assets"), rhs.with_suffix(".assets"))
    right.group = "SB02"
    first = " ".join(["Hold"] * 54 + ["here."])
    second = " ".join(["Step"] * 14 + ["back."])
    original = f"{first} {second}"
    remainder = "Wait for the lamp."
    cut = len(first) + 1
    planner = validator.with_name("plan_english_dialogue.py")
    for index, (project, path) in enumerate(((left, production), (right, rhs))):
        project.lines.clear()
        source = project.import_source("相邻组合成剧本.md", "R2", original + "\n" + remainder)
        catalog = [{"id": "D100", "speaker": "值班员", "text": original, "sentence_ends": [cut, len(original)]}]
        if index:
            catalog.append({"id": "D101", "speaker": "值班员", "text": remainder})
        project.import_dialogue(source, json.dumps(catalog))
        for number, shot in enumerate(project.shots, 1):
            if index:
                shot.id = f"right-{number}"
            shot.source = source.id
            shot.dialogue.clear()
            if index and number in (3, 4):
                shot.scene = "外廊"
            attach(project, path, shot, number)
        project.notes["场景身份判定"] = "试验间沿用批准灯号；外廊是另一处有独立门框和照明的测试空间" if index else project.notes["场景身份判定"]
        project.notes["本组退出状态"] = project.notes["本组进入状态"] = "门保持关闭，信号灯仍亮"
        scope = plan_project_dialogue(project, planner)
        select_scope(project, scope[index], "SB01" if index else "")
        if index:
            project.shots[0].dialogue = [("D100", cut, len(original))]
            project.shots.append(Shot(id="deferred-tail", source=source.id, anchor="信号灯下一节拍", scene="试验间",
                                      dialogue=[("D101", 0, len(remainder))]))
            defer_tail(project, 8)
        else:
            project.shots[-1].dialogue = [("D100", 0, cut)]
            add_mark(project, project.shots[0].id, "道具移动", "合成信号滑块", (100, 145), (180, 150))
        lay(project, path, tmp_path / f"pair-{index}", mixed=bool(index))
        project.structure_review = project.fingerprint()
        project.save(path)
    left, right = ProductionProject.open(production), ProductionProject.open(rhs)
    text, issues = boundary_report(left, right, planner)
    assert not issues and f"{cut}:{len(original)}" in text
    assert windows_for_shots(right)[right.shots[0].id]["plate"][0].id == right.shots[2].plate
    confirm_boundary(left, right, planner, "核对上一组末格和下一组首格，门和灯状态延续")
    result = publish_batch([(left, production), (right, rhs)], validator, tmp_path / "相邻两组.zip")
    assert result.exit_code == 0, result.report
    with ZipFile(result.output) as archive:
        assert archive.testzip() is None
        rows = load_shots(ReviewResult(0, "", result.output, index_members(archive), []))
        assert len(rows) == 16 and rows[7].shot == "SB01-08" and rows[8].shot == "SB02-01"
        assert rows[8].plate_box and rows[10].plate_box and rows[8].plate_box != rows[10].plate_box
        assert rows[8].plate.filename == rows[10].plate.filename
        assert "D100=续说" in rows[8].production and second in rows[8].sd2
        assert first not in rows[8].sd2
        pending = archive.read("待制作分镜.txt").decode("utf-8-sig")
        assert "deferred-tail" in pending and f"- D101 | 值班员 | {remainder}" in pending
        assert "跨组交接记录" in archive.read("README.txt").decode("utf-8-sig")
        assert "SB03" not in " ".join(archive.namelist())
