"""Synthetic single-group production with unrelated footage-free test material."""

import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image, ImageDraw

from src.asset_registry import AssetRegistry, sha256_file
from src.production_export import preview_project, project_registry, publish_project
from src.production_project import ProductionProject, Shot
from src.shot_review import load_shots
from src.storyboard_review import ReviewResult, index_members


def synthetic_sheet(path, size, slots, *, mono=False):
    sheet = Image.new("RGB", size)
    draw = ImageDraw.Draw(sheet)
    for number, x, y, units in slots:
        width, height = 160 * units, 90 * units
        rect = (x, y, x + width - 1, y + height - 1)
        draw.rectangle(rect, fill=(45, 45, 45) if mono else (25, 78, 128), outline=(201, 201, 201))
        draw.polygon(((x + 1, y + height - 1), (x + width // 4, y + height // 2),
                      (x + width * 3 // 4, y + height // 2), (x + width - 1, y + height - 1)),
                     fill=(102, 102, 102) if mono else (174, 65, 23))
        door_left = x + width // 5 + (number % 3) * width // 12
        draw.rectangle((door_left, y + height // 6, door_left + width // 3, y + height * 3 // 4),
                       fill=(192, 192, 192) if mono else (50, 158, 99))
        draw.ellipse((x + width * 4 // 5, y + height // 8, x + width * 9 // 10, y + height // 4),
                     fill=(220, 220, 220) if mono else (241, 175, 63))
        draw.text((x + 7, y + 6), f"{number:02}", fill="white")
    sheet.save(path)


@pytest.fixture
def production(tmp_path):
    project = ProductionProject("合成测试·信号灯", "EP01", "SB01")
    path = tmp_path / "本地项目.cfproject"
    script = project.import_source("合成剧本.md", "R1", "值班员（画外）：The signal is green.\n仓间的灯号依次切换。")
    project.import_dialogue(script, json.dumps([{"id": "D001", "speaker": "值班员", "text": "The signal is green."}]))
    project.notes.update({
        "分组状态": "常规", "覆盖段落": "合成剧本，空仓间的灯号切换",
        "内容类型": "环境", "对白规格": "1-2句短对白", "本组进入状态": "仓间信号灯开始闪烁",
        "本组退出状态": "仓间信号灯稳定", "连续性锁定": "机位变化时同一扇门保留同侧灯和柜体",
        "场景资产模式": "常规", "场景清单": "试验间",
        "场景身份判定": "试验间 | 合成底图 | 一扇门和一个信号灯，相同空间",
        "人物判定": "纯场景，无角色型实体", "人物资产表": "无", "武器轴线核对": "无",
        "镜头节奏核对": "从入口关系切到门侧局部，再回到室内关系统一灯号",
        "空间合理性核对": "门与灯位于同一堵墙，按机位观察相对位置",
        "群像差异化核对": "无群像", "追击节奏核对": "无追击",
    })
    project.prompt = {"场景/总体状态": "空仓间的信号灯正在切换", "公共限制": "门和信号灯位置保持一致，保留画外声音。"}
    board = tmp_path / "storyboard_8panel_bw_16x9.png"
    layout = ((0, 0, 3), (3, 0, 2), (3, 2, 1), (4, 2, 1), (0, 3, 2), (2, 3, 2), (4, 3, 1), (4, 4, 1))
    synthetic_sheet(board, (800, 450), [(i, x * 160, y * 90, u) for i, (x, y, u) in enumerate(layout, 1)], mono=True)
    images = []
    for filename in ("scene_试验间_details_01_16x9.png", "scene_试验间_details_02_16x9.png"):
        item = tmp_path / filename
        first = len(images) * 4 + 1
        synthetic_sheet(item, (320, 180), [(first + i, i % 2 * 160, i // 2 * 90, 1) for i in range(4)])
        images.append(project.import_image(path, item, filename, action="直接复用",
                                           reason="直接复制批准的合成彩色局部，保持相同指纹",
                                           inspection="合成图画面及四个局部标记可读，核对门和信号灯"))
    project.import_image(path, board, board.name, action="新生成", reason="合成灰度分格样例",
                         inspection="合成图八格编号与两个场景页对应，观察灰度图形")
    project.import_image(path, board, "approved_reference.png", action="直接复用",
                         reason="批准来源对照", inspection="", reference_only=True)
    for position in range(8):
        project.shots.append(Shot(
            source=script.id, anchor=f"合成剧本·灯号节拍 {position + 1}", plate=images[position // 4].id,
            scene="试验间", plate_note=f"门和灯从机位 {position + 1} 观察",
            dialogue=[("D001", 0, 20)] if position == 3 else [],
            fields={
                "景别": "中景" if position % 2 else "广角", "机位/角度": "门侧平视",
                "机位空间": f"仓内机位 {position + 1}", "可见范围": "门框和信号灯", "运镜": "固定",
                "画面/事件": "观察空仓间的门边信号灯", "人物站位": "无", "动作起止": "画面留在门框直到灯稳住",
                "唯一角色数量锁定": "无", "本格新增叙事功能": "更新信号灯的状态",
                "情绪/表演": "空场，积蓄等待感", "环境威胁/视觉副线": "信号灯光落在地面",
                "声音": "低频电流声", "声源位置": "右侧门边", "连续性": "一扇门和一盏灯维持相对位置",
                "视频模型约束": "门框结构与灯相对位置一致", "场景/环境": "空仓间，门框和灯固定",
            },
        ))
    project.save(path)
    return path


@pytest.fixture
def validator(tmp_path):
    configured = os.environ.get("COMICFLOW_M1_TEST_VALIDATOR")
    if configured:
        return Path(configured)
    checker = tmp_path / "validate_storyboard_package.py"
    checker.write_text('print("RESULT: 0 error(s), 0 warning(s)")\n', encoding="utf-8")
    checker.with_name("plan_english_dialogue.py").write_text(
        'import json, sys\n'
        'items = json.load(open(sys.argv[1], encoding="utf-8"))\n'
        'for item in items:\n'
        '    item["text"] = item["text"][item["start"]:item["end"]]\n'
        '    item["cue"] = "续说" if item["start"] else "首说"\n'
        'print(json.dumps([{"words": 4, "fragments": items}]))\n', encoding="utf-8",
    )
    return checker


def test_single_group_reopen_render_and_verify_zip(production, validator, tmp_path):
    project = ProductionProject.open(production)
    first = project.shots[0].id
    rehearsal = tmp_path / "rehearsal"
    rehearsal.mkdir()
    draft = preview_project(project, production, validator, rehearsal)
    with ZipFile(draft) as package:
        members = index_members(package)
        rows = load_shots(ReviewResult(0, "", draft, members, []))
        assert len(rows) == 8
        assert package.testzip() is None
        details = package.read("SB01/SB01_shot_details.txt")
        prompt = package.read("SB01/SD2_prompt.txt")
        assert details.startswith(b"\xef\xbb\xbf") and prompt.startswith(b"\xef\xbb\xbf")
        assert first in details.decode("utf-8-sig")
        assert '值班员：“The signal is green.”' in details.decode("utf-8-sig")
        assert '值班员：“The signal is green.”' in prompt.decode("utf-8-sig")
        assert "资产复用核对" not in prompt.decode("utf-8-sig")
        assert "SB01/approved_reference.png" not in members
    with pytest.raises(ValueError, match="逐格核对"):
        publish_project(project, production, validator, tmp_path / "blocked.zip")
    project.structure_review = project.fingerprint()
    project.save(production)
    project = ProductionProject.open(production)
    result = publish_project(project, production, validator, tmp_path / "第一次.zip")
    assert result.exit_code == 0, result.report
    assert result.sha256 == sha256_file(draft) == sha256_file(result.output)
    assert len(AssetRegistry(project_registry(production)).records()) == 4
    completed = subprocess.run(
        [sys.executable, "-m", "src.delivery_checker", str(result.output), "--storyboard-validator", str(validator),
         "--asset-registry", str(project_registry(production))],
        capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    project.move_shot(0, 1)
    assert project.shots[1].id == first
    assert "storyboard_8panel_bw_16x9.png" in project.impacts()
    assert "scene_试验间_details_01_16x9.png" in project.impacts()
    project.shots[1].plate = ""
    missing = tmp_path / "missing"
    missing.mkdir()
    with pytest.raises(ValueError, match="SB01-02 缺少正式净板"):
        preview_project(project, production, validator, missing)

    reopened = ProductionProject.open(production)
    inserted = Shot(source=reopened.sources[0].id, anchor="合成剧本·插入节拍")
    reopened.shots.insert(1, inserted)
    assert reopened.shots[0].id == first and reopened.shots[1].id == inserted.id
    assert set(reopened.impacts()) >= {"SB01_shot_details.txt", "SD2_prompt.txt", "README.txt"}
    with pytest.raises(ValueError, match="格数与镜头清单一致"):
        preview_project(reopened, production, validator, tmp_path)
    reopened.shots.pop(1)
    reopened.shots[0].fields["机位空间"] = "仓内机位 1，摄像机贴墙"
    reopened.structure_review = reopened.fingerprint()
    compared = publish_project(reopened, production, validator, tmp_path / "第二次.zip", result.output)
    assert compared.exit_code == 0, compared.report
    assert compared.changed == ("SB01/SB01_shot_details.txt", "SB01/SD2_prompt.txt")
    assert compared.added == compared.removed == ()


def test_source_revision_and_missing_spoken_line(production, validator, tmp_path):
    project = ProductionProject.open(production)
    source = project.sources[0]
    with pytest.raises(ValueError, match="新版本"):
        project.import_source(source.name, source.version, source.text + "改稿")
    with pytest.raises(ValueError, match="先移除镜头"):
        project.import_dialogue(source, "[]", replace_source_lines=True)
    revised = project.import_source(source.name, "R2", source.text)
    assert revised.id != source.id and project.shots[0].source == source.id
    project.shots[3].dialogue.clear()
    with pytest.raises(ValueError, match="有遗漏：D001"):
        preview_project(project, production, validator, tmp_path)


def test_approved_local_image_repair_enters_strict_zip(production, validator, tmp_path):
    from io import BytesIO

    from src.image_api import EDIT, IMAGE_PROVIDERS, ImageReply, ImageSettings
    from src.production_images import approve_candidate, local_patch, prepare_job, store_reply

    project = ProductionProject.open(production)
    shot = project.shots[0]
    plate = next(image for image in project.images if image.id == shot.plate)
    base = project.checked_image(production, plate)
    expected_old_digest = sha256_file(base)
    with Image.open(base) as image:
        changed = image.copy()
    edit_box = (26, 20, 40, 32)
    ImageDraw.Draw(changed).rectangle((26, 20, 39, 31), fill=(103, 87, 73))
    output = BytesIO()
    changed.save(output, format="PNG")
    provider = "火山方舟 Seedream"
    preset = IMAGE_PROVIDERS[provider]
    config = ImageSettings(provider, preset.base, preset.model, "test-key")
    job, _ = prepare_job(project, production, config, EDIT, "净板", shot.id, "修改测试门板颜色", [plate.id], edit_box)
    project.image_jobs.append(job)
    store_reply(production, job, ImageReply((output.getvalue(),), request_id="synthetic-image-work"))
    local_patch(project, production, job, job["outputs"][0])
    revised = approve_candidate(project, production, job, 0, plate.filename, "R2", "仅修补批准画面的门板局部",
                                "两版的门和信号灯位置已按合成样例核对", replace_original=True)
    assert sha256_file(base) == expected_old_digest
    assert revised.id == project.shots[1].plate and revised.originals == (plate.id,)
    project.structure_review = project.fingerprint()
    result = publish_project(project, production, validator, tmp_path / "已批准返修.zip")
    assert result.exit_code == 0, result.report
    with ZipFile(result.output) as archive:
        assert archive.testzip() is None
        picture = archive.read("SB01/" + revised.filename)
        assert picture == project.checked_image(production, revised).read_bytes()
        production_txt = archive.read("SB01/SB01_shot_details.txt").decode("utf-8-sig")
        sd2 = archive.read("SB01/SD2_prompt.txt").decode("utf-8-sig")
        assert "图像生成和返修来源：" in production_txt and "synthetic-image-work" in production_txt
        assert "synthetic-image-work" not in sd2
        assert not any("原图_" in name for name in archive.namelist())
