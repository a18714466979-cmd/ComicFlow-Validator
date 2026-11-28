"""Open the packaged action-card browser and confirm it supplies the previews it displays."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

from PIL import Image


def descend(widget):
    for child in widget.winfo_children():
        yield child
        yield from descend(child)


def named(widget, name):
    return next(child for child in descend(widget) if child.winfo_name() == name)


def wait(root, ready, message):
    deadline = monotonic() + 6
    while monotonic() < deadline:
        root.update()
        if ready():
            return
        sleep(.015)
    raise AssertionError(message)


def photo(widget):
    value = widget.cget("image")
    if isinstance(value, (tuple, list)):
        value = value[0] if value else ""
    return str(value)


def image_present(widget):
    image = photo(widget)
    return image and int(widget.tk.call("image", "width", image)) > 10


def toplevel(root):
    return next(widget for widget in descend(root) if widget.winfo_name() == "action_presets")


def validate_assets():
    from src.action_card_catalog import ACTION_PRESETS, action_preview_path

    keys = {preset.id for preset in ACTION_PRESETS}
    assert len(keys) == len(ACTION_PRESETS) == 53
    assert len({preset.category for preset in ACTION_PRESETS}) == 9
    checksums = set()
    for key in keys:
        path = action_preview_path(key)
        checksums.add(sha256(path.read_bytes()).digest())
        with Image.open(path) as image:
            image.load()
            assert image.format == "WEBP" and image.n_frames == 1, key
            width, height = image.size
            assert width == 4 * height, (key, image.size)
            panel_width = width // 3
            stages = {sha256(image.crop((i * panel_width, 0, (i + 1) * panel_width, height)).tobytes()).digest()
                      for i in range(3)}
            assert len(stages) == 3, key
    assert len(checksums) == len(keys), "Duplicate complete preview"
    print("Decoded 53 packaged action previews and checked the 159 distinct stages", flush=True)


def exercise(root, temp):
    from src.action_card_catalog import get_preset
    from src.action_preset_gallery import open_action_presets
    from src.action_sequence import ActionCard, cards_to_records
    from src.action_sequence_dialog import ActionSequenceDialog
    from src.production_project import ProductionProject
    from src.workbench_style import configure_workbench

    configure_workbench(root)
    root.geometry("1100x760+0+0")
    key = "performance-03"
    sample = get_preset(key)
    for language, percent in (("zh", 125), ("en", 150)):
        english = language == "en"
        root.ui_language = language
        root.tk.call("tk", "scaling", 96 / 72 * percent / 100)
        selected = []
        gallery = open_action_presets(root, english=english, on_add=selected.append)
        minimum_width, minimum_height = gallery.minsize()
        gallery.geometry(f"{minimum_width}x{minimum_height}+0+0")
        category = named(gallery, "preset_category")
        category.current(tuple(category.cget("values")).index(sample.category[english]))
        category.event_generate("<<ComboboxSelected>>")
        root.update()
        cover = named(gallery, "cover_" + key)
        wait(root, lambda: image_present(cover), "Card cover never loaded")
        cover.invoke()
        previews = tuple(named(gallery, "frame_" + part) for part in ("start", "beat", "end"))
        wait(root, lambda: all(image_present(widget) for widget in previews), "Three stages did not load")
        assert named(gallery, "preset_title").cget("text") == sample.title[english]
        root_left, root_top = gallery.winfo_rootx(), gallery.winfo_rooty()
        for widget in previews + (named(gallery, "add_preset"),):
            assert widget.winfo_ismapped()
            x, y = widget.winfo_rootx() - root_left, widget.winfo_rooty() - root_top
            assert 0 <= x and x + widget.winfo_width() <= gallery.winfo_width()
            assert 0 <= y and y + widget.winfo_height() <= gallery.winfo_height()
        named(gallery, "add_preset").invoke()
        assert selected == [key] and not gallery.winfo_exists()
        print(f"Verified {language} action gallery at {percent}% with a full-size cover and three frames", flush=True)

    root.ui_language = "zh"
    path = temp / "动作预览.cfproject"
    project = ProductionProject("本地预演", "EP01", "SB01")
    old_card = ActionCard(title=sample.title[0], movement=sample.movement[0], prop=sample.prop[0])
    project.action_cards = cards_to_records([old_card])
    project.save(path)
    original = path.read_bytes()
    owner = SimpleNamespace(window=root, path=path, project=project, update_group=lambda: None, refresh=lambda: None)
    workbench = ActionSequenceDialog(owner)
    root.update()
    workbench.window.grab_set()
    named(workbench.window, "browse_action_cards").invoke()
    gallery = toplevel(root)
    assert workbench.window.grab_current() == gallery
    named(gallery, "cover_" + key).invoke()
    named(gallery, "add_preset").invoke()
    assert workbench.window.grab_current() == workbench.window
    assert len(workbench.cards) == 2 and workbench.cards[-1].preset_id == key
    assert path.read_bytes() == original, "Browsing and unsaved selection changed the existing project file"
    workbench.tabs.select(1)
    wait(root, lambda: sum(bool(image_present(widget)) for widget in descend(workbench.board)
                          if isinstance(widget, ttk.Label)) >= 2,
         "Legacy and new presets did not render in the sequence grid")
    workbench.save()
    reopened = ProductionProject.open(path)
    assert len(reopened.action_cards) == 2 and reopened.action_cards[1]["preset_id"] == key
    assert not reopened.images and all(not record["reference"] for record in reopened.action_cards)

    reference = temp / "approved-project-reference.png"
    Image.new("RGB", (320, 180), "#a42660").save(reference)
    attached = owner.project.import_image(
        path, reference, reference.name, action="直接复用", reason="本地合成样例", inspection="画面已核对",
        reference_only=True,
    )
    workbench.images = [attached]
    workbench.cards[-1] = replace(workbench.cards[-1], reference=attached.id)
    workbench.render_board()
    wait(root, lambda: any(getattr(widget, "preview_kind", None) == "reference" and image_present(widget)
                          for widget in descend(workbench.board)),
         "The attached project reference did not take precedence over the built-in preview")
    workbench.window.destroy()
    print("Verified actual action editor, legacy preset preview, project reopen and delivery-image isolation", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, str(Path.cwd()))
    validate_assets()
    root = tk.Tk()
    callback_errors = []

    def report_callback(_kind, exception, trace):
        callback_errors.append(exception.with_traceback(trace))

    root.report_callback_exception = report_callback
    try:
        with TemporaryDirectory(prefix="studio-action-previews-") as folder:
            exercise(root, Path(folder))
            if callback_errors:
                raise callback_errors[0]
    finally:
        root.destroy()
