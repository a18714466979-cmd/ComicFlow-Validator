"""Exercise media browsing with real image and video files and an unpacked Tk app."""

import gc
import hashlib
import shutil
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import current_thread, enumerate as active_threads
from tkinter import filedialog, messagebox, ttk
from unittest.mock import patch

from PIL import Image, ImageDraw


LABELS = {
    "zh": ("全部类别", "场景", "人物", "道具", "待分类", "全部媒体", "图片", "视频", "大"),
    "en": ("All categories", "Scenes", "Characters", "Props", "Unclassified",
           "All media", "Images", "Videos", "Large"),
}


def descendants(parent):
    for widget in parent.winfo_children():
        yield widget
        yield from descendants(widget)


def named(parent, name):
    return next(widget for widget in descendants(parent) if widget.winfo_name() == name)


def by_caption(parent, label):
    return next(widget for widget in descendants(parent)
                if isinstance(widget, ttk.Button) and widget.cget("text") == label)


def wait(root, condition, failed, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if errors := getattr(root, "callback_errors", ()):
            raise errors[0]
        if result := condition():
            return result
        time.sleep(.015)
    raise AssertionError(failed)


def choose(combo, label):
    assert label in combo["values"], (label, combo["values"])
    combo.current(combo["values"].index(label))
    combo.event_generate("<<ComboboxSelected>>")


def picture_at(canvas, item):
    name = canvas.itemcget(item, "image")
    return (int(canvas.tk.call("image", "width", name)),
            int(canvas.tk.call("image", "height", name)),
            name)


def find_picture(canvas, tag):
    names = canvas.find_withtag(tag)
    if names:
        return picture_at(canvas, names[0])


def picture_color(canvas, picture, x=None, y=None):
    width, height, name = picture
    value = canvas.tk.call(name, "get", width // 2 if x is None else x, height // 2 if y is None else y)
    return tuple(int(channel) for channel in value)


def visible_photo_sizes(canvas):
    return [picture_at(canvas, item)[:2] for item in canvas.find_withtag("media-item-photo")]


def first_square(canvas):
    squares = canvas.find_withtag("square")
    return canvas.coords(squares[0]) if squares else None


def click_card(root, canvas, photo=False):
    bounds = wait(root, lambda: canvas.bbox("media-item-photo") if photo else first_square(canvas),
                  "No visible preview card")
    x = int((bounds[0] + bounds[2]) / 2 - canvas.canvasx(0))
    y = int((bounds[1] + bounds[3]) / 2 - canvas.canvasy(0))
    assert 0 <= x < canvas.winfo_width() and 0 <= y < canvas.winfo_height(), bounds
    canvas.event_generate("<ButtonPress-1>", x=x, y=y)
    canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
    root.update()


def fixtures(folder):
    from src.ecommerce_video import resolve_ffmpeg
    from src.media_catalog import MediaItem

    scene = folder / "01_场景-宽图.png"
    portrait = folder / "02_人物-全身.png"
    prop = folder / "03_道具-信封.png"
    board = folder / "04_故事板-四格.png"
    video = folder / "05_片头黑场-竖屏.mp4"
    unknown = folder / "06_待分类.png"
    missing = folder / "不在磁盘上的图片.png"

    for path, size, fill in (
        (scene, (320, 180), "#4987b7"), (portrait, (180, 320), "#53a187"),
        (prop, (240, 240), "#ac7b41"), (board, (320, 180), "#48556a"),
        (unknown, (213, 151), "#905789"),
    ):
        picture = Image.new("RGB", size, fill)
        draw = ImageDraw.Draw(picture)
        draw.rectangle((0, 0, size[0]-1, max(2, size[1]//7)), fill="#cc3630")
        draw.rectangle((0, size[1] - size[1]//7, size[0]-1, size[1]-1), fill="#cfba55")
        if path == board:
            draw.line((size[0]//2, 0, size[0]//2, size[1]), fill="white", width=4)
            draw.line((0, size[1]//2, size[0], size[1]//2), fill="white", width=4)
        picture.save(path)

    ffmpeg_inputs = [
        value
        for color, duration in (("black", "0.45"), ("0xd67936", "1.0"), ("0x32a99a", "1.4"))
        for value in ("-f", "lavfi", "-i", f"color=c={color}:s=144x256:r=24:d={duration}")
    ]
    subprocess.run(
        [resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", *ffmpeg_inputs,
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[out]", "-map", "[out]",
         "-c:v", "mpeg4", "-threads", "2", "-pix_fmt", "yuv420p", "-y", str(video)],
        check=True, timeout=12, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return (
        MediaItem("scene", scene, "scene"),
        MediaItem("character", portrait, "character"),
        MediaItem("prop", prop, "prop"),
        MediaItem("board", board, "storyboard"),
        MediaItem("video", video, "motion_reference", media_type="video"),
        MediaItem("unknown", unknown),
        MediaItem("missing", missing),
    )


def validate_video(root, gallery, canvas, catalog):
    picture = wait(root, lambda: find_picture(canvas, "media-item-photo"), "Video poster did not load")
    w, h, _ = picture
    assert abs(w * 16 - h * 9) <= 24, (w, h)
    red, green, blue = picture_color(canvas, picture)
    assert red > 130 and red > green and green > blue, (red, green, blue)

    click_card(root, canvas)
    named(gallery, "media_preview").invoke()
    detail = wait(root, lambda: next(
        (widget for widget in descendants(gallery) if widget.winfo_name() == "media_detail"), None
    ), "Video detail window did not open")
    detail_canvas = named(detail, "media_detail_preview")
    scrub = named(detail, "media_scrub")
    wait(root, lambda: find_picture(detail_canvas, "media-detail-photo"), "Video detail did not decode")

    play = named(detail, "media_play")
    before = float(scrub.get())
    play.invoke()
    wait(root, lambda: float(scrub.get()) > before + 120, "Video did not advance during playback", timeout=4)
    play.invoke()

    scrub.set(1900)

    def teal_frame():
        frame = find_picture(detail_canvas, "media-detail-photo")
        if frame:
            red, green, blue = picture_color(detail_canvas, frame)
            return green > red + 50 and blue > red + 45
        return False

    wait(root, teal_frame, "Scrubbed video did not show the second scene")
    named(detail, "media_save_poster").invoke()
    wait(root, lambda: (catalog.poster_time("video") or 0) >= 1800,
         "Saved video cover time was not registered")
    detail.destroy()
    wait(root, lambda: (frame := find_picture(canvas, "media-item-photo")) and
         picture_color(canvas, frame)[1] > picture_color(canvas, frame)[0] + 50,
         "Updated cover did not appear on the video card")


def bulk_import(root, gallery, canvas, catalog, native, folder):
    batch = folder / "混合导入"
    batch.mkdir()
    scene, video = native[0].path, native[4].path
    imports = []
    for number in range(101):
        original = scene if number < 99 else video
        target = batch / f"素材-{number:03d}{original.suffix}"
        shutil.copyfile(original, target)
        imports.append(str(target))

    pulses = 0

    def pulse():
        nonlocal after_id, pulses
        pulses += 1
        after_id = root.after(10, pulse)

    after_id = root.after(1, pulse)
    try:
        with patch.object(filedialog, "askopenfilenames", return_value=tuple(imports)):
            named(gallery, "media_import").invoke()
        wait(root, lambda: len(catalog.items(native)) == 108, "Mixed file import did not retain every item")
        wait(root, lambda: canvas.yview()[1] < .8, "Large imports did not extend the scrollable viewport")
        assert pulses, "UI did not process its scheduled update during import"
        canvas.yview_moveto(.99)
        canvas.event_generate("<Configure>")
        wait(root, lambda: canvas.yview()[0] > .5 and canvas.find_withtag("media-item-photo"),
             "Could not scroll to and preview the final batch of imported images")
    finally:
        root.after_cancel(after_id)


def exercise(root, working, native, locale, percentage):
    from src.media_catalog import MediaCatalog
    from src.media_gallery import open_media_gallery

    path = working / f"catalog-{locale}.json"
    catalog = MediaCatalog(path)
    all_categories, scene, _, prop, unclassified, all_media, images, videos, large = LABELS[locale]
    source_digests = {item.path: hashlib.sha256(item.path.read_bytes()).digest()
                      for item in native if item.path.is_file()}
    picked = []
    root.ui_language = locale
    root.tk.call("tk", "scaling", 96 / 72 * percentage / 100)
    root.geometry("580x350+0+0")
    gallery = open_media_gallery(root, native, catalog=catalog, on_select=picked.append, allow_import=True)
    if gallery is None:
        gallery = named(root, "media_gallery")
    canvas = named(gallery, "media_cards")
    genre = named(gallery, "media_category")
    kind = named(gallery, "media_kind")
    size = named(gallery, "media_size")
    assignment = named(gallery, "media_assign_category")
    gallery.geometry("820x675+0+0")
    bounds = wait(root, lambda: first_square(canvas), "Square cards did not display")
    assert abs((bounds[2] - bounds[0]) - (bounds[3] - bounds[1])) <= 1, bounds
    original = bounds[2] - bounds[0]

    choose(kind, images)

    def varied_sizes():
        sizes = visible_photo_sizes(canvas)
        return sizes if any(w > h for w, h in sizes) and any(w < h for w, h in sizes) else None

    sizes = wait(root, varied_sizes, "Horizontal and vertical images were not both rendered")
    assert all(w <= original + 1 and h <= original + 1 for w, h in sizes), sizes
    choose(size, large)

    def larger_square():
        box = first_square(canvas)
        return box if box and box[2] - box[0] > original + 10 else None

    enlarged = wait(root, larger_square, "Resizing cards did not enlarge the preview")
    assert abs((enlarged[2]-enlarged[0]) - (enlarged[3]-enlarged[1])) <= 1

    choose(genre, scene)
    full_scene = wait(root, lambda: find_picture(canvas, "media-item-photo"), "Filtered scene did not render")
    width, height, _ = full_scene
    assert abs(width * 9 - height * 16) <= 24, full_scene
    top_r, top_g, _ = picture_color(canvas, full_scene, width // 2, 1)
    bottom_r, bottom_g, _ = picture_color(canvas, full_scene, width // 2, height - 2)
    assert top_r > top_g + 50 and bottom_g > top_g + 65 and bottom_r > bottom_g, (
        top_r, top_g, bottom_r, bottom_g,
    )

    choose(genre, unclassified)
    wait(root, lambda: find_picture(canvas, "media-item-photo"), "Unclassified image was not visible")
    click_card(root, canvas, photo=True)
    choose(assignment, prop)
    named(gallery, "media_apply_category").invoke()
    wait(root, lambda: any(item.key == "unknown" and item.category == "prop"
                            for item in MediaCatalog(path).items(native)),
         "Category assignment was not written to disk")

    choose(genre, all_categories)
    choose(kind, videos)
    validate_video(root, gallery, canvas, catalog)

    choose(kind, all_media)
    if locale == "en":
        bulk_import(root, gallery, canvas, catalog, native, working)
    gallery.destroy()

    relaunched_catalog = MediaCatalog(path)
    assert (relaunched_catalog.poster_time("video") or 0) >= 1800
    assert len(relaunched_catalog.items(native)) == (108 if locale == "en" else 7)
    gallery = open_media_gallery(root, native, catalog=relaunched_catalog, on_select=picked.append,
                                 selected=("character",), select_types=("image",))
    if gallery is None:
        gallery = named(root, "media_gallery")
    canvas = named(gallery, "media_cards")
    wait(root, lambda: len(visible_photo_sizes(canvas)) >= 2, "Reopened image picker drew no assets")
    named(gallery, "media_choose").invoke()
    assert len(picked) == 1 and tuple(item.key for item in picked[0]) == ("character",), picked
    for source, digest in source_digests.items():
        assert hashlib.sha256(source.read_bytes()).digest() == digest, source
    print(f"Verified real media cards, poster, playback, image picker and saved categories at "
          f"{percentage}% ({locale})", flush=True)


def exercise_integrations(root, working, native):
    from src.batch_dialog import BatchDialog
    from src.batch_workspace import BatchWorkspace
    from src.ecommerce_page import EcommercePage
    from src.image_production_dialog import ImageProductionDialog
    from src.production_dialog import open_production_dialog
    from src.production_media import project_media_catalog
    from src.production_project import ProductionProject
    from src.production_rules import ENGLISH

    root.ui_language = "zh"
    root.tk.call("tk", "scaling", 96 / 72)
    root.geometry("1100x820+0+0")
    scene, portrait, prop, _, video, *_ = native
    path = working / "已有单组.cfproject"
    project = ProductionProject("已有单组", "EP01", "SB01")
    approved = project.import_image(path, portrait.path, "protagonist_reference.png", action="直接复用",
                                    reason="离线合成样例", inspection="人工核对色彩和比例")
    project.save(path)
    original_project = path.read_bytes()
    project_media_catalog(path).import_paths((video.path,), category="character")
    group = open_production_dialog(root, {}, tk.StringVar(root), {}, {}, ENGLISH, lambda _rules: None,
                                   initial_project=path, destination="assets")
    wait(root, lambda: group.project is not None, "Existing group did not open")
    by_caption(group.window, "打开素材库").invoke()
    catalog_view = named(group.window, "media_gallery")
    canvas = named(catalog_view, "media_cards")
    wait(root, lambda: len(visible_photo_sizes(canvas)) == 2, "Group library omitted image or video")
    catalog_view.destroy()

    image_job = ImageProductionDialog(group, {})
    by_caption(image_job.window, "按图选择参考").invoke()
    chooser = named(image_job.window, "media_gallery")
    canvas = named(chooser, "media_cards")
    wait(root, lambda: len(visible_photo_sizes(canvas)) == 1, "Approved reference did not render")
    assert len(canvas.find_withtag("square")) == 1, "The model reference picker showed a linked video"
    click_card(root, canvas)
    named(chooser, "media_choose").invoke()
    assert [item.id for item in image_job.chosen_refs()] == [approved.id]
    assert path.read_bytes() == original_project, "Viewing a media catalog rewrote the old project"
    group.window.destroy()

    batch_path = working / "已有批次.cfbatch"
    batch_model = BatchWorkspace.create(batch_path, "已有批次", ENGLISH)
    batch_model.approve_asset("入口", "白天", "R1", scene.path, "已核对边缘", filename="scene_entry.png")
    batch = BatchDialog(root, ENGLISH, {}, {}, {}, lambda *_args: None)
    batch.open_path(batch_path)
    wait(root, lambda: not batch.busy and batch.workspace is not None, "Existing batch did not open")
    batch.select_stage("assets")
    by_caption(batch.window, "打开素材库").invoke()
    batch_view = named(batch.window, "media_gallery")
    canvas = named(batch_view, "media_cards")
    wait(root, lambda: visible_photo_sizes(canvas), "Approved shared scene did not render")
    assert "场景" in named(batch_view, "media_category")["values"]
    batch.window.destroy()

    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True)
    ecommerce = EcommercePage(frame, {}, {}, lambda: None)
    with patch.object(filedialog, "askopenfilename", return_value=str(video.path)):
        by_caption(frame, "导入参考视频").invoke()
    wait(root, lambda: getattr(ecommerce.poster, "image", None), "The source video cover did not render")
    assert ecommerce.poster.image.width() == ecommerce.poster.image.height()
    with patch.object(filedialog, "askopenfilenames", return_value=(str(prop.path),)):
        by_caption(frame, "导入产品照片").invoke()
    wait(root, lambda: len(ecommerce.project.product_refs) == 1, "E-commerce product photo did not import")
    by_caption(frame, "打开素材库").invoke()
    ecommerce_view = named(root, "media_gallery")
    canvas = named(ecommerce_view, "media_cards")
    wait(root, lambda: len(visible_photo_sizes(canvas)) == 2,
         "E-commerce library omitted the source video or product photo")
    assert "产品" in named(ecommerce_view, "media_category")["values"]
    print("Verified real single-group, generation picker, batch and ecommerce entry points", flush=True)


def finish_workers(preexisting, timeout=12):
    deadline = time.monotonic() + timeout
    while threads := [worker for worker in active_threads() if worker not in preexisting]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"Media smoke workers held files after shutdown: {[worker.name for worker in threads]}")
        threads[0].join(min(remaining, .2))


def verify():
    with TemporaryDirectory(prefix="studio-media-") as name:
        working = Path(name)
        native = fixtures(working)
        preexisting = {*active_threads(), current_thread()}
        root = tk.Tk()
        callback_errors = []
        root.callback_errors = callback_errors

        def record_callback_error(_kind, error, trace):
            callback_errors.append(error.with_traceback(trace))

        root.report_callback_exception = record_callback_error
        try:
            with patch.object(messagebox, "showerror", side_effect=AssertionError):
                exercise(root, working, native, "zh", 125)
                exercise(root, working, native, "en", 150)
                exercise_integrations(root, working, native)
                if callback_errors:
                    raise callback_errors[0]
        finally:
            try:
                root.destroy()
            finally:
                # Closing windows cancels queued work. Running FFmpeg and Pillow jobs
                # must leave the files before Windows can remove the fixture folder.
                finish_workers(preexisting)
                # Tk resources must be collected on this main test thread.
                del root.report_callback_exception
                del root
                gc.collect()
        if callback_errors:
            raise callback_errors[0]


if __name__ == "__main__":
    # The developer test file runs from the unpacked application's root.
    sys.path.insert(0, str(Path.cwd()))
    verify()
