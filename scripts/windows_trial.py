"""Build and reopen the Windows trial ZIP with entirely synthetic sample projects."""

import argparse
from io import BytesIO
from pathlib import Path
from shutil import copy2, copytree
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image, ImageDraw

from src.action_card_catalog import ACTION_PRESETS, ACTION_PREVIEW_DIRECTORY
from src.brand import APP_FOLDER, VERSION
from src.bundled_validators import ENGLISH_VALIDATOR_DIRECTORY, ENGLISH_VALIDATOR_FILES
from src.director_desk import DIRECTOR_BUNDLE, DIRECTOR_HOST
from src.image_api import EDIT, IMAGE_PROVIDERS, ImageReply, ImageSettings
from src.production_export import build_batch, project_registry
from src.production_images import local_patch, prepare_job, store_reply
from src.production_layout import apply_layout, bind_window, render_layout, windows_for_shots
from src.production_project import ProductionProject, Shot
from src.production_rules import CHINESE, ENGLISH
from src.repair_package import write_delivery_zip
from src.storyboard_guide import STORYBOARD_GUIDE_IMAGES, STORYBOARD_TOPICS
from src.workbench_tutorial import SECTIONS, TUTORIAL_IMAGES, TUTORIAL_LOCALES
from src.dialogue_blocking import DIALOGUE_CARDS, DIALOGUE_PREVIEW_DIRECTORY, dialogue_preview_path


ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = f"{APP_FOLDER}-Setup.bat"
LAUNCH_SCRIPT = f"{APP_FOLDER}.bat"
INSTALL_FILES = (SETUP_SCRIPT, LAUNCH_SCRIPT, "requirements-runtime.txt", "WINDOWS-TRYOUT.md", "CHANGELOG.md", "LICENSE")
COSTUME_REFERENCES = Path("assets/costume_references")
ECOMMERCE_VALIDATOR_DIRECTORY = Path("assets/workflow_validators/ecommerce")
CONTINUITY = "门保持关闭，右侧绿灯稳定，左侧柜体仍在原位"
ENGLISH_EXAMPLE_FRAMING = ("全景", "中景", "近景", "特写", "全景", "中景", "近景", "特写", "全景")


def draw_frame(path, beat, *, board, reverse=False, east=False, steady=False):
    lights = ((19, 91, 146), (80, 168, 118), (248, 173, 51))
    background = (248, 248, 248) if board else lights[0]
    wall = (226, 226, 226) if board else (128, 95, 66) if east else (76, 110, 133)
    door = (245, 245, 245) if board else (49, 132, 118)
    floor = (231, 231, 231) if board else (138, 80, 64)
    lamp = (115, 115, 115) if board else lights[1 if steady or beat >= 8 else 2]
    frame = Image.new("RGB", (640, 360), background)
    draw = ImageDraw.Draw(frame)
    left = (320 if reverse else 210) + (beat % 3) * 15
    right = left + 171
    draw.rectangle((25, 35, 615, 298), fill=wall, outline="#101010", width=4)
    draw.polygon(((0, 340), (154, 251), (486, 251), (639, 338), (639, 359), (0, 359)), fill=floor, outline="#202020")
    draw.rectangle((left, 56, right, 298), fill=door, outline="#171717", width=5)
    cabinet_x, light_x = (480, 122) if reverse else (86, 437)
    draw.rectangle((cabinet_x, 134, cabinet_x + 63, 278), fill=background, outline="#161616", width=4)
    draw.rectangle((light_x, 128, light_x + 68, 163), fill=lamp, outline="#111111", width=3)
    draw.line((left + 121, 176, left + 150, 176), fill="#171717", width=4)
    for offset in (0, 45, 90):
        draw.line((154 + offset, 252, 40 + offset * 3, 359), fill="#222222", width=2)
    draw.text((27, 38), f"{beat:02d}", fill="#ffffff" if not board else "#111111")
    frame.save(path)


def make_group(dest, scratch, number, rules):
    name = f"SB{number:02d}"
    path = dest / f"{name}.cfproject"
    chinese = rules == CHINESE
    scenes = ("值守室", "东走廊") if chinese and number == 2 else ("值守室",) if chinese else ("信号站",)
    project = ProductionProject("合成试用·值守站" if chinese else "Synthetic Example · Signal Station",
                                "EP01", name, rules=rules)
    script = ("值守室只有设备和建筑。门保持关闭，绿灯稳定。第二组在室内承接后切到东走廊。"
              if chinese else "信号站只有设备和建筑。门关闭，信号灯从琥珀色转换到绿灯。")
    source = project.import_source("合成试用剧本.md", "R1", script)
    project.notes = {
        "分组状态": "常规", "覆盖段落": f"合成试用剧本第 {number} 段", "内容类型": "环境", "对白规格": "无对白",
        "本组进入状态": "门关闭，右侧亮琥珀灯" if number == 1 and not chinese else CONTINUITY,
        "本组退出状态": CONTINUITY,
        "连续性锁定": CONTINUITY, "场景资产模式": "常规", "场景清单": "信号站",
        "场景身份判定": "信号站 | 本地合成素材 | 同一门框、同侧灯和柜体",
        "人物判定": "纯场景，无角色型实体", "人物资产表": "无", "武器轴线核对": "无",
        "镜头节奏核对": "从设备间全景进入门和灯的局部，再回到全景核对状态",
        "空间合理性核对": "门、柜体和灯在同一侧墙", "群像差异化核对": "无群像", "追击节奏核对": "无追击",
    }
    if chinese:
        project.notes.update({
            "组间镜头衔接核对": "首尾均以值守室关门和绿灯状态定位，第二组在值守室内承接后再切东走廊。",
            "景别衔接核对": "同向从门框全景切入设备中景，换地点先交代东走廊全景。",
            "主角判定": "本组只有建筑和固定设备，无人物或角色型实体",
        })
    project.prompt = {"场景/总体状态": "彩色空信号站，墙上的右侧灯点亮。", "公共限制": CONTINUITY}

    def import_frame(filename, beat, *, board=False, reverse=False, east=False, formal=False):
        original = scratch / filename
        draw_frame(original, beat, board=board, reverse=reverse, east=east, steady=chinese)
        return project.import_image(path, original, filename, action="直接复用", reference_only=not formal,
                                    reason="本地生成的试用素材", inspection="供试用版逐格核图",
                                    origin_label=f"合成样例 {name}/{filename}")

    if chinese and len(scenes) == 1:
        for angle in ("main", "reverse"):
            import_frame(f"scene_{scenes[0]}_{angle}_16x9.png", 8, formal=True, reverse=angle == "reverse")

    cameras = {}
    count = 10 if chinese and number == 1 else 9
    for ordinal in range(1, count + 1):
        beat = (number - 1) * (10 if chinese else 9) + ordinal
        scene = scenes[-1] if ordinal > 5 else scenes[0]
        camera = (ordinal - 1) % 3 + 1 if chinese else ordinal
        shot = Shot(source=source.id, anchor=f"信号站合成节拍 {beat:02d}", scene=scene,
                    plate_note=f"机位 {camera:02d} 对照门框、左柜与右灯",
                    fields={
                        "景别": ("全景" if ordinal in (1, 5, 9) else "中景")
                        if chinese else ENGLISH_EXAMPLE_FRAMING[ordinal - 1],
                        "机位/角度": "同侧平视",
                        "机位空间": f"{scene}同侧机位 {camera:02d}", "可见范围": "门框、左柜和右灯", "运镜": "固定",
                        "画面/事件": "记录合成设备在当前观察角度的状态", "人物站位": "无人物",
                        "动作起止": "观察门和信号灯，保持画面可见的设备位置",
                        "唯一角色数量锁定": "无", "本格新增叙事功能": "给出本镜设备位置的合成对照",
                        "情绪/表演": "空场等待", "环境威胁/视觉副线": "灯号反光",
                        "声音": "环境电流声", "声源位置": "画外", "连续性": CONTINUITY,
                        "视频模型约束": "门保持关闭", "场景/环境": "彩色室内设备间",
                    })
        project.shots.append(shot)
        east = scene == "东走廊"
        board = import_frame(f"板格_原图_{beat:02d}.png", beat, board=True, east=east)
        bind_window(project, path, shot.id, "board", board.id)
        key = (scene, camera)
        if key not in cameras:
            cameras[key] = import_frame(f"净板_原图_{beat:02d}.png", beat, east=east)
        bind_window(project, path, shot.id, "plate", cameras[key].id)
    sheets = scratch / name
    sheets.mkdir()
    apply_layout(project, path, render_layout(project, path, sheets, mixed=len(scenes) > 1),
                 "合成样例，编号、门和灯位置用于本地试用")
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


def make_examples(dest, scratch, rules, preview_name):
    dest.mkdir(parents=True)
    scratch.mkdir()
    groups = [make_group(dest, scratch, number, rules) for number in (1, 2)]
    add_repair_candidate(*groups[0])
    staging = scratch / "delivery"
    build_batch(groups, staging, scratch / "offline-preview.py", scratch / "preview.sqlite3")
    write_delivery_zip(staging, dest / preview_name)
    return groups


def build(output, revision):
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"VERSION.txt": VERSION + "\n", "REVISION.txt": revision + "\n"}
    with TemporaryDirectory(prefix="comic-sequence-studio-trial-") as temp:
        scratch = Path(temp)
        staging = scratch / "kit"
        folder = staging / APP_FOLDER
        folder.mkdir(parents=True)
        for filename in INSTALL_FILES:
            copy2(ROOT / filename, folder / filename)
        (folder / "src").mkdir()
        for path in sorted((ROOT / "src").glob("*.py")):
            copy2(path, folder / "src" / path.name)
        if not (ROOT / DIRECTOR_BUNDLE / "index.html").is_file():
            raise FileNotFoundError("Build the bundled 3D Director Desk first: python -m scripts.build_director_desk")
        copytree(ROOT / DIRECTOR_BUNDLE, folder / DIRECTOR_BUNDLE)
        copytree(ROOT / DIRECTOR_HOST, folder / DIRECTOR_HOST)
        copytree(ROOT / COSTUME_REFERENCES, folder / COSTUME_REFERENCES)
        copytree(ROOT / TUTORIAL_IMAGES, folder / TUTORIAL_IMAGES)
        guide_images = tuple(STORYBOARD_GUIDE_IMAGES / f"{topic}_{locale}.webp"
                             for topic in STORYBOARD_TOPICS for locale in TUTORIAL_LOCALES)
        (folder / STORYBOARD_GUIDE_IMAGES).mkdir(parents=True)
        for relative in guide_images:
            copy2(ROOT / relative, folder / relative)
        previews = tuple(ACTION_PREVIEW_DIRECTORY / f"{preset.id}.webp" for preset in ACTION_PRESETS)
        (folder / ACTION_PREVIEW_DIRECTORY).mkdir(parents=True)
        for relative in previews:
            copy2(ROOT / relative, folder / relative)
        dialogue_views = tuple(dialogue_preview_path(card.id, index).relative_to(ROOT)
                               for card in DIALOGUE_CARDS for index in range(3))
        (folder / DIALOGUE_PREVIEW_DIRECTORY).mkdir(parents=True)
        for relative in dialogue_views:
            copy2(ROOT / relative, folder / relative)
        copytree(ROOT / ECOMMERCE_VALIDATOR_DIRECTORY, folder / ECOMMERCE_VALIDATOR_DIRECTORY)
        (folder / ENGLISH_VALIDATOR_DIRECTORY).mkdir(parents=True)
        for filename in ENGLISH_VALIDATOR_FILES:
            relative = ENGLISH_VALIDATOR_DIRECTORY / filename
            copy2(ROOT / relative, folder / relative)
        for name, content in metadata.items():
            (folder / name).write_bytes(content.encode("utf-8"))
        make_examples(folder / "Examples", scratch / "en", ENGLISH, "预览_信号站_相邻两组.zip")
        make_examples(folder / "Examples" / "中文制作", scratch / "zh", CHINESE, "预览_相邻两组.zip")
        write_delivery_zip(staging, output)
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("The trial archive contains unreadable data.")
        samples = ("Examples/SB01.cfproject", "Examples/SB02.cfproject", "Examples/预览_信号站_相邻两组.zip",
                   "Examples/中文制作/SB01.cfproject", "Examples/中文制作/SB02.cfproject", "Examples/中文制作/预览_相邻两组.zip")
        references = tuple(path.relative_to(ROOT).as_posix() for path in (ROOT / COSTUME_REFERENCES).iterdir())
        validators = tuple((ENGLISH_VALIDATOR_DIRECTORY / name).as_posix() for name in ENGLISH_VALIDATOR_FILES)
        ecommerce_validator = (ECOMMERCE_VALIDATOR_DIRECTORY / "validate_storyboard_package.py").as_posix()
        tutorial = tuple((TUTORIAL_IMAGES / f"{section[0]}_{language}.png").as_posix()
                         for section in SECTIONS for language in TUTORIAL_LOCALES)
        director = tuple(path.relative_to(ROOT).as_posix() for directory in (DIRECTOR_BUNDLE, DIRECTOR_HOST)
                         for path in (ROOT / directory).rglob("*") if path.is_file())
        for name in (*INSTALL_FILES, *samples, *references, *validators, ecommerce_validator, *tutorial, *director):
            archive.getinfo(f"{APP_FOLDER}/{name}")
        for relative in guide_images:
            with Image.open(BytesIO(archive.read(f"{APP_FOLDER}/{relative.as_posix()}"))) as screenshot:
                screenshot.load()
                if screenshot.format != "WEBP" or screenshot.n_frames != 1 or screenshot.width < 600 or screenshot.height < 250:
                    raise ValueError(f"Expected a readable storyboard guide screenshot: {relative.name}")
        for relative in previews:
            with Image.open(BytesIO(archive.read(f"{APP_FOLDER}/{relative.as_posix()}"))) as strip:
                strip.load()
                if strip.format != "WEBP" or strip.n_frames != 1 or strip.width * 3 != strip.height * 12:
                    raise ValueError(f"Expected a three-panel 4:3 action preview strip: {relative.name}")
        for relative in dialogue_views:
            with Image.open(BytesIO(archive.read(f"{APP_FOLDER}/{relative.as_posix()}"))) as view:
                view.load()
                if view.format != "WEBP" or view.n_frames != 1 or view.width * 9 != view.height * 16:
                    raise ValueError(f"Expected a 16:9 dialogue view: {relative.name}")
        for name, content in metadata.items():
            if archive.read(f"{APP_FOLDER}/{name}") != content.encode("utf-8"):
                raise ValueError(f"The trial archive has mismatched metadata in {name}.")
        if archive.read(f"{APP_FOLDER}/CHANGELOG.md") != (ROOT / "CHANGELOG.md").read_bytes():
            raise ValueError("The trial archive does not match the repository changelog.")
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
