"""Refresh storyboard guide screenshots from the running desktop app.

Use a dedicated X11 desktop with Tk, Pillow, and Noto Sans CJK SC installed.
Run from the repository root with python -m scripts.capture_storyboard_guide.
The only file chooser replies and project data come from disposable local examples.
Capture the 3D director with scripts.capture_director_guide instead.
"""

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
from unittest.mock import patch

from PIL import ImageGrab

from scripts.windows_trial import ROOT, make_examples
from src import windows_launcher
from src.action_card_catalog import ACTION_PRESETS
from src.action_preset_gallery import _preview_frames
from src.production_rules import ENGLISH
from src.ui_language import translate


TOPICS = (
    "home", "project", "script", "shots", "drafts", "inventory", "generate_assets", "generate_board",
    "prompts", "assets", "media", "media_preview", "costume", "action_sequence", "action_gallery",
    "action_preview", "dialogue", "pose", "layout", "deliver",
)
DEFAULT_OUTPUT = ROOT / "assets" / "storyboard_guide"
WIDTH, HEIGHT = 1280, 880
SCRIPT = {
    "zh": "内景 · 信号站 · 夜\n\n门保持关闭。柜体在左侧墙边。\n门右侧的信号灯由琥珀色转为绿色，随后持续亮起。",
    "en": "INT. SIGNAL STATION — NIGHT\n\nThe door stays shut. A cabinet stands against the left wall.\n"
          "The light to the right of the door changes from amber to green and stays on.",
}
ASSETS = {
    "zh": "场景 · 信号站内景（SB01-01 至 SB01-09）\n道具 · 关闭的门、左侧柜体、右侧信号灯\n状态 · 琥珀色转为稳定绿色；其他物件的位置保持不变。",
    "en": "Set · Signal station interior (SB01-01 to SB01-09)\nProps · Closed door, cabinet on the left, right-side signal light\n"
          "State · Amber changes to steady green. Other fixtures stay in place.",
}


def children(widget):
    for child in widget.winfo_children():
        yield child
        yield from children(child)


class Capture:
    def __init__(self, root, language, project, output, requested):
        self.root = root
        self.language = language
        self.project = project
        self.output = output
        self.requested = requested
        self.saved = set()

    def wait(self, test, detail, *, parent=None):
        deadline = monotonic() + 6
        while monotonic() < deadline:
            self.root.update()
            if result := test(parent or self.root):
                return result
            sleep(0.025)
        raise RuntimeError(f"Missing ready application control: {detail}")

    def control(self, name, *, parent=None, kind=tk.Widget):
        return self.wait(lambda scope: next(
            (widget for widget in children(scope)
             if isinstance(widget, kind) and widget.winfo_name() == name and widget.winfo_ismapped()), None),
            name, parent=parent)

    def press(self, label, *, parent=None, english=None):
        caption = english if english and self.language == "en" else translate(self.root, label)
        control = self.wait(lambda scope: next(
            (widget for widget in children(scope)
             if isinstance(widget, ttk.Button) and widget.winfo_ismapped() and widget.cget("text") == caption),
            None), caption, parent=parent)
        self.invoke(control)

    def invoke(self, control):
        if control.instate(["disabled"]):
            raise RuntimeError(f"Application control is disabled: {control.cget('text')}")
        control.invoke()
        self.root.update()

    def production_page(self):
        self.navigation().select(0)
        self.root.update()

    def navigation(self):
        return next(widget for widget in children(self.root) if isinstance(widget, ttk.Notebook))

    def close_task(self):
        navigation = self.navigation()
        page = navigation.nametowidget(navigation.select())
        chip = self.control(page.winfo_name().replace("task_page_", "task_"))
        self.invoke(self.control("close", parent=chip))

    def stage(self, button, *, picker="production_project_picker"):
        self.production_page()
        self.press(button)
        with patch.object(filedialog, "askopenfilename", return_value=str(self.project)):
            self.invoke(self.control("open_project", parent=self.control(picker)))

    def snapshot(self, topic, window=None):
        if topic not in self.requested:
            return
        window = window or self.root
        self.root.update()
        sleep(0.16)
        self.root.update()
        window.lift()
        self.root.update()
        left, top = window.winfo_rootx(), window.winfo_rooty()
        right, bottom = left + window.winfo_width(), top + window.winfo_height()
        if right > window.winfo_screenwidth() or bottom > window.winfo_screenheight():
            raise RuntimeError("The application must fit inside the capture desktop.")
        image = ImageGrab.grab(bbox=(left, top, right, bottom), xdisplay=os.environ.get("DISPLAY"))
        name = f"{topic}_{self.language}.webp"
        image.save(self.output / name, format="WEBP", quality=83, method=6)
        self.saved.add(topic)
        print(name, image.size, flush=True)

    def capture_project(self):
        with patch.object(filedialog, "askopenfilename", return_value=str(self.project)):
            self.press("继续已有项目")
            window = self.wait(lambda scope: next(
                (w for w in children(scope) if isinstance(w, tk.Toplevel) and w.winfo_ismapped()), None),
                "the open group project")
        window.geometry("1150x795+65+50")
        self.snapshot("project", window)
        window.destroy()

    def capture_script(self):
        self.production_page()
        self.press("剧本创作")
        source = self.control("planning_source", kind=tk.Text)
        source.insert("1.0", SCRIPT[self.language])
        self.snapshot("script")
        source.delete("1.0", "end")
        self.close_task()

    def capture_shots(self):
        self.stage("分镜拆分")
        editor = self.control("production_panel")
        tree = self.wait(lambda scope: next(
            (w for w in children(scope) if isinstance(w, ttk.Treeview) and w.winfo_ismapped()), None),
            "the storyboard shot table", parent=editor)
        tree.selection_set(tree.get_children()[0])
        self.snapshot("shots")
        if "drafts" in self.requested:
            self.press("AI 拆分镜", parent=editor)
            self.control("drafting_panel")
            self.snapshot("drafts")
            self.close_task()
        self.close_task()

    def capture_assets(self):
        self.stage("批准图像")
        editor = self.control("production_panel")
        self.snapshot("assets")
        if not {"media", "media_preview"} & self.requested:
            return
        self.press("打开素材库", parent=editor)
        gallery = self.control("media_gallery")
        canvas = self.control("media_cards", parent=gallery)
        self.wait(lambda _: canvas.find_all(), "the media thumbnails")
        self.snapshot("media")
        if "media_preview" in self.requested:
            canvas.event_generate("<Button-1>", x=48, y=54)
            self.invoke(self.control("media_preview", parent=gallery, kind=ttk.Button))
            detail = self.control("media_detail")
            display = self.control("media_detail_preview", parent=detail)
            self.wait(lambda _: any(display.type(item) == "image" for item in display.find_all()),
                      "a decoded sample image")
            self.snapshot("media_preview")

    def capture_action(self):
        self.stage("人物动作编排", picker="action_project_picker")
        editor = self.control("action_sequence_editor")
        self.press("加入选中预设", parent=editor, english="Add preset")
        self.snapshot("action_sequence")
        if not {"action_gallery", "action_preview", "dialogue"} & self.requested:
            return
        self.invoke(self.control("browse_action_cards", parent=editor))
        library = self.control("action_presets")
        preview = self.control("frame_beat", parent=library, kind=ttk.Button)
        self.wait(lambda _: bool(preview.cget("image")), "an action preview")
        self.snapshot("action_gallery")
        if "action_preview" in self.requested:
            self.invoke(preview)
            self.control("enlarged_action_frame")
            self.snapshot("action_preview")
            self.invoke(self.control("back_to_presets"))
        if "dialogue" in self.requested:
            self.invoke(self.control("dialogue_card_library"))
            dialogue = self.control("dialogue_cards")
            self.invoke(self.control("dialogue_show_1", parent=dialogue))
            picture = self.control("dialogue_image", parent=dialogue)
            self.wait(lambda _: bool(picture.cget("image")), "an over-the-shoulder image")
            self.snapshot("dialogue")

    def populate_stage(self, topic, editor):
        if topic == "inventory":
            self.control("planning_output", parent=editor, kind=tk.Text).insert("1.0", ASSETS[self.language])
        if topic == "pose":
            reference = self.project.with_name("Sample pose.png")
            _start, beat, _end = _preview_frames(ACTION_PRESETS[0].id)
            beat.save(reference)
            with patch.object(filedialog, "askopenfilename", return_value=str(reference)):
                self.press("导入本地参考图", parent=editor, english="Import local reference")

    def run(self):
        self.snapshot("home")
        if "project" in self.requested:
            self.capture_project()
        if "script" in self.requested:
            self.capture_script()
        if {"shots", "drafts"} & self.requested:
            self.capture_shots()
        stages = (
            ("inventory", "资产分析", "planning_editor"),
            ("generate_assets", "资产图生成", "image_production_editor"),
            ("generate_board", "故事板图生成", "image_production_editor"),
            ("prompts", "提示词生成", "production_panel"),
            ("costume", "角色服装设计", "costume_reference_editor"),
            ("pose", "角色动作设计", "pose_reference_editor"),
            ("layout", "排版与交接", "layout_editor"),
            ("deliver", "故事板组打包交付", "production_panel"),
        )
        for topic, button, expected in stages:
            if topic in self.requested:
                self.stage(button)
                editor = self.control(expected)
                self.populate_stage(topic, editor)
                self.snapshot(topic)
                if topic == "inventory":
                    self.control("planning_output", parent=editor, kind=tk.Text).delete("1.0", "end")
                self.close_task()
        if {"assets", "media", "media_preview"} & self.requested:
            self.capture_assets()
            self.close_task()
        if {"action_sequence", "action_gallery", "action_preview", "dialogue"} & self.requested:
            self.capture_action()
        if missing := self.requested - self.saved:
            raise RuntimeError(f"Missing captures: {', '.join(sorted(missing))}")


def capture_desktop(language, project, output, requested):
    errors = []

    class GuideWindow(tk.Tk):
        def mainloop(self, *args):
            self.geometry(f"{WIDTH}x{HEIGHT}+0+0")
            if "Noto Sans CJK SC" not in font.families(self):
                raise RuntimeError("Tk must be able to render Noto Sans CJK SC for this capture.")
            for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
                font.nametofont(name, root=self).configure(family="Noto Sans CJK SC", size=10)
            self.after(150, self.drive)
            return super().mainloop(*args)

        def report_callback_exception(self, _type, value, _traceback):
            errors.append(value)
            self.quit()

        def drive(self):
            try:
                Capture(self, language, project, output, requested).run()
            except Exception as error:
                errors.append(error)
            finally:
                self.quit()

    def unexpected_error(title, detail, **_options):
        raise RuntimeError(f"{title}: {detail}")

    with (patch.object(tk, "Tk", GuideWindow), patch.object(windows_launcher, "load_language", return_value=language),
          patch.object(messagebox, "showerror", side_effect=unexpected_error)):
        windows_launcher.open_workbench("")
    if errors:
        raise errors[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("zh", "en"))
    parser.add_argument("--topic", choices=TOPICS, action="append")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    requested = set(options.topic or TOPICS)
    languages = (options.language,) if options.language else ("zh", "en")
    for language in languages:
        with TemporaryDirectory(prefix="studio-guide-") as temp:
            examples = Path(temp) / "Examples"
            make_examples(examples, Path(temp) / "scratch", ENGLISH, "Example.zip")
            capture_desktop(language, examples / "SB01.cfproject", options.output, requested)


if __name__ == "__main__":
    main()
