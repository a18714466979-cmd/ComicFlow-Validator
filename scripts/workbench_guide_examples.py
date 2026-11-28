"""Create portable, entirely local examples for the workbench lessons."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont

from src.batch_workspace import BatchWorkspace
from src.ecommerce_delivery import board_layout, label_board_sheet
from src.ecommerce_project import EcommerceShot, render_shots
from src.ecommerce_video import VideoShot, analyze_video, resolve_ffmpeg
from src.production_rules import ENGLISH


EPISODES = (
    (
        "场景：信号站值守室",
        "桌面的灯暗了。",
        "窗框外，晨光落到地上。",
        "值班员将记录本放在左侧柜子上。",
        "灯罩里的灯丝慢慢变亮。",
        "值班员转向仪表板。",
        "她看见电流表指针回到零。",
        "门框右侧的灯转为绿色。",
        "值班员听见靠窗的风铃轻响。",
        "她低头核对旧记录本。",
        "末行的墨迹已经干了。",
        "她在记录下方画一条短线。",
        "门外的走廊空无一人。",
    ),
    (
        "场景：信号站东走廊",
        "巡检员从东侧楼梯口走来。",
        "长窗投下的阴影落在地砖上。",
        "他停在第一扇关闭的窗前。",
        "窗外的汽笛轻响一声。",
        "巡检员抬眼看向走廊尽头。",
        "门口的状态灯闪了一下。",
        "他把手电从桌面拿起。",
        "手电的光扫过地上褪色的箭头。",
        "箭头指向走廊右侧的机房。",
        "巡检员沿箭头走到机房门前。",
        "门框上的铜牌反射手电的光。",
        "他在检查表上记下铜牌编号。",
    ),
)


def build_batch_example(folder):
    folder.mkdir(parents=True)
    script_paths = []
    for number, lines in enumerate(EPISODES, 1):
        path = folder / f"EP{number:02}.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        script_paths.append(path)
    workspace = BatchWorkspace.create(folder / "Signal-Station.cfbatch", "Signal Station", ENGLISH)
    for episode in workspace.add_scripts(script_paths):
        if [project.stem for project in workspace.group_paths(episode.id)] != ["SB01", "SB02"]:
            raise ValueError(f"Unexpected tutorial group plan for {episode.id}")
        workspace.approve_plan(episode.id)
    scene = Image.new("RGB", (512, 288), "#dce0db")
    draw = ImageDraw.Draw(scene)
    draw.polygon(((0, 288), (146, 151), (338, 151), (512, 288)), fill="#9faa9b")
    draw.rectangle((174, 51, 308, 221), fill="#476c61", outline="#233c35", width=5)
    draw.rectangle((279, 136, 292, 144), fill="#dcc78d")
    draw.rectangle((225, 93, 261, 110), fill="#d8cfad")
    draw.ellipse((335, 89, 354, 108), fill="#64a77d", outline="#476c61", width=3)
    reference = folder / "Shared-Station-Door.png"
    scene.save(reference)
    asset_key = ("场景：信号站东走廊", "机房门关闭", "R1")
    workspace.approve_asset(*asset_key, reference, "合成练习图已核对关闭的机房门和右侧状态灯。")
    workspace.require_asset("EP02", "SB02", *asset_key)
    return workspace.path


WIDTH, HEIGHT = 144, 256


def draw_bottle(draw, center, top, scale, *, color, cap, label=""):
    def box(left, y, right, bottom):
        return tuple(round(value) for value in (
            center + left * scale, top + y * scale, center + right * scale, top + bottom * scale,
        ))

    draw.rounded_rectangle(box(-21, 18, 21, 119), radius=round(10 * scale), fill=color)
    draw.rounded_rectangle(box(-11, 0, 11, 25), radius=round(4 * scale), fill=cap)
    draw.rounded_rectangle(box(-16, 57, 16, 86), radius=round(3 * scale), fill="#f4e6bc")
    if label:
        draw.text((center, top + 71 * scale), label, font=ImageFont.load_default(size=round(8 * scale)),
                  fill=cap, anchor="mm")
    else:
        draw.line(box(-8, 68, 8, 68), fill=cap, width=round(2 * scale))
        draw.line(box(-5, 75, 5, 75), fill=cap, width=round(scale))


def reference_frames():
    """Three visibly distinct views of a generic bottle for hard-cut analysis."""
    backgrounds = ("#e8b778", "#263e55", "#cde6d7")
    surfaces = ("#d49a57", "#142333", "#95bfad")
    products = ((72, 61, 1.14), (91, 26, 1.8), (63, 91, .78))
    for background, surface, (x, y, scale) in zip(backgrounds, surfaces, products):
        image = Image.new("RGB", (WIDTH, HEIGHT), background)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 192, WIDTH, HEIGHT), fill=surface)
        draw.ellipse((x - 39, 182, x + 39, 208), fill=surface)
        draw_bottle(draw, x, y, scale, color="#bc5b3b", cap="#913c33")
        yield image


def ecommerce_shots(timings):
    scene = "产品展示台"
    descriptions = (
        ("中景", "平视正面", "展示水瓶和台面的相对位置。"),
        ("近景", "平视略偏右", "看清正面 LUMA 标签与带旋盖的瓶口。"),
        ("全景", "平视略偏左", "回到全瓶身与台面的画面。"),
    )
    return [
        EcommerceShot(f"{index:02}", timing.start_ms, timing.end_ms, scene, size, angle,
                      camera="固定", action=action, positions="水瓶直立在展示台中部",
                      dialogue="无", sound="无", continuity="瓶盖保持关闭，标签朝镜头",
                      contains_product=True, visual_text="LUMA")
        for index, (timing, (size, angle, action)) in enumerate(zip(timings, descriptions), 1)
    ]


def ecommerce_set(size):
    width, height = size
    image = Image.new("RGB", size, "#ead3be")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((width * .22, height * .13, width * .78, height * .82),
                           radius=width // 11, fill="#f4ebdd")
    draw.rectangle((0, height * .69, width, height), fill="#997d72")
    return image


def save_ecommerce_materials(folder, timings):
    shots = ecommerce_shots(timings)
    (folder / "Shots.json").write_text(render_shots(shots), encoding="utf-8", newline="\n")
    ecommerce_set((640, 360)).save(folder / "Scene.png")

    sheet_size = (1080, 1920)
    board = Image.new("RGB", sheet_size, "#344046")
    columns, rows = board_layout(len(shots))
    panel_size = (sheet_size[0] // columns, sheet_size[1] // rows)
    positions = ((270, 280, 4), (310, 125, 6), (250, 420, 3))
    for index, (center, top, scale) in enumerate(positions):
        panel = ecommerce_set(panel_size)
        draw = ImageDraw.Draw(panel)
        ground = top + 119 * scale
        draw.ellipse((center - 27 * scale, ground - 4 * scale,
                      center + 27 * scale, ground + 4 * scale), fill="#866c61")
        draw_bottle(draw, center, top, scale, color="#378d79", cap="#275d54", label="LUMA")
        row, column = divmod(index, columns)
        board.paste(panel, (column * panel_size[0], row * panel_size[1]))
    with TemporaryDirectory(prefix="practice-board-") as tmp:
        draft = Path(tmp) / "Unnumbered.png"
        board.save(draft)
        label_board_sheet(draft, folder / "SB01-Board.png", [shot.id for shot in shots])


def build_ecommerce_example(folder):
    folder.mkdir(parents=True)
    video, product = folder / "Reference.mp4", folder / "Product.png"
    image = Image.new("RGB", (256, 256), "#edf4ef")
    draw = ImageDraw.Draw(image)
    draw.ellipse((57, 199, 198, 224), fill="#c9ddd6")
    draw_bottle(draw, 128, 37, 1.44, color="#378d79", cap="#275d54", label="LUMA")
    image.save(product)
    fps = 12
    frames = b"".join(frame.tobytes() * fps for frame in reference_frames())
    ffmpeg = resolve_ffmpeg()
    process = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "rawvideo",
        "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(fps), "-i", "pipe:0",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-threads", "2", "-movflags", "+faststart", str(video),
    ], input=frames, capture_output=True, timeout=30, check=False)
    if process.returncode:
        raise ValueError(f"Could not encode the tutorial MP4: {process.stderr.decode('utf-8', errors='replace')}")
    expected = tuple(VideoShot(start, start + 1000) for start in (0, 1000, 2000))
    analyzed = analyze_video(video, ffmpeg=ffmpeg)
    if (not analyzed.info.is_vertical or analyzed.info.has_audio
            or analyzed.info.duration_ms != 3000 or analyzed.shots != expected):
        raise ValueError(f"Unexpected tutorial cut analysis: {analyzed}")
    save_ecommerce_materials(folder, analyzed.shots)
    return video, product


def build_workbench_examples(examples):
    folder = Path(examples) / "Workbench"
    build_ecommerce_example(folder / "Ecommerce")
    build_batch_example(folder / "Batch")
