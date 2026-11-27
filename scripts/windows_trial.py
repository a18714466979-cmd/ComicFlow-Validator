"""Build and reopen the Windows trial ZIP with entirely synthetic sample projects."""

import argparse
from io import BytesIO
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image, ImageDraw

from src.image_api import EDIT, IMAGE_PROVIDERS, ImageReply, ImageSettings
from src.production_export import build_batch, project_registry
from src.production_images import local_patch, prepare_job, store_reply
from src.production_layout import apply_layout, bind_window, render_layout, windows_for_shots
from src.production_project import ProductionProject, Shot
from src.repair_package import write_delivery_zip


ROOT = Path(__file__).resolve().parents[1]
INSTALL_FILES = ("ComicFlow-Setup.bat", "ComicFlow-Windows.bat", "requirements-runtime.txt", "WINDOWS-TRYOUT.md", "LICENSE")
CONTINUITY = "门保持关闭，右侧绿灯稳定，左侧柜体仍在原位"


def draw_frame(path, beat, *, board):
    lights = ((19, 91, 146), (80, 168, 118), (248, 173, 51))
    background = (248, 248, 248) if board else lights[0]
    wall = (226, 226, 226) if board else (76, 110, 133)
    door = (245, 245, 245) if board else (49, 132, 118)
    floor = (231, 231, 231) if board else (138, 80, 64)
    lamp = (115, 115, 115) if board else lights[1 if beat >= 8 else 2]
    frame = Image.new("RGB", (640, 360), background)
    draw = ImageDraw.Draw(frame)
    left = 210 + (beat % 3) * 15
    right = left + 171
    draw.rectangle((25, 35, 615, 298), fill=wall, outline="#101010", width=4)
    draw.polygon(((0, 340), (154, 251), (486, 251), (639, 338), (639, 359), (0, 359)), fill=floor, outline="#202020")
    draw.rectangle((left, 56, right, 298), fill=door, outline="#171717", width=5)
    draw.rectangle((86, 134, 149, 278), fill=background, outline="#161616", width=4)
    draw.rectangle((437, 128, 505, 163), fill=lamp, outline="#111111", width=3)
    draw.line((left + 121, 176, left + 150, 176), fill="#171717", width=4)
    for offset in (0, 45, 90):
        draw.line((154 + offset, 252, 40 + offset * 3, 359), fill="#222222", width=2)
    draw.text((27, 38), f"{beat:02d}", fill="#ffffff" if not board else "#111111")
    frame.save(path)


def make_group(dest, scratch, number):
    name = f"SB{number:02d}"
    path = dest / f"{name}.cfproject"
    project = ProductionProject("ComicFlow 合成试用·信号站", "EP01", name)
    source = project.import_source("合成试用剧本.md", "R1", "信号站只有设备和建筑。门关闭，信号灯从琥珀色转换到绿灯。")
    project.notes = {
        "分组状态": "常规", "覆盖段落": f"合成试用剧本第 {number} 段", "内容类型": "环境", "对白规格": "无对白",
        "本组进入状态": "门关闭，右侧亮琥珀灯" if number == 1 else CONTINUITY, "本组退出状态": CONTINUITY,
        "连续性锁定": CONTINUITY, "场景资产模式": "常规", "场景清单": "信号站",
        "场景身份判定": "信号站 | 本地合成素材 | 同一门框、同侧灯和柜体",
        "人物判定": "纯场景，无角色型实体", "人物资产表": "无", "武器轴线核对": "无",
        "镜头节奏核对": "从设备间全景进入门和灯的局部，再回到全景核对状态",
        "空间合理性核对": "门、柜体和灯在同一侧墙", "群像差异化核对": "无群像", "追击节奏核对": "无追击",
    }
    project.prompt = {"场景/总体状态": "彩色空信号站，墙上的右侧灯点亮。", "公共限制": CONTINUITY}
    for ordinal in range(1, 10):
        beat = (number - 1) * 9 + ordinal
        shot = Shot(source=source.id, anchor=f"信号站合成节拍 {beat:02d}", scene="信号站",
                    plate_note=f"机位 {ordinal:02d} 对照门框、左柜与右灯",
                    fields={
                        "景别": "全景" if ordinal in (1, 5, 9) else "中景", "机位/角度": "同侧平视",
                        "机位空间": f"房间同侧机位 {ordinal:02d}", "可见范围": "门框、左柜和右灯", "运镜": "固定",
                        "画面/事件": "记录合成设备在当前观察角度的状态", "人物站位": "无人物",
                        "动作起止": "观察门和信号灯，保持画面可见的设备位置",
                        "唯一角色数量锁定": "无", "本格新增叙事功能": "给出本镜设备位置的合成对照",
                        "情绪/表演": "空场等待", "环境威胁/视觉副线": "灯号反光",
                        "声音": "环境电流声", "声源位置": "画外", "连续性": CONTINUITY,
                        "视频模型约束": "门保持关闭", "场景/环境": "彩色室内设备间",
                    })
        project.shots.append(shot)
        for kind in ("board", "plate"):
            filename = f"{'板格' if kind == 'board' else '净板'}_原图_{beat:02d}.png"
            original = scratch / filename
            draw_frame(original, beat, board=kind == "board")
            asset = project.import_image(path, original, filename, action="直接复用", reference_only=True,
                                         reason="本地生成的试用素材", inspection="供试用版逐格核图",
                                         origin_label=f"ComicFlow 合成样例 {name}/{filename}")
            bind_window(project, path, shot.id, kind, asset.id)
    sheets = scratch / name
    sheets.mkdir()
    apply_layout(project, path, render_layout(project, path, sheets), "合成样例，编号、门和灯位置用于本地试用")
    return project, path


def add_repair_candidate(project, path):
    shot = project.shots[0]
    plate, (x, y, right, bottom) = windows_for_shots(project)[shot.id]["plate"]
    # Keep the edit away from the slot label and use a small bounded rectangle.
    box = (x + (right-x)*69//100, y + (bottom-y)*36//100,
           x + (right-x)*75//100, y + (bottom-y)*42//100)
    provider = "火山方舟 Seedream"
    preset = IMAGE_PROVIDERS[provider]
    config = ImageSettings(provider, preset.base, preset.model, "offline-example")
    job, _ = prepare_job(project, path, config, EDIT, "净板", shot.id, "合成试用，局部修改灯罩", [plate.id], box)
    with Image.open(project.checked_image(path, plate)) as base:
        result = base.copy()
    ImageDraw.Draw(result).rectangle((box[0], box[1], box[2]-1, box[3]-1), fill="#f3cd5a")
    data = BytesIO()
    result.save(data, format="PNG")
    job["base"] = preset.base
    store_reply(path, job, ImageReply((data.getvalue(),), request_id="本地合成，未调用模型"))
    local_patch(project, path, job, job["outputs"][0])
    project.image_jobs.append(job)
    project.save(path)


def make_examples(dest, scratch):
    dest.mkdir()
    groups = [make_group(dest, scratch, number) for number in (1, 2)]
    add_repair_candidate(*groups[0])
    staging = scratch / "delivery"
    build_batch(groups, staging, scratch / "offline-preview.py", scratch / "preview.sqlite3")
    write_delivery_zip(staging, dest / "预览_信号站_相邻两组.zip")
    return groups


def build(output, revision):
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="comicflow-trial-") as temp:
        scratch = Path(temp)
        staging = scratch / "kit"
        folder = staging / "ComicFlow-Windows"
        folder.mkdir(parents=True)
        for filename in INSTALL_FILES:
            copy2(ROOT / filename, folder / filename)
        (folder / "src").mkdir()
        for path in sorted((ROOT / "src").glob("*.py")):
            copy2(path, folder / "src" / path.name)
        (folder / "REVISION.txt").write_text(revision + "\n", encoding="utf-8")
        make_examples(folder / "Examples", scratch)
        write_delivery_zip(staging, output)
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("The trial archive contains unreadable data.")
        for name in (*INSTALL_FILES, "Examples/SB01.cfproject", "Examples/SB02.cfproject", "Examples/预览_信号站_相邻两组.zip"):
            archive.getinfo(f"ComicFlow-Windows/{name}")
        if any(".sqlite3" in name for name in archive.namelist()):
            raise ValueError("The portable archive must rebuild machine-local asset paths.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--revision", default="local")
    args = parser.parse_args()
    build(args.output.resolve(), args.revision)


if __name__ == "__main__":
    main()
