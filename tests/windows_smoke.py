"""Exercise the batch file and real Tk widgets with a synthetic local ZIP."""

import faulthandler
import json
import os
from runpy import run_path
import subprocess
import sys
import time
from base64 import b64decode
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_TAB, ECOMMERCE_TAB, REVIEW_TAB, API_TAB, TUTORIAL_TAB = range(5)


def attach_chinese_layout(project, path, folder, *, distinct=1, local=3, extras=0):
    """Register simple synthetic walls and fixed equipment without calling an image model."""
    from src.production_layout import bind_window

    def picture(name, index, *, muted=False, reference=False, reverse=False, site=0):
        target = folder / name
        wall = (235, 235, 235) if muted else ((120, 156, 160) if site else (162, 138, 102))
        floor = (195, 195, 195) if muted else ((65, 103, 103) if site else (113, 73, 59))
        feature = (220, 220, 220) if muted else ((53, 80, 98) if site else (66, 95, 78))
        canvas = Image.new("RGB", (640, 360), wall)
        paint = ImageDraw.Draw(canvas)
        paint.polygon([(0, 288), (219, 220), (400, 220), (640, 272), (640, 360), (0, 360)], fill=floor, outline="#242424")
        paint.rectangle((100 if reverse else 366, 50, 226 if reverse else 494, 240), fill=feature, outline="#333333", width=5)
        x = 516 if reverse else 92 + index * 7
        paint.rectangle((x, 144, x+59, 190), fill="#343434", outline="#111111", width=4)
        paint.ellipse((x+12, 156, x+21, 165), fill="#d7d7d7" if muted else "#e9ad60")
        paint.line((0, 47, 639, 47 + index * 8), fill="#565656", width=3)
        canvas.save(target)
        return project.import_image(path, target, name, action="直接复用", reason="本地合成测试素材",
                                    inspection="模拟门、设备和机位关系", reference_only=reference)

    places = ("南厅", "北廊")[:distinct]
    plates = {}
    for site, place in enumerate(places):
        picture(f"scene_{place}_main_16x9.png", 0, site=site)
        picture(f"scene_{place}_reverse_16x9.png", 2, site=site, reverse=True)
        for camera in range(local):
            plates[(place, camera)] = picture(f"{place}_批准净板_{camera+1:02d}.png", camera, reference=True, site=site)
    for index, shot in enumerate(project.shots):
        site = min(index // 5, distinct - 1)
        camera = (index % 5 if distinct > 1 else index) % local
        shot.scene = places[site]
        shot.plate_note = f"{shot.scene}第 {camera + 1} 机位独立净板"
        shot.fields["机位空间"] = f"{shot.scene}同侧机位 {camera + 1}"
        shot.fields["可见范围"] = f"固定小门与设备 {camera + 1}"
        board = picture(f"合成板格_{index+1:02d}.png", index+1, muted=True, reference=True, site=site)
        bind_window(project, path, shot.id, "board", board.id)
        bind_window(project, path, shot.id, "plate", plates[(shot.scene, camera)].id)
    for index in range(extras):
        picture(f"other_characters_{index+1:02d}_合成预算载体_16x9.png", index)


def run_inside_launcher():
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    from src.brand import APP_FOLDER, APP_NAME_EN, APP_NAME_ZH, VERSION

    archive = os.environ["COMICFLOW_SMOKE_ZIP"]
    mode = os.environ["COMICFLOW_SMOKE_MODE"]
    project_path = Path(archive).with_name(f"制片-{mode}.cfproject")
    if mode == "shell-project":
        project_path = Path(os.environ["COMICFLOW_SMOKE_PROJECT"])
    marker = project_path.with_suffix(".status")

    def walk(root, kind):
        for child in root.winfo_children():
            if isinstance(child, kind):
                yield child
            yield from walk(child, kind)

    def click(root, title):
        root.update_idletasks()
        matches = [widget for widget in walk(root, ttk.Button) if widget.cget("text") == title]
        button = next((widget for widget in matches if widget.winfo_ismapped()), matches[0])
        assert button.instate(["!disabled"]), title
        button.invoke()

    def named(root, kind, name, *, mapped=False):
        return next(widget for widget in walk(root, kind)
                    if widget.winfo_name() == name and (not mapped or widget.winfo_ismapped()))

    def wait_for(root, ready, reason):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            root.update()
            if (result := ready()):
                return result
            time.sleep(0.015)
        raise AssertionError(reason)

    def page_at(root, index):
        navigation = next(walk(root, ttk.Notebook))
        return navigation.nametowidget(navigation.tabs()[index])

    def show_page(root, index):
        navigation = next(walk(root, ttk.Notebook))
        navigation.select(index)
        root.update_idletasks()
        return navigation.nametowidget(navigation.select())

    def visible_frame(root, name):
        return wait_for(root, lambda: next((w for w in walk(root, (tk.Frame, ttk.Frame, ttk.LabelFrame))
                                            if w.winfo_name() == name and w.winfo_ismapped()), None),
                        f"Missing visible task frame {name}")

    def pick_production_project(root, title, path):
        click(show_page(root, PRODUCTION_TAB), title)
        picker = visible_frame(root, "production_project_picker")
        with patch.object(filedialog, "askopenfilename", return_value=str(path)) as file_picker:
            named(picker, ttk.Button, "open_project").invoke()
        assert file_picker.call_args.kwargs["parent"] is root
        return picker

    def close_current_task(root):
        navigation = next(walk(root, ttk.Notebook))
        page = navigation.nametowidget(navigation.select())
        chip = page.winfo_name().replace("task_page_", "task_")
        named(named(root, ttk.Frame, chip), ttk.Button, "close").invoke()
        root.update_idletasks()

    def fail(reason):
        print(reason, file=sys.stderr, flush=True)
        faulthandler.dump_traceback()
        if mode == "shell-project":
            marker.write_text(str(reason), encoding="utf-8")
        os._exit(10)

    class SmokeWindow(tk.Tk):
        def __init__(self):
            super().__init__()
            if mode in {"a-layout-125", "a-layout-150"}:
                percentage = int(mode.rsplit("-", 1)[1])
                self.tk.call("tk", "scaling", 96 / 72 * percentage / 100)

        def report_callback_exception(self, exc, value, traceback):
            sys.__excepthook__(exc, value, traceback)
            fail(value)

        def mainloop(self):
            self.after(100, self.begin)
            self.after(25000, lambda: fail("Desktop smoke timed out"))
            super().mainloop()

        def begin(self):
            if not self.winfo_viewable():
                self.after(100, self.begin)
                return
            if mode == "batch-file":
                panel = next((w for w in walk(self, ttk.Frame) if w.winfo_name() == "batch_workspace" and
                              w.winfo_ismapped()), None)
                combo = next((w for w in walk(panel, ttk.Combobox) if w.winfo_name() == "episode"), None) if panel else None
                if combo is None or len(self.tk.splitlist(combo.cget("values"))) != 3:
                    self.after(80, self.begin)
                    return
                print("Verified saved .cfbatch launcher argument restored three episodes", flush=True)
                print("COMICFLOW_GUI_OK", flush=True)
                self.destroy()
                return
            if mode == "image-entry":
                self.inspect_image_entry()
                return
            if mode == "shell-project":
                dialog = next(walk(self, tk.Toplevel))
                name = next(walk(dialog, ttk.Entry))
                assert name.get() == project_path.stem, name.get()
                tabs = next(walk(dialog, ttk.Notebook))
                assert tabs.tab(1, "state") == "normal" and tabs.tab(3, "text") == "文本与排版"
                assert any(widget.instate(["selected"]) for widget in walk(self, ttk.Radiobutton)
                           if widget.cget("text") == "中文影片制作")
                assert any("中文影片制作 · v14.8.8" in self.getvar(variable)
                           for label in walk(dialog, ttk.Label) if (variable := label.cget("textvariable")))
                self.destroy()
                marker.write_text("COMICFLOW_GUI_OK", encoding="utf-8")
                return
            navigation = next(walk(self, ttk.Notebook))
            initial_page = PRODUCTION_TAB if mode == "empty" or mode.startswith("a-layout-") else REVIEW_TAB
            assert navigation.index(navigation.select()) == initial_page
            field, validator, *_ = walk(page_at(self, REVIEW_TAB), ttk.Entry)
            assert field.get() == ("" if initial_page == PRODUCTION_TAB else archive), field.get()
            if mode.startswith("a-layout-"):
                self.inspect_release_notes()
                self.inspect_a_workbench()
                return
            if mode == "api-settings":
                self.inspect_api_settings()
                return
            if mode == "new-tools":
                self.inspect_new_tools()
                return
            if mode == "action-sequence":
                self.inspect_action_sequence()
                return
            if mode == "task-navigation":
                self.inspect_task_navigation()
                return
            if mode == "dialogue-blocking":
                self.inspect_dialogue_blocking()
                return
            if mode == "batch-center":
                self.inspect_batch_center()
                return
            if mode == "ecommerce":
                self.inspect_ecommerce()
                return
            if mode == "production-handoff":
                self.inspect_production_handoff()
                return
            if mode == "production-workspace":
                self.inspect_production_workspace()
                return
            if mode == "storyboard-guide":
                with patch.object(messagebox, "showerror", side_effect=self.fail_storyboard_guide):
                    self.inspect_storyboard_guide()
                return
            if mode == "workbench-guide":
                with patch.object(messagebox, "showerror", side_effect=self.fail_storyboard_guide):
                    self.inspect_workbench_guide()
                return
            if mode == "workbench-bridges":
                self.inspect_workbench_bridges()
                return
            if mode == "job-recovery":
                self.inspect_job_recovery()
                return
            if mode == "mode-switch":
                self.inspect_mode_switch(validator)
                return
            if mode == "ui-language-restore":
                assert self.title() == APP_NAME_EN
                click(self, "中文 / English")
                assert self.title() == APP_NAME_ZH
                print("COMICFLOW_GUI_OK", flush=True)
                self.destroy()
                return
            if mode == "file-only":
                from src.bundled_validators import bundled_validator
                from src.production_rules import ENGLISH

                assert Path(validator.get()) == bundled_validator(ENGLISH)
                validator.delete(0, "end")
                click(self, "开始验收")
                self.after(100, self.inspect_file_only)
                return
            if mode == "empty":
                production = show_page(self, PRODUCTION_TAB)
                click(production, "项目文件说明")
                self.update_idletasks()
                guidance = [label.cget("text") for label in walk(production, tk.Label) if label.winfo_ismapped()]
                assert any("软件会创建 .cfproject" in text for text in guidance)
                assert any("Examples/SB01.cfproject" in text for text in guidance)
                assert any("无需解压" in text for text in guidance)
                click(production, "项目文件说明")
                with patch.object(filedialog, "askopenfilename", return_value=archive) as picker:
                    click(production, "验收已有 ZIP")
                    assert picker.call_args.kwargs["filetypes"][0] == ("ZIP 交付包", "*.zip")
                navigation = next(walk(self, ttk.Notebook))
                assert navigation.index(navigation.select()) == REVIEW_TAB
                assert field.get() == archive
                print("Verified beginner guidance and the direct ZIP review route", flush=True)
            click(self, "开始验收")
            self.after(100, self.inspect_result)

        def inspect_api_settings(self):
            import socket

            from src.production_project import ProductionProject

            def input_field(scope, caption):
                label = next(w for w in walk(scope, ttk.Label) if w.cget("text") == caption)
                return label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]

            def enter(scope, caption, value):
                field = input_field(scope, caption)
                field.delete(0, "end")
                field.insert(0, value)
                return field

            def save_settings(tab):
                with (patch.object(socket, "getaddrinfo", side_effect=AssertionError("API configuration resolved a host")),
                      patch.object(socket.socket, "connect", side_effect=AssertionError("API configuration opened a connection"))):
                    click(tab, "保存本次设置")

            assert any("Seedance 2.0" in widget.cget("text") for widget in walk(self, tk.Label))
            navigation = next(walk(self, ttk.Notebook))
            assert [navigation.tab(tab, "text") for tab in navigation.tabs()] == [
                "故事板制作", "电商信息流视频复刻", "检查验收", "API 接入", "使用教程",
            ]
            tabs = next(walk(show_page(self, API_TAB), ttk.Notebook))
            assert [tabs.tab(i, "text") for i in range(3)] == ["文本创作", "AI 审图", "图像生成"]
            text, vision, image = (tabs.nametowidget(tab) for tab in tabs.tabs())
            key = "synthetic-shared-provider-key"
            enter(text, "模型 ID", "draft-text-test")
            assert enter(text, "API Key", key).cget("show") == "*"
            previous_base = input_field(text, "API 基础地址").get()
            enter(text, "API 基础地址", "http://invalid.example.test/v1")
            with patch.object(messagebox, "showerror") as error:
                save_settings(text)
            assert error.call_count == 1 and "HTTPS" in error.call_args.args[1]
            enter(text, "API 基础地址", previous_base)
            enter(text, "API Key", key)
            save_settings(text)

            tabs.select(1)
            base = input_field(vision, "API 基础地址").get()
            enter(vision, "模型 ID", "image-review-test")
            enter(vision, "API 基础地址", "https://different.example.test/api/v3")
            click(vision, "带入另一用途的 Key")
            assert not input_field(vision, "API Key").get()
            enter(vision, "API 基础地址", base)
            click(vision, "带入另一用途的 Key")
            assert input_field(vision, "API Key").get() == key
            assert input_field(vision, "模型 ID").get() == "image-review-test"
            enter(vision, "API 基础地址", "https://different.example.test/api/v3")
            assert not input_field(vision, "API Key").get()
            enter(vision, "API 基础地址", base)
            click(vision, "带入另一用途的 Key")
            save_settings(vision)

            tabs.select(2)
            assert not input_field(image, "API Key").get()
            provider = next(walk(image, ttk.Combobox))
            provider.set("腾讯云混元")
            provider.event_generate("<<ComboboxSelected>>")
            assert input_field(image, "腾讯云 SecretId").instate(["!disabled"])
            assert input_field(image, "腾讯云 SecretKey").cget("show") == "*"
            provider.current(0)
            provider.event_generate("<<ComboboxSelected>>")
            enter(image, "模型 ID", "image-generation-test")
            enter(image, "API Key", "synthetic-image-key")
            save_settings(image)
            self.exercise_page_help(visible_frame(self, "api_settings"), "api")
            assert tabs.index(tabs.select()) == 2
            assert input_field(image, "API Key").get() == "synthetic-image-key"

            click(self, "中文 / English")
            assert [navigation.tab(tab, "text") for tab in navigation.tabs()] == [
                "Storyboard production", "E-commerce video recreation", "Inspection & validation",
                "API connections", "Tutorial",
            ]
            assert [tabs.tab(i, "text") for i in range(3)] == ["Text drafting", "AI image review", "Image generation"]
            assert input_field(image, "Model ID").get() == "image-generation-test"
            self.inspect_tutorial(navigation)
            assert input_field(image, "模型 ID").get() == "image-generation-test"
            production = show_page(self, PRODUCTION_TAB)
            guidance = [label.cget("text") for label in walk(production, tk.Label)]
            assert any("Examples/SB01.cfproject" in text for text in guidance)
            assert any("开始验收" in text for text in guidance)

            ProductionProject("API smoke test", "EP01", "SB01").save(project_path)
            original_picker = filedialog.askopenfilename

            def choose_saved_project(**options):
                assert options["title"] == "打开已保存的项目（.cfproject）"
                assert options["filetypes"] == (("单组制作项目", "*.cfproject"),)
                return str(project_path)

            filedialog.askopenfilename = choose_saved_project
            click(self, "继续已有项目")

            def check_panel(parent, model_caption, expected_model, expected_key):
                dialog = next(walk(parent, tk.Toplevel))
                assert input_field(dialog, model_caption).get() == expected_model
                assert input_field(dialog, "API Key").get() == expected_key
                dialog.destroy()

            def check_project_tools():
                filedialog.askopenfilename = original_picker
                project = next(walk(self, tk.Toplevel))
                self.after(60, lambda: check_panel(project, "文本模型 ID", "draft-text-test", key))
                click(project, "对白与分镜起草")
                self.after(60, lambda: check_panel(project, "图像模型 ID", "image-generation-test", "synthetic-image-key"))
                click(project, "图像制片")
                project.destroy()
                show_page(self, REVIEW_TAB)
                click(self, "开始验收")
                self.after(100, check_review)

            def check_review():
                selector = next(walk(page_at(self, REVIEW_TAB), ttk.Combobox))
                if not selector["values"]:
                    self.after(100, check_review)
                    return
                selector.set("SB01/storyboard_2panel.png")
                selector.event_generate("<<ComboboxSelected>>")
                click(self, "AI 辅助看图")
                dialog = visible_frame(self, "vision_review_editor")
                assert not input_field(dialog, "审图重点（可选）").get()
                with patch.object(messagebox, "showinfo") as info:
                    click(dialog, "查看固定审图规则")
                    title, instructions = info.call_args.args
                    assert title == "查看固定审图规则" and "英文影片制作 v14.10.4" in instructions
                assert input_field(dialog, "模型 ID").get() == "image-review-test"
                assert input_field(dialog, "API Key").get() == key
                close_current_task(self)
                saved = project_path.read_text(encoding="utf-8")
                assert key not in saved and "synthetic-image-key" not in saved
                appdata = Path(os.environ["LOCALAPPDATA"]) / APP_FOLDER
                assert all(key not in path.read_text(encoding="utf-8")
                           and "synthetic-image-key" not in path.read_text(encoding="utf-8")
                           for path in appdata.iterdir() if path.is_file())
                print("Verified all API settings routes, scoped key reuse, and no credential writes", flush=True)
                print("COMICFLOW_GUI_OK", flush=True)
                self.destroy()

            self.after(120, check_project_tools)

        def read_workbench_topic(self, topic, *, reader=None):
            from src.workbench_guide_topics import WORKBENCH_TOPICS

            guide = reader if reader is not None else visible_frame(self, "storyboard_guide")
            outline = named(guide, ttk.Treeview, "guide_topic_list", mapped=True)
            title = named(guide, (tk.Label, ttk.Label), "guide_title")
            picture = named(guide, (tk.Label, ttk.Label), "guide_screenshot")
            self.update()
            assert outline.selection() == (topic,), (topic, outline.selection())
            assert title.cget("text") == WORKBENCH_TOPICS[topic].title[self.ui_language == "en"]
            assert picture.cget("image") and picture.winfo_ismapped()
            return guide

        def exercise_page_help(self, scope, topic):
            navigation = next(walk(self, ttk.Notebook))
            origin = navigation.select()
            origin_window = scope.winfo_toplevel()
            before_grab = self.grab_current()
            button = wait_for(self, lambda: next((item for item in walk(scope, ttk.Button)
                                                  if item.winfo_name() == "page_help" and item.winfo_ismapped()), None),
                              f"Contextual help unavailable for {topic}")
            button.invoke()
            guide = self.read_workbench_topic(topic)
            if origin_window is not self:
                assert not origin_window.winfo_viewable() and self.grab_current() is None
            named(guide, ttk.Button, "guide_return", mapped=True).invoke()
            self.update()
            assert navigation.select() == origin and scope.winfo_ismapped(), topic
            assert self.grab_current() is before_grab, topic

        def inspect_tutorial(self, navigation):
            from src import workbench_tutorial

            self.geometry("900x700")
            tutorial = show_page(self, TUTORIAL_TAB)
            overview = named(tutorial, ttk.Button, "guide_overview")
            if overview.winfo_ismapped():
                overview.invoke()
            tutorial = visible_frame(tutorial, "tutorial_overview")
            for topic in ("Quick start", "Script to delivery", "Check a delivery ZIP", "Connect an API"):
                click(tutorial, topic)
                images = [widget for widget in walk(tutorial, tk.Label) if widget.cget("image")]
                assert images and images[0].winfo_viewable(), topic
            click(tutorial, "Open API connections")
            self.update_idletasks()
            assert navigation.index(navigation.select()) == API_TAB
            show_page(self, TUTORIAL_TAB)
            click(self, "中文 / English")
            for topic in ("快速开始", "从剧本到交付", "检查交付 ZIP", "配置 API"):
                click(tutorial, topic)
                assert any(widget.cget("image") for widget in walk(tutorial, tk.Label)), topic
            original_picker = filedialog.askopenfilename
            try:
                filedialog.askopenfilename = lambda **options: archive if options["filetypes"][0][1] == "*.zip" else ""
                click(tutorial, "检查交付 ZIP")
                click(tutorial, "选择要验收的 ZIP")
                assert navigation.index(navigation.select()) == REVIEW_TAB
                assert next(walk(page_at(self, REVIEW_TAB), ttk.Entry)).get() == archive
            finally:
                filedialog.askopenfilename = original_picker
            show_page(self, TUTORIAL_TAB)
            click(tutorial, "快速开始")
            examples = Path(workbench_tutorial.__file__).resolve().parents[1] / "Examples"
            if (examples / "SB01.cfproject").is_file():
                click(tutorial, "打开示例项目")
                self.update()
                dialog = next(walk(self, tk.Toplevel))
                project_tabs = next(walk(dialog, ttk.Notebook))
                assert project_tabs.tab(project_tabs.select(), "text") == "镜头清单"
                dialog.destroy()
            print("Verified all four illustrated tutorial topics, language switch and linked actions", flush=True)

        @staticmethod
        def fail_storyboard_guide(title, detail, **_):
            raise AssertionError(f"{title}: {detail}")

        def inspect_storyboard_guide(self):
            from src.production_project import ProductionProject
            from src.storyboard_guide_topics import STORYBOARD_TOPICS
            from src.workbench_tutorial import __file__ as tutorial_file

            root = Path(tutorial_file).resolve().parents[1]
            actual_topics = {
                "home", "project", "script", "shots", "drafts", "inventory", "generate_assets",
                "generate_board", "prompts", "assets", "media", "media_preview", "costume",
                "action_sequence", "action_gallery", "action_preview", "dialogue", "pose",
                "director", "layout", "deliver",
            }
            assert actual_topics <= set(STORYBOARD_TOPICS)
            for topic in actual_topics:
                for language in ("zh", "en"):
                    screenshot = root / "assets" / "storyboard_guide" / f"{topic}_{language}.webp"
                    with Image.open(screenshot) as image:
                        image.load()
                        assert image.format == "WEBP" and min(image.size) >= 160, screenshot

            self.geometry("900x700")
            navigation = next(walk(self, ttk.Notebook))
            tutorial = show_page(self, TUTORIAL_TAB)
            named(tutorial, ttk.Button, "storyboard_guide_open", mapped=True).invoke()
            guide = visible_frame(self, "storyboard_guide")
            topics = named(guide, ttk.Treeview, "guide_topic_list", mapped=True)
            title = named(guide, (tk.Label, ttk.Label), "guide_title")
            illustration = named(guide, (tk.Label, ttk.Label), "guide_screenshot")

            def show_topic(topic):
                assert topics.exists(topic), topic
                topics.selection_set(topic)
                topics.see(topic)
                topics.event_generate("<<TreeviewSelect>>")
                self.update()

            def read_topic(topic, locale):
                assert topics.selection() == (topic,), (topic, topics.selection())
                assert title.cget("text") == STORYBOARD_TOPICS[topic].title[locale], title.cget("text")
                assert illustration.cget("image") and illustration.winfo_ismapped()
                assert not any(dialog.winfo_viewable() for dialog in walk(self, tk.Toplevel))

            show_topic("shots")
            read_topic("shots", 0)
            zoom = named(guide, ttk.Button, "guide_image_zoom", mapped=True)
            reader = named(guide, tk.Canvas, "guide_reader", mapped=True)
            zoom.invoke()
            self.update()
            assert reader.xview()[1] < 1 and not list(walk(self, tk.Toplevel))
            zoom.invoke()
            self.update()
            assert reader.xview() == (0.0, 1.0)
            before = str(illustration.cget("image"))
            click(self, "中文 / English")
            self.update()
            assert self.title() == APP_NAME_EN
            read_topic("shots", 1)
            assert str(illustration.cget("image")) != before
            click(self, "中文 / English")
            self.update()
            assert self.title() == APP_NAME_ZH

            guide_folder = project_path.with_name("教程练习独立目录")
            guide_folder.mkdir()
            bundled_example = root / "Examples" / "SB01.cfproject"
            bundled_data = bundled_example.read_bytes()
            show_topic("home")
            with patch.object(filedialog, "askdirectory", return_value=str(guide_folder)):
                named(guide, ttk.Button, "practice_script", mapped=True).invoke()
            writer = visible_frame(self, "planning_editor")
            editor = named(writer, tk.Text, "planning_source")
            (source_file,) = tuple(guide_folder.rglob("Approved-Script.txt"))
            assert editor.get("1.0", "end-1c").strip() == source_file.read_text(encoding="utf-8-sig").strip()
            editor.insert("end-1c", "\n\n本地分镜教程练习。")
            editor.mark_set("insert", "2.0")
            draft = editor.get("1.0", "end-1c")
            source_tab = navigation.select()
            source_before = source_file.read_bytes()
            named(navigation.nametowidget(source_tab), ttk.Button, "page_help", mapped=True).invoke()
            visible_frame(self, "storyboard_guide")
            read_topic("script", 0)
            named(guide, ttk.Button, "guide_return", mapped=True).invoke()
            self.update()
            assert navigation.select() == source_tab and visible_frame(self, "planning_editor") is writer
            assert editor.get("1.0", "end-1c") == draft and editor.index("insert") == "2.0"
            assert source_file.read_bytes() == source_before

            named(writer, ttk.Button, "use_left_script", mapped=True).invoke()
            target = visible_frame(self, "script_target_picker")
            planned = guide_folder / "练习新分镜.cfproject"
            with (patch.object(messagebox, "askyesno", return_value=True),
                  patch.object(filedialog, "asksaveasfilename", return_value=str(planned))):
                named(target, ttk.Button, "new_script_project", mapped=True).invoke()
            visible_frame(self, "production_panel")
            assert ProductionProject.open(planned).sources[0].text.strip() == draft.strip()
            named(navigation.nametowidget(navigation.select()), ttk.Button, "page_help", mapped=True).invoke()
            visible_frame(self, "storyboard_guide")
            read_topic("shots", 0)
            self.geometry("1280x880")
            self.update()

            show_topic("home")
            with patch.object(filedialog, "askdirectory", return_value=str(guide_folder)):
                named(guide, ttk.Button, "practice_existing", mapped=True).invoke()
            assets = visible_frame(self, "production_panel")
            (copied,) = tuple(guide_folder.rglob("SB01.cfproject"))
            assert not copied.samefile(bundled_example)
            assert bundled_example.read_bytes() == bundled_data
            copied_project = ProductionProject.open(copied)
            assert copied_project.images and copied_project.shots
            assert all(copied_project.checked_image(copied, image).is_file() for image in copied_project.images)
            assert next(w for w in walk(assets, ttk.Treeview) if w.winfo_ismapped()).get_children()
            asset_tab = navigation.select()
            named(navigation.nametowidget(asset_tab), ttk.Button, "page_help", mapped=True).invoke()
            visible_frame(self, "storyboard_guide")
            read_topic("assets", 0)
            named(guide, ttk.Button, "guide_return", mapped=True).invoke()
            self.update()
            assert navigation.select() == asset_tab and visible_frame(self, "production_panel") is assets

            click(assets, "打开素材库")
            library = visible_frame(self, "media_gallery")
            cards = named(library, tk.Canvas, "media_cards")
            wait_for(self, cards.find_all, "The practice project images are missing from the gallery")
            cards.event_generate("<Button-1>", x=45, y=40)
            named(library, ttk.Button, "media_preview", mapped=True).invoke()
            detail = visible_frame(self, "media_detail")
            named(detail, ttk.Button, "page_help", mapped=True).invoke()
            visible_frame(self, "storyboard_guide")
            read_topic("media_preview", 0)
            named(guide, ttk.Button, "guide_return", mapped=True).invoke()
            assert visible_frame(self, "media_detail") is detail
            named(detail, ttk.Button, "media_detail_close", mapped=True).invoke()

            pick_production_project(self, "故事板组打包交付", copied)
            delivery = visible_frame(self, "production_panel")
            click(delivery, "生成逐格复核预览")
            panel = visible_frame(self, "production_subpanel")
            named(panel, ttk.Button, "page_help", mapped=True).invoke()
            visible_frame(self, "storyboard_guide")
            read_topic("deliver", 0)
            named(guide, ttk.Button, "guide_return", mapped=True).invoke()
            assert visible_frame(self, "production_subpanel") is panel
            click(panel, "返回")
            with patch.object(messagebox, "askyesno", return_value=True):
                click(delivery, "确认本版画面")
            delivered = guide_folder / "教程交付复测.zip"
            with patch.object(filedialog, "asksaveasfilename", return_value=str(delivered)):
                click(delivery, "验收并导出 ZIP")
            with ZipFile(delivered) as archive:
                assert archive.testzip() is None
                assert "SB01/SD2_prompt.txt" in archive.namelist()

            show_page(self, TUTORIAL_TAB)
            named(guide, ttk.Button, "guide_overview", mapped=True).invoke()
            click(visible_frame(self, "tutorial_overview"), "打开示例项目")
            self.update()
            native_project = next(walk(self, tk.Toplevel))
            click(show_page(native_project, 2), "打开素材库")
            self.update()
            native_library = next(walk(native_project, tk.Toplevel))
            assert self.grab_current() is native_library
            named(native_library, ttk.Button, "page_help", mapped=True).invoke()
            visible_frame(self, "storyboard_guide")
            read_topic("media", 0)
            assert self.grab_current() is None
            named(guide, ttk.Button, "guide_return", mapped=True).invoke()
            self.update()
            assert native_project.winfo_viewable() and native_library.winfo_viewable()
            assert self.grab_current() is native_library
            named(native_library, ttk.Button, "media_close", mapped=True).invoke()
            native_project.destroy()
            assert bundled_example.read_bytes() == bundled_data
            print("Verified bilingual storyboard guide, linked help, draft and modal return, isolated practice routes "
                  "and a reopened storyboard delivery ZIP", flush=True)
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def inspect_workbench_guide(self):
            from src.asset_registry import sha256_file
            from src.batch_workspace import BatchWorkspace
            from src.bundled_validators import bundled_validator
            from src.ecommerce_project import EcommerceProject
            from src.production_export import build_batch
            from src.production_images import approve_candidate
            from src.production_project import ProductionProject
            from src.production_rules import ENGLISH
            from src.workbench_guide_topics import WORKBENCH_TOPICS
            from src.workbench_tutorial import __file__ as tutorial_file

            root = Path(tutorial_file).resolve().parents[1]
            expected = {
                "general", "guide_navigation", "ecommerce_import", "ecommerce_shots", "ecommerce_assets",
                "ecommerce_delivery", "batch_import", "batch_plan", "batch_assets", "batch_queue",
                "batch_delivery", "review_zip", "review_images", "review_cuts", "review_repair", "jobs", "api",
            }
            assert set(WORKBENCH_TOPICS) == expected
            verified = {}
            for topic in expected:
                for language in ("zh", "en"):
                    screenshot = root / "assets" / "workbench_guide" / f"{topic}_{language}.webp"
                    with Image.open(screenshot) as image:
                        image.load()
                        assert image.format == "WEBP" and image.width >= 640 and image.height >= 250, screenshot
                    verified[topic, language] = sha256_file(screenshot)
                assert verified[topic, "zh"] != verified[topic, "en"], topic

            self.geometry("1160x870")
            tutorial = show_page(self, TUTORIAL_TAB)
            named(tutorial, ttk.Button, "workbench_guide_open", mapped=True).invoke()
            guide = self.read_workbench_topic("general")
            topics = named(guide, ttk.Treeview, "guide_topic_list", mapped=True)

            def read(topic):
                topics.selection_set(topic)
                topics.see(topic)
                topics.event_generate("<<TreeviewSelect>>")
                self.read_workbench_topic(topic, reader=guide)

            read("guide_navigation")
            illustration = named(guide, (tk.Label, ttk.Label), "guide_screenshot")
            chinese_picture = illustration.cget("image")
            click(self, "中文 / English")
            self.read_workbench_topic("guide_navigation", reader=guide)
            assert self.title() == APP_NAME_EN and illustration.cget("image") != chinese_picture
            for topic in sorted(expected):
                read(topic)
            click(self, "中文 / English")
            assert self.title() == APP_NAME_ZH
            for topic in sorted(expected):
                read(topic)

            practice = project_path.with_name("教程工作台演练")
            practice.mkdir()

            def start_practice(kind):
                show_page(self, TUTORIAL_TAB)
                read("general")
                with patch.object(filedialog, "askdirectory", return_value=str(practice)):
                    named(guide, ttk.Button, f"practice_{kind}", mapped=True).invoke()

            examples = root / "Examples"
            ecom = examples / "Workbench" / "Ecommerce"
            start_practice("ecommerce")
            flow = visible_frame(self, "ecommerce_workflow")
            opened = next(practice.rglob("Practice.cfecom"))
            loaded = EcommerceProject.open(opened)
            assert loaded.product_name and not loaded.product_reviewed
            assert Path(loaded.video_path).is_file() and loaded.product_refs
            assert all(Path(path).is_file() and practice in Path(path).parents for path in loaded.product_refs)
            assert (page_at(self, ECOMMERCE_TAB).winfo_ismapped() and
                    next(walk(flow, ttk.Notebook)).index("current") == 0)
            self.exercise_page_help(flow, "ecommerce_import")
            self.exercise_packaged_ecommerce(opened.parent)

            batch_source = examples / "Workbench" / "Batch" / "Signal-Station.cfbatch"
            baseline_batch = sha256_file(batch_source)
            start_practice("batch")
            batch = visible_frame(self, "batch_workspace")
            manifest = next(practice.rglob(batch_source.name))
            workspace = BatchWorkspace.open(manifest)
            episode, group = named(batch, ttk.Combobox, "episode"), named(batch, ttk.Combobox, "batch_group")
            wait_for(self, lambda: len(episode["values"]) == 2, "The copied practice batch did not restore two episodes")
            assert [item.id for item in workspace.episodes] == ["EP01", "EP02"]
            assert not manifest.samefile(batch_source)
            episode.current(1)
            episode.event_generate("<<ComboboxSelected>>")
            trace = named(batch, ttk.Treeview, "trace")
            wait_for(self, lambda: any("巡检员" in trace.set(row, "text") for row in trace.get_children()),
                     "The copied batch did not load Episode 2's source trace")
            assert "SB02" in group["values"]
            group.set("SB02")
            group.event_generate("<<ComboboxSelected>>")
            self.exercise_page_help(batch, "batch_plan")
            assert episode.get().startswith("EP02") and group.get() == "SB02"
            named(batch, ttk.Button, "open_target_group", mapped=True).invoke()
            header = visible_frame(self, "production_task_header")
            wait_for(self, lambda: any("EP02" in label.cget("text") and "SB02" in label.cget("text")
                                      for label in walk(header, ttk.Label)), "Batch sample opened the wrong group")
            named(header, ttk.Button, "return_to_batch", mapped=True).invoke()
            assert visible_frame(self, "batch_workspace") is batch
            assert episode.get().startswith("EP02") and group.get() == "SB02"
            named(batch, ttk.Button, "step_assets", mapped=True).invoke()
            self.exercise_page_help(batch, "batch_assets")
            assert workspace.required_asset_gaps("EP02", "SB02")
            bind = wait_for(self, lambda: next((button for button in walk(batch, ttk.Button)
                                                if button.winfo_ismapped() and button.instate(["!disabled"])
                                                and button.cget("text") == "绑定已批准依赖"), None),
                            "The copied batch did not finish reopening Episode 2 / SB02")
            bind.invoke()
            wait_for(self, lambda: not BatchWorkspace.open(manifest).required_asset_gaps("EP02", "SB02"),
                     "The approved shared asset did not bind to Episode 2 / SB02")
            assert sha256_file(batch_source) == baseline_batch

            start_practice("review")
            review = page_at(self, REVIEW_TAB)
            zip_entry, validator, *_ = walk(review, ttk.Entry)
            baseline = Path(zip_entry.get())
            original = examples / baseline.name
            assert review.winfo_ismapped() and practice in baseline.parents and baseline.is_file()
            assert baseline.read_bytes() == original.read_bytes()
            assert Path(validator.get()) == bundled_validator(ENGLISH)
            self.exercise_page_help(review, "review_zip")
            assert zip_entry.get() == str(baseline)
            click(review, "开始验收")
            selector = next(walk(review, ttk.Combobox))
            wait_for(self, lambda: bool(selector["values"]), "Bundled English ZIP did not produce a preview")
            assert any("自动检查通过" in self.getvar(variable) for label in walk(review, ttk.Label)
                       if (variable := label.cget("textvariable")))
            member = next(name for name in selector["values"]
                          if name.startswith("SB01/") and "_details_" in name and name.endswith(".png"))
            selector.set(member)
            selector.event_generate("<<ComboboxSelected>>")
            with patch.object(filedialog, "askopenfilename",
                              side_effect=AssertionError("The practice ZIP should find its exact copied project")):
                named(review, ttk.Button, "return_to_production", mapped=True).invoke()
                assets = visible_frame(self, "production_panel")
            asset_table = next(tree for tree in walk(assets, ttk.Treeview) if tree.winfo_ismapped())
            assert any(member.partition("/")[2] in str(asset_table.item(row, "values"))
                       for row in asset_table.selection())
            show_page(self, REVIEW_TAB)

            click(review, "图片大小与比例")
            image_window = next(walk(self, tk.Toplevel))
            with patch.object(filedialog, "askopenfilename", return_value=str(ecom / "Product.png")):
                click(image_window, "选择本地图片")
            controls = visible_frame(image_window, "review_image_controls")
            self.exercise_page_help(controls, "review_images")
            assert any("比例与 16:9 不同" in self.getvar(variable) for label in walk(image_window, ttk.Label)
                       if (variable := label.cget("textvariable")))
            click(image_window, "关闭")

            click(review, "景别机位与格间衔接")
            cut = next(walk(self, tk.Toplevel))
            choices = next(walk(cut, ttk.Combobox))
            click(cut, "下一处")
            selected_cut = choices.get()
            assert "SB01-02" in selected_cut
            self.exercise_page_help(visible_frame(cut, "review_cut_controls"), "review_cuts")
            assert choices.get() == selected_cut
            click(cut, "关闭")

            left_path, right_path = (baseline.with_name(f"SB{n:02d}.cfproject") for n in (1, 2))
            left, right = (ProductionProject.open(path) for path in (left_path, right_path))
            original_project = left_path.read_bytes()
            job = left.image_jobs[0]
            prior = next(asset for asset in left.images if asset.id == job["references"][0]["id"])
            target = approve_candidate(left, left_path, job, 0, prior.filename, "R2", "局部修改合成灯罩",
                                       "核对选区与边缘", replace_original=True)
            assert prior.digest != target.digest
            staging = baseline.with_name("返修后的交付目录")
            registry = baseline.with_name("Practice-Assets.sqlite3")
            local_validator = bundled_validator(ENGLISH)
            assert registry.is_file()
            build_batch([(left, left_path), (right, right_path)], staging, local_validator, registry)
            repaired = baseline.with_name("返修复验.zip")

            def repair():
                modal = next(walk(self, tk.Toplevel))
                tabs = named(modal, ttk.Notebook, "repair_workbook")
                tabs.select(1)
                pane = tabs.nametowidget(tabs.select())
                for row, item in ((0, "SB01-01"), (2, staging), (3, repaired), (4, "合成灯罩"),
                                  (5, "批准局部修改")):
                    field = pane.grid_slaves(row=row, column=1)[0]
                    assert isinstance(field, ttk.Entry)
                    field.insert(0, str(item))
                self.exercise_page_help(visible_frame(modal, "review_repair_controls"), "review_repair")
                assert tabs.index("current") == 1
                assert pane.grid_slaves(row=0, column=1)[0].get() == "SB01-01"
                report = next(walk(pane, tk.Text))
                click(pane, "查看关联文件")
                wait_for(self, lambda: "SD2_prompt.txt" in report.get("1.0", "end"), "Repair missed the selected shot")
                click(pane, "复验并打包")
                wait_for(self, lambda: "复验：已发布" in report.get("1.0", "end"),
                         "Bundled validator did not publish a repaired ZIP")
                assert sha256_file(repaired) in report.get("1.0", "end")
                modal.destroy()

            self.after(65, repair)
            click(review, "资产与返修")
            with ZipFile(baseline) as before, ZipFile(repaired) as after:
                assert after.testzip() is None and set(before.namelist()) == set(after.namelist())
                changed = {member for member in before.namelist() if before.read(member) != after.read(member)}
                assert changed == {"SB01/SB01_shot_details.txt", f"SB01/{prior.filename}"}, changed
                with Image.open(BytesIO(after.read(f"SB01/{prior.filename}"))) as image:
                    image.load()
                    assert image.width * 9 == image.height * 16
            assert (examples / left_path.name).read_bytes() == original_project
            assert left_path.read_bytes() != original_project and baseline.read_bytes() == original.read_bytes()

            click(review, "任务中心")
            jobs = visible_frame(self, "jobs_center")
            table = named(jobs, ttk.Treeview, "registered_jobs", mapped=True)
            table.selection_set(table.get_children()[0])
            selected_job = table.selection()
            self.exercise_page_help(jobs, "jobs")
            assert table.selection() == selected_job
            print("Verified offline workbench guides (Chinese and English), independent practice files, exact batch "
                  "episode/group return and the reopened ZIP repaired by the bundled English validator", flush=True)
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def exercise_packaged_ecommerce(self, folder):
            page = page_at(self, ECOMMERCE_TAB)
            phases = next(walk(page, ttk.Notebook))

            def select_check(parent, caption):
                check = next(item for item in walk(parent, ttk.Checkbutton) if item.cget("text") == caption)
                assert check.winfo_ismapped()
                check.invoke()

            select_check(page, "确认产品照片覆盖所需角度")
            click(page, "下一步：分镜分析")
            with (patch.object(filedialog, "askopenfilename", return_value=str(folder / "Shots.json")),
                  patch.object(messagebox, "askyesno", return_value=True)):
                click(page, "导入分镜 JSON")
                click(page, "确认分镜并分析资产")
            wait_for(self, lambda: phases.index("current") == 2, "Bundled e-commerce shots could not be confirmed")
            assets = next(walk(phases.nametowidget(phases.select()), ttk.Treeview))
            assert set(assets.get_children()) == {"product", "scene:产品展示台", "board:SB01"}

            def approve_preview():
                preview = visible_frame(page, "ecommerce_detail")
                click(preview, "确认使用这张图")
                self.update()

            assets.selection_set("product")
            click(page, "合成自有产品总图")
            approve_preview()
            for item, filename in (("scene:产品展示台", "Scene.png"), ("board:SB01", "SB01-Board.png")):
                assets.selection_set(item)
                with patch.object(filedialog, "askopenfilename", return_value=str(folder / filename)):
                    click(page, "导入批准图像")
                approve_preview()
            click(page, "下一步：提示词与交付")
            click(page, "生成交付预览")
            files = next(walk(phases.nametowidget(phases.select()), ttk.Treeview))
            wait_for(self, files.get_children, "Bundled e-commerce assets did not form a delivery preview")
            select_check(page, "已逐格核对画面、原语言对白、产品细节及独立人物资产")
            output = folder / "Luma-练习交付.zip"
            with patch.object(filedialog, "asksaveasfilename", return_value=str(output)):
                click(page, "验收并导出 ZIP")
            done = visible_frame(page, "ecommerce_detail")
            assert named(done, ttk.Label, "ecommerce_detail_title").cget("text") == "交付完成"
            with ZipFile(output) as package:
                assert package.testzip() is None
                name = "SB01_01-03/prompts/SD2_prompt.txt"
                assert package.read(name).decode("utf-8-sig").count("产品入画：Luma") == 3
            click(done, "关闭")
            print("Verified bundled e-commerce practice used the shipped shots and approved images to export a ZIP",
                  flush=True)

        def inspect_production_handoff(self):
            from src import drafting_dialog
            from src.production_project import ProductionProject
            from src.text_api import TextReply

            title = "信号站制片"
            body = "门打开了。\n\n值班员拿钥匙。"
            alternate = "新稿标记，门关了。"
            group = ProductionProject("接续制片试用", "EP01", "SB01")
            base = group.import_source(title, "R1", body)
            group.import_source(title, "R2", alternate)
            group.save(project_path)
            original = project_path.read_bytes()
            script_file = project_path.with_name(f"{title}.md")
            script_file.write_text(body, encoding="utf-8")
            click(show_page(self, PRODUCTION_TAB), "剧本创作")
            editor = visible_frame(self, "planning_editor")
            left = named(editor, tk.Text, "planning_source")
            with patch.object(filedialog, "askopenfilename", return_value=str(script_file)):
                named(editor, ttk.Button, "import_planning_source").invoke()
            assert left.get("1.0", "end-1c") == body
            title_box = next(walk(editor, ttk.Entry))
            assert title_box.get() == title

            named(editor, ttk.Button, "use_left_script").invoke()
            picker = visible_frame(self, "script_target_picker")
            named(picker, ttk.Button, "cancel_script_target").invoke()
            assert project_path.read_bytes() == original
            assert left.get("1.0", "end-1c") == body

            def fake_shots(settings, instructions, payload):
                data = json.loads(payload)
                assert data["approved_source"]["version"] == "R1"
                assert "值班员拿钥匙。" in data["approved_source"]["lines"].values()
                return TextReply('{"shots":[{"line_start":1,"line_end":3,'
                                 '"fields":{"画面/事件":"值班员拿起钥匙","人物站位":"门右侧"}}]}',
                                 "fixture-shot-handoff")

            with (patch.object(messagebox, "askyesno", return_value=True),
                  patch.object(filedialog, "askopenfilename", return_value=str(project_path)),
                  patch.object(drafting_dialog, "request_text", side_effect=fake_shots)):
                named(editor, ttk.Button, "use_left_script").invoke()
                picker = visible_frame(self, "script_target_picker")
                named(picker, ttk.Button, "existing_script_project").invoke()
                project = visible_frame(self, "production_panel")
                assert any(w.get() == f"{title} · R1" for w in walk(project, ttk.Combobox))
                assert not list(walk(self, tk.Toplevel)) and self.grab_current() is None

                click(project, "AI 拆分镜")
                tool = visible_frame(self, "drafting_panel")
                tabs = next(walk(tool, ttk.Notebook))
                assert tabs.tab(tabs.select(), "text") == "文本模型与历史"
                for caption in ("文本模型 ID", "API Key"):
                    label = next(widget for widget in walk(tool, ttk.Label) if widget.cget("text") == caption)
                    entry = label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]
                    entry.delete(0, "end")
                    entry.insert(0, "synthetic")
                click(tool, "调用模型起草")
                wait_for(self, lambda: ProductionProject.open(project_path).text_drafts,
                         "Synthetic draft did not arrive in the embedded shot task")
                click(tool, "采纳已选建议")
                grouped = ProductionProject.open(project_path)
                assert len(grouped.shots) == 1 and grouped.shots[0].source == base.id
                click(tool, "下一步：分析资产")
            analysis = visible_frame(self, "planning_editor")
            assert analysis is not editor
            before = project_path.read_bytes()
            original_source = named(analysis, tk.Text, "planning_source")
            assert original_source.get("1.0", "end-1c") == body
            assert original_source.cget("state") == "disabled"
            assert editor.winfo_exists() and left.get("1.0", "end-1c") == body
            assert not list(walk(self, tk.Toplevel)) and self.grab_current() is None

            click(analysis, "预览发送内容")

            def request_text():
                rows = (widget.get("1.0", "end-1c") for widget in walk(self, tk.Text)
                        if widget.winfo_ismapped() and widget.cget("state") == "disabled")
                return next((value for value in rows if value.startswith("软件锁定规则\n")), None)
            content = wait_for(self, request_text, "Asset request preview did not display the approved source")
            policy, material = content.split("\n\n用户资料\n", 1)
            assert "英文影片制作 v14.10.4" in policy
            shot_id = grouped.shots[0].id
            assert shot_id not in policy and shot_id in material
            assert "SB01-01" in material and "值班员拿起钥匙" in material
            assert alternate not in material and '"3": "值班员拿钥匙。"' in material
            assert project_path.read_bytes() == before
            print("Verified in-page script-to-shots-to-assets with exact approved revision, shot evidence and cancellation",
                  flush=True)
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def inspect_production_workspace(self):
            from shutil import copytree

            from src.production_project import ProductionProject

            def check_error(title, detail, **_options):
                raise AssertionError(f"{title}: {detail}")

            from src import windows_launcher

            examples = Path(windows_launcher.__file__).resolve().parents[1] / "Examples"
            folder = project_path.with_name("复核独立工作区")
            copytree(examples, folder)
            first, second = (folder / f"SB{index:02d}.cfproject" for index in (1, 2))
            initial = ProductionProject.open(first)
            second_bytes = second.read_bytes()
            navigation = next(walk(self, ttk.Notebook))

            def next_stage():
                work = visible_frame(self, "production_task_header")
                named(work, ttk.Button, "next_stage").invoke()

            def current_tool(frame):
                return visible_frame(self, frame)

            def select_page(page):
                navigation.select(page)
                self.update_idletasks()

            def field(scope, caption):
                label = next(widget for widget in walk(scope, ttk.Label) if widget.cget("text") == caption)
                return label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]

            with patch.object(messagebox, "showerror", side_effect=check_error):
                pick_production_project(self, "分镜拆分", first)
                shots = current_tool("production_panel")
                shots_page = navigation.select()
                table = next(widget for widget in walk(shots, ttk.Treeview) if widget.winfo_ismapped())
                assert tuple(table.get_children()) == tuple(shot.id for shot in initial.shots)
                assert not list(walk(self, tk.Toplevel))

                pick_production_project(self, "提示词生成", first)
                prompts = current_tool("production_panel")
                prompts_page = navigation.select()
                assert prompts is not shots and prompts_page != shots_page
                prompt_file = folder / "本地公共提示词.md"
                hint = "空信号站，右侧灯由暖色切换到稳定的绿灯。"
                prompt_file.write_text(f"场景/总体状态：{hint}\n公共限制：保持柜体和门的相对位置。", encoding="utf-8")
                with (patch.object(filedialog, "askopenfilename", return_value=str(prompt_file)),
                      patch.object(messagebox, "askyesno", return_value=True)):
                    click(prompts, "导入提示词 TXT / Markdown")
                prompt_box = named(prompts, tk.Text, "production_prompt")
                assert hint in prompt_box.get("1.0", "end-1c")

                pick_production_project(self, "资产图生成", second)
                other = current_tool("image_production_editor")
                other_page = navigation.select()
                assert other_page not in (shots_page, prompts_page)

                select_page(shots_page)
                table.selection_set(initial.shots[0].id)
                click(shots, "编辑镜头")
                edit = current_tool("production_subpanel")
                shot_text = named(edit, tk.Text, "production_shot_fields")
                raw = shot_text.get("1.0", "end-1c")
                key = "动作起止"
                action = "镜头观察关闭的门，右侧信号灯保持琥珀色。"
                changed = raw.replace(f"{key}：{initial.shots[0].fields[key]}", f"{key}：{action}", 1)
                assert changed != raw
                shot_text.delete("1.0", "end")
                shot_text.insert("1.0", changed)
                click(edit, "应用镜头更改")
                click(shots, "保存项目")
                assert ProductionProject.open(first).shots[0].fields[key] == action
                assert ProductionProject.open(first).prompt == initial.prompt

                pick_production_project(self, "批准图像", first)
                assets = current_tool("production_panel")
                local_ref = folder / "local-lamp-reference.png"
                Image.new("RGB", (640, 360), "steelblue").save(local_ref)
                with patch.object(filedialog, "askopenfilename", return_value=str(local_ref)):
                    click(assets, "导入批准 PNG")
                binding = current_tool("production_subpanel")
                field(binding, "处理理由").insert(0, "合成的灯号颜色对照样例")
                field(binding, "实际核图记录").insert(0, "已打开原图并核对色块与画幅")
                next(w for w in walk(binding, ttk.Checkbutton) if w.cget("text") == "仅用于来源比对").invoke()
                click(binding, "绑定批准图像")
                click(assets, "保存项目")

                select_page(prompts_page)
                assert hint in prompt_box.get("1.0", "end-1c"), "A sibling save replaced the unsaved prompt"
                click(prompts, "保存项目")
                saved = ProductionProject.open(first)
                assert saved.shots[0].fields[key] == action and saved.prompt["场景/总体状态"] == hint
                assert [shot.id for shot in saved.shots] == [shot.id for shot in initial.shots]
                assert saved.images[:-1] == initial.images
                assert saved.images[-1].reference_only and saved.images[-1].filename == local_ref.name
                assert saved.checked_image(first, saved.images[-1]).read_bytes() == local_ref.read_bytes()
                assert other.winfo_exists() and second.read_bytes() == second_bytes

                select_page(shots_page)
                close_current_task(self)
                pick_production_project(self, "分镜拆分", first)
                reopened = current_tool("production_panel")
                assert reopened is not shots
                next_stage()
                linked = current_tool("planning_editor")
                source = named(linked, tk.Text, "planning_source")
                assert source.get("1.0", "end-1c") == saved.sources[0].text
                assert source.cget("state") == "disabled"

                asset_file = folder / "本地资产清单.md"
                asset_file.write_text("场景：信号站\n道具：固定信号灯与左侧柜体", encoding="utf-8")
                with patch.object(filedialog, "askopenfilename", return_value=str(asset_file)):
                    named(linked, ttk.Button, "import_asset_report").invoke()
                next_stage()
                image_editor = current_tool("image_production_editor")
                assert (first.with_suffix(".assets") / "asset-analysis.md").read_text(encoding="utf-8") == (
                    asset_file.read_text(encoding="utf-8")
                )
                click(image_editor, "按图选择参考")
                library = current_tool("media_gallery")
                canvas = named(library, tk.Canvas, "media_cards")
                wait_for(self, lambda: canvas.find_all(), "The same-group gallery did not render its cards")
                canvas.event_generate("<Button-1>", x=45, y=40)
                named(library, ttk.Button, "media_preview").invoke()
                detail = current_tool("media_detail")
                assert not list(walk(self, tk.Toplevel)) and self.grab_current() is None
                named(detail, ttk.Button, "media_detail_close").invoke()
                visible_frame(self, "media_gallery")
                named(library, ttk.Button, "media_choose").invoke()
                assert current_tool("image_production_editor") is image_editor
                assert next(walk(image_editor, tk.Listbox)).curselection()

                next_stage()
                board = current_tool("image_production_editor")
                assert board is not image_editor and board is not other
                assert any(widget.get() == "故事板" for widget in walk(board, ttk.Combobox))
                next_stage()
                assert current_tool("production_panel") is prompts
                next_stage()
                delivery = current_tool("production_panel")
                assert delivery is not prompts
                click(delivery, "生成逐格复核预览")
                review = current_tool("production_subpanel")
                shot = next(widget for widget in walk(review, ttk.Combobox) if widget.winfo_ismapped())
                assert shot.get() == "SB01 / SB01-01"
                click(review, "返回")
                with patch.object(messagebox, "askyesno", return_value=True):
                    click(delivery, "确认本版画面")
                output = project_path.with_suffix(".zip")
                with patch.object(filedialog, "asksaveasfilename", return_value=str(output)):
                    click(delivery, "验收并导出 ZIP")

            with ZipFile(output) as packaged:
                assert packaged.testzip() is None
                names = packaged.namelist()
                assert "README.txt" in names and not any(local_ref.name in name for name in names)
                assert hint in packaged.read("SB01/SD2_prompt.txt").decode("utf-8-sig")
                text = packaged.read("SB01/SB01_shot_details.txt").decode("utf-8-sig")
                assert action in text
                for member in names:
                    if member.endswith(".png"):
                        with Image.open(BytesIO(packaged.read(member))) as image:
                            image.load()
                            assert image.width * 9 == image.height * 16
            assert second.read_bytes() == second_bytes
            print("Verified embedded handoffs, mixed-project tasks, local imports, sibling saves, in-page media selection "
                  "and real storyboard ZIP export", flush=True)
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def exercise_action_references(self, workbench):
            import webbrowser
            from urllib.parse import parse_qs, urlsplit
            from src.action_sequence import load_action_cards
            from src.production_project import ProductionProject

            title = "烟雨站台 · 摄影观察"
            url = "https://www.youtube.com/watch?v=CFtest12345"
            note = "等演员停住，再从全景切到反应近景。"

            def named(scope, kind, name):
                return next(widget for widget in walk(scope, kind) if widget.winfo_name() == name)

            def enter(field, value):
                field.delete(0, "end")
                field.insert(0, value)

            def fill_reference(library):
                form = named(library, tk.Toplevel, "reference_editor")
                for name, value in (("title", title), ("url", "https://example.com/clip"),
                                    ("start", "00:42"), ("end", "00:53")):
                    enter(named(form, ttk.Entry, name), value)
                named(form, tk.Text, "notes").insert("1.0", note)
                with patch.object(messagebox, "showerror") as error:
                    click(form, "保存参考")
                assert error.called and form.winfo_exists()
                enter(named(form, ttk.Entry, "url"), url)
                click(form, "保存参考")

            def inspect_library():
                library = next(w for w in walk(self, tk.Toplevel) if w.title() == "动作参考库")
                listing = named(library, ttk.Treeview, "references")
                self.after(60, lambda: fill_reference(library))
                click(library, "新增参考")
                assert not ProductionProject.open(project_path).action_cards
                keyword = named(library, ttk.Entry, "filter")
                for value, count in (("不会匹配的关键词", 0), ("反应近景", 1)):
                    enter(keyword, value)
                    self.update()
                    assert len(listing.get_children()) == count
                listing.selection_set(listing.get_children()[0])
                self.update()
                with patch.object(webbrowser, "open", return_value=True) as open_url:
                    click(library, "打开播放页")
                parts = urlsplit(open_url.call_args.args[0])
                query = parse_qs(parts.query)
                assert parts.hostname in ("www.youtube.com", "youtube.com")
                assert query.get("v") == ["CFtest12345"] and query.get("t") == ["42s"]
                click(library, "用笔记新建动作卡")

            self.after(60, inspect_library)
            click(workbench, "动作参考库")
            cards_path = project_path.with_suffix(".cards.json")
            with patch.object(filedialog, "asksaveasfilename", return_value=str(cards_path)):
                click(workbench, "导出动作卡")
            new_card, = load_action_cards(cards_path)
            assert new_card.title == "原创动作" and new_card.movement == note
            assert not any((new_card.reference, new_card.shot_id, new_card.route_notes))
            wire = cards_path.read_text(encoding="utf-8")
            assert all(value not in wire for value in (title, url, "00:42", "00:53"))
            assert not ProductionProject.open(project_path).action_cards
            with patch.object(messagebox, "askyesno", return_value=True):
                click(workbench, "删除")
            return title, url, note

        def add_notes_to_selected_action(self, workbench):
            from src.production_project import ProductionProject

            def inspect_library():
                library = next(w for w in walk(self, tk.Toplevel) if w.title() == "动作参考库")

                def edit_range():
                    form = next(walk(library, tk.Toplevel))
                    end = next(w for w in walk(form, ttk.Entry) if w.winfo_name() == "end")
                    end.delete(0, "end")
                    end.insert(0, "00:55")
                    click(form, "保存参考")

                self.after(60, edit_range)
                click(library, "编辑参考")
                reopened = ProductionProject.open(project_path)
                assert reopened.action_references[0]["end"] == "00:55" and not reopened.action_cards
                click(library, "把笔记加入动作卡")

            self.after(60, inspect_library)
            click(workbench, "动作参考库")

        def inspect_action_sequence(self):
            from src import action_sequence_dialog
            from src.production_project import ProductionProject

            project = ProductionProject("动作编排试用", "EP01", "SB01")
            source = project.import_source("场景一", "R1", "演员从门口走到桌边。")
            project.save(project_path)
            original = project_path.read_bytes()
            director_path = project_path.parent / "director-action" / "project.json"

            def receive_tracks(_parent, path, mode, callback, *, language):
                assert path.samefile(project_path), (path, project_path)
                assert (mode, language) == ("action", "zh")
                callback(director_path)
            gallery = show_page(self, PRODUCTION_TAB)
            click(gallery, "人物动作编排")
            picker = named(self, ttk.Frame, "action_project_picker")
            with patch.object(filedialog, "askopenfilename", return_value=str(project_path)):
                named(picker, ttk.Button, "open_project").invoke()

            def inspect_sequence():
                workbench = next((w for w in walk(self, ttk.Frame) if w.winfo_name() == "action_sequence_editor"), None)
                if workbench is None:
                    self.after(60, inspect_sequence)
                    return
                assert project_path.read_bytes() == original
                title, url, note = self.exercise_action_references(workbench)
                click(workbench, "加入选中预设")
                with patch.object(action_sequence_dialog, "open_director", side_effect=receive_tracks):
                    click(workbench, "打开内置 3D 导演台")
                cards = next(walk(workbench, ttk.Treeview))
                first, second = cards.get_children()
                assert cards.set(second, "actor") == "角色01"
                click(workbench, "上移")
                assert cards.get_children() == (second, first)

                def edit_route():
                    editor = named(self, tk.Toplevel, "action_card_editor")
                    start, action, end, notes = walk(editor, tk.Text)
                    assert not action.get("1.0", "end-1c") and "路线点" in notes.get("1.0", "end-1c")
                    start.insert("1.0", "演员在门口")
                    action.insert("1.0", "演员走到桌边")
                    end.insert("1.0", "演员在桌边停住")
                    click(editor, "确认")

                self.after(60, edit_route)
                click(workbench, "编辑")
                self.add_notes_to_selected_action(workbench)
                tabs = next(walk(workbench, ttk.Notebook))
                tabs.select(1)
                self.update()
                board_page = tabs.nametowidget(tabs.select())
                for size in (12, 15):
                    radio = next(w for w in walk(board_page, ttk.Radiobutton) if w.cget("text") == f"{size} 格")
                    radio.invoke()
                    assert len(list(walk(board_page, tk.Frame))) == size
                    assert any(note in w.cget("text") for w in walk(board_page, ttk.Label))
                tabs.select(0)
                cards.selection_set(second)

                def confirm():
                    handoff = next(w for w in walk(self, tk.Toplevel) if w.title() == "带入正式分镜")
                    entry = next(w for w in walk(handoff, ttk.Entry) if not isinstance(w, ttk.Combobox))
                    entry.insert(0, "场景一 · 进门")
                    click(handoff, "确认带入")

                self.after(60, confirm)
                click(workbench, "带入正式分镜")
                saved = ProductionProject.open(project_path)
                assert len(saved.shots) == 1 and saved.shots[0].source == source.id
                assert saved.action_cards[0]["shot_id"] == saved.shots[0].id
                assert "演员走到桌边" in saved.shots[0].fields["动作起止"]
                assert "路线点" not in saved.shots[0].fields["动作起止"]
                assert note in saved.shots[0].fields["动作起止"]
                card_text = json.dumps(saved.action_cards, ensure_ascii=False)
                shot_text = json.dumps(saved.shots[0].fields, ensure_ascii=False)
                assert note in card_text and all(value not in card_text + shot_text for value in (title, url))
                assert len(saved.action_references) == 1 and saved.action_references[0]["title"] == title
                print("Verified new cards and notes-only handoff from saved, filtered and timed video references", flush=True)
                print("Verified action card presets, built-in director handoff, reordering, panel counts and formal shot handoff", flush=True)
                print("COMICFLOW_GUI_OK", flush=True)
                self.after_idle(self.destroy)

            self.after(60, inspect_sequence)

        def inspect_workbench_bridges(self):
            from src import action_sequence_dialog
            from src.production_project import ProductionProject, Shot
            from src.production_rules import CHINESE, ENGLISH

            root = project_path.parent
            origin = root / "发起-SB03.cfproject"
            sibling = root / "另一组-SB04.cfproject"
            decoy = root / "同名-SB03.cfproject"

            def make_project(path, episode, group, rules, text):
                project = ProductionProject("同名制作项", episode, group, rules=rules)
                source = project.import_source("批准源稿", "R1", text)
                project.shots = [Shot(source=source.id, anchor=segment) for segment in text.splitlines()]
                project.save(path)
                return project

            first = make_project(origin, "EP03", "SB03", ENGLISH, "Mira enters.\nMira checks the door.")
            make_project(decoy, "EP03", "SB03", ENGLISH, "Decoy group must stay separate.")
            make_project(sibling, "EP03", "SB04", CHINESE, "演员关上旁边的门。")
            sibling_bytes, decoy_bytes = sibling.read_bytes(), decoy.read_bytes()
            navigation = next(walk(self, ttk.Notebook))

            def open_actions(path):
                click(show_page(self, PRODUCTION_TAB), "人物动作编排")
                picker = visible_frame(self, "action_project_picker")
                with patch.object(filedialog, "askopenfilename", return_value=str(path)):
                    named(picker, ttk.Button, "open_project").invoke()
                return visible_frame(self, "action_sequence_editor")

            action = open_actions(origin)
            origin_tab = navigation.select()
            returns = []

            def start_director(_parent, path, kind, callback, *, language):
                assert path.samefile(origin) and kind == "action" and language == "zh"
                returns.append(callback)

            with patch.object(action_sequence_dialog, "open_director", side_effect=start_director):
                click(action, "打开内置 3D 导演台")
                alternate = open_actions(sibling)
                assert len(returns) == 1 and alternate is not action
                returns[0](root / "director-action" / "project.json")
                assert alternate.winfo_ismapped() and not next(walk(alternate, ttk.Treeview)).get_children()
            navigation.select(origin_tab)
            assert len(next(walk(action, ttk.Treeview)).get_children()) == 1
            click(action, "保存动作编排")
            assert ProductionProject.open(origin).action_cards[0]["actor"] == "角色01"

            pick_production_project(self, "分镜拆分", sibling)
            chinese = visible_frame(self, "production_panel")
            assert any("中文影片制作" in widget.getvar(variable) for widget in walk(chinese, ttk.Label)
                       if (variable := widget.cget("textvariable")))

            reviewed = root / "已交付的-SB03.zip"
            validator_path = root / "返修定位-校验器.py"
            validator_path.write_text(
                'print("WARNING: SB03/SB03_shot_details.txt: shot SB03-02: repair fixture")\n'
                'print("RESULT: 0 error(s), 1 warning(s)")\n', encoding="utf-8",
            )
            rows = "\n".join(f"- SB03-{i:02d} | {shot.id} | R1 | line {i}"
                             for i, shot in enumerate(first.shots, 1))
            with ZipFile(reviewed, "w") as package:
                package.writestr("README.txt", f"同名制作项 · EP03\n组号：SB03\n镜头与来源：\n{rows}\n")
                package.writestr("SB03/SB03_shot_details.txt", "分镜 SB03-01\n动作：开门\n分镜 SB03-02\n动作：核对门。")
                package.writestr("SB03/SD2_prompt.txt", "分镜编号：SB03-01\n动作：开门\n分镜编号：SB03-02\n动作：核对门。")
            review = show_page(self, REVIEW_TAB)
            archive_entry, validator, *_ = walk(review, ttk.Entry)
            for field, value in ((archive_entry, reviewed), (validator, validator_path)):
                field.delete(0, "end")
                field.insert(0, str(value))
            click(review, "开始验收")
            issues = next(walk(review, ttk.Treeview))
            wait_for(self, issues.get_children, "Could not validate the ZIP and select a production issue")
            issue = next(iid for iid in issues.get_children() if issues.item(iid, "values")[2] == "SB03-02")
            issues.selection_set(issue)
            issues.event_generate("<<TreeviewSelect>>")
            with patch.object(filedialog, "askopenfilename",
                              side_effect=AssertionError("A known exact shot should not need manual project selection")):
                named(review, ttk.Button, "return_to_production", mapped=True).invoke()
                matched = visible_frame(self, "production_panel")
            table = next(w for w in walk(matched, ttk.Treeview) if w.winfo_ismapped())
            assert table.selection() == (first.shots[1].id,)
            assert any("英文影片制作" in widget.getvar(variable) for widget in walk(matched, ttk.Label)
                       if (variable := widget.cget("textvariable")))
            assert sibling.read_bytes() == sibling_bytes and decoy.read_bytes() == decoy_bytes
            print("Verified isolated Chinese/English groups, director returns to SB03 and ZIP repair locates its exact shot",
                  flush=True)
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def inspect_job_recovery(self):
            from threading import Event

            from src import image_production_dialog, vision_dialog
            from src.image_api import ImageReply
            from src.production_project import ProductionProject
            from src.production_rules import CHINESE, ENGLISH

            source = project_path.with_name("请求发起-SB03.cfproject")
            other = project_path.with_name("并行项目-SB04.cfproject")
            ProductionProject("生图发起组", "EP03", "SB03", rules=ENGLISH).save(source)
            ProductionProject("另一个组", "EP03", "SB04", rules=CHINESE).save(other)
            other_bytes = other.read_bytes()
            asset = BytesIO()
            Image.new("RGB", (640, 360), "steelblue").save(asset, format="PNG")
            release, sent = Event(), Event()
            requests = []

            def submit(_settings, request):
                requests.append(request)
                sent.set()
                assert release.wait(8), "UI blocked while the offline image worker was running"
                return ImageReply((asset.getvalue(),), request_id="smoke-detached-group-image")

            pick_production_project(self, "资产图生成", source)
            editor = visible_frame(self, "image_production_editor")
            navigation = next(walk(self, ttk.Notebook))
            origin_tab = navigation.select()
            label = next(w for w in walk(editor, ttk.Label) if w.cget("text") == "API Key")
            key = label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]
            key.insert(0, "synthetic-key-for-local-test")
            named(visible_frame(self, "production_task_header"), ttk.Button, "open_task_api", mapped=True).invoke()
            self.update()
            api = page_at(self, API_TAB)
            assert api.winfo_ismapped()
            named(api, ttk.Button, "api_return", mapped=True).invoke()
            self.update_idletasks()
            assert navigation.select() == origin_tab and editor.winfo_ismapped()
            assert key.get() == "synthetic-key-for-local-test"

            def reopen_job(source_name, expected_editor):
                page = show_page(self, REVIEW_TAB)
                named(page, ttk.Button, "workbench_jobs", mapped=True).invoke()
                center = visible_frame(self, "jobs_center")
                registry = named(center, ttk.Treeview, "registered_jobs")
                wait_for(self, registry.get_children, "The running job was absent from the workbench registry")
                row = next(iid for iid in registry.get_children() if source_name in str(registry.item(iid, "values")))
                registry.selection_set(row)
                registry.event_generate("<<TreeviewSelect>>")
                named(center, ttk.Button, "resume_job", mapped=True).invoke()
                return visible_frame(self, expected_editor)

            with (patch.object(image_production_dialog, "submit_image", side_effect=submit),
                  patch.object(messagebox, "askyesno", return_value=True)):
                try:
                    click(editor, "确认并提交生图")
                    wait_for(self, sent.is_set, "The offline image job did not start")
                    pending, = ProductionProject.open(source).image_jobs
                    assert pending["status"] == "submitting"

                    pick_production_project(self, "资产图生成", other)
                    alternate = visible_frame(self, "image_production_editor")
                    assert alternate is not editor and navigation.select() != origin_tab
                    navigation.select(origin_tab)
                    close_current_task(self)
                    assert not editor.winfo_exists() and alternate.winfo_ismapped() and not release.is_set()

                    recovered = reopen_job("SB03", "image_production_editor")
                    history = next(walk(recovered, ttk.Notebook))
                    assert recovered is not alternate and history.index(history.select()) == 1
                    history.select(0)
                    send = next(button for button in walk(recovered, ttk.Button)
                                if button.cget("text") == "确认并提交生图")
                    send.invoke()
                    history.select(1)
                    assert len(requests) == 1
                finally:
                    release.set()

                def completed():
                    job, = ProductionProject.open(source).image_jobs
                    return job if job["status"] == "ready" and any(
                        job["request_id"] in widget.get("1.0", "end-1c") for widget in walk(recovered, tk.Text)
                    ) else None

                result = wait_for(self, completed, "The detached job did not persist its image candidate")
            assert len(requests) == 1 and result["id"] == pending["id"] and len(result["outputs"]) == 1
            assert result["request_id"] == "smoke-detached-group-image"
            assert any(result["request_id"] in widget.get("1.0", "end-1c") for widget in walk(recovered, tk.Text))
            assert other.read_bytes() == other_bytes
            assert b"synthetic-key-for-local-test" not in source.read_bytes()

            review = show_page(self, REVIEW_TAB)
            click(review, "开始验收")
            selector = next(walk(review, ttk.Combobox))
            wait_for(self, lambda: "SB01/storyboard_2panel.png" in selector["values"], "Fixture image was not indexed")
            selector.set("SB01/storyboard_2panel.png")
            selector.event_generate("<<ComboboxSelected>>")
            click(review, "AI 辅助看图")
            vision = visible_frame(self, "vision_review_editor")
            named(vision, ttk.Entry, "vision_key").insert(0, "isolated-vision-key")
            named(vision, ttk.Entry, "vision_model").insert(0, "offline-test-model")
            named(vision, ttk.Entry, "vision_focus").insert(0, "只核对窗口和肩膀位置")
            vision_calls = []
            sent.clear()
            release.clear()

            def analyze(_settings, image, *, focus, rules):
                with Image.open(BytesIO(image)) as picture:
                    assert picture.size == (640, 360)
                assert focus == "只核对窗口和肩膀位置" and rules == ENGLISH
                vision_calls.append(focus)
                sent.set()
                assert release.wait(8), "UI blocked while the offline review worker was running"
                return "离线审图候选：保留原图构图"

            with (patch.object(vision_dialog, "review_image", side_effect=analyze),
                  patch.object(messagebox, "askyesno", return_value=True)):
                try:
                    named(vision, ttk.Button, "vision_send").invoke()
                    wait_for(self, sent.is_set, "The offline vision request did not start")
                    close_current_task(self)
                    assert not vision.winfo_exists()
                    recovered_vision = reopen_job("storyboard_2panel.png", "vision_review_editor")
                    named(recovered_vision, ttk.Button, "vision_send").invoke()
                    assert len(vision_calls) == 1
                finally:
                    release.set()
                output = named(recovered_vision, tk.Text, "vision_output")
                wait_for(self, lambda: "离线审图候选" in output.get("1.0", "end-1c"),
                         "The reopened vision workspace did not restore its result")
            assert len(vision_calls) == 1
            print("Verified detached image and vision requests, task recovery and one submission for each original input", flush=True)
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def inspect_task_navigation(self):
            from src.production_project import ProductionProject
            from src.production_rules import CHINESE, ENGLISH

            nav = named(self, ttk.Frame, "workbench_nav")
            initial_tabs = tuple(named(nav, ttk.Button, f"primary_{index}") for index in range(5))
            assert all(not button.winfo_children() for button in initial_tabs)
            assert all(button.cget("text") for button in initial_tabs)
            first = project_path.parent / "甲组" / "SB03.cfproject"
            second = first.with_name("SB04.cfproject")
            same_group = project_path.parent / "乙组" / first.name
            first.parent.mkdir()
            same_group.parent.mkdir()
            paths = (
                (first, "庭院制作", "SB03", ENGLISH),
                (second, "走廊制作", "SB04", CHINESE),
                (same_group, "另一项目", "SB03", ENGLISH),
                *((first.with_name(f"SB{number:02d}.cfproject"), f"视窗测试 {number}", f"SB{number:02d}", ENGLISH)
                  for number in range(5, 11)),
            )
            for path, name, group, rules in paths:
                ProductionProject(name, "EP01", group, rules=rules).save(path)

            def visible_editor():
                return next((w for w in walk(self, ttk.Frame)
                             if w.winfo_name() == "action_sequence_editor" and w.winfo_ismapped()), None)

            def task_controls():
                return {w.winfo_name(): w for w in walk(nav, ttk.Frame)
                        if w.winfo_name().startswith("task_") and
                        any(child.winfo_name() == "select" for child in w.winfo_children())}

            def buttons_for(name):
                frame = task_controls()[name]
                return named(frame, ttk.Button, "select"), named(frame, ttk.Button, "close")

            def open_task(path):
                initial_tabs[PRODUCTION_TAB].invoke()
                before = task_controls()
                click(page_at(self, PRODUCTION_TAB), "人物动作编排")
                self.update_idletasks()
                picker = named(self, ttk.Frame, "action_project_picker", mapped=True)
                assert not list(walk(self, tk.Toplevel))
                with patch.object(filedialog, "askopenfilename", return_value=str(path)):
                    named(picker, ttk.Button, "open_project").invoke()
                editor = wait_for(self, visible_editor, f"{path} did not open in a task page")
                assert not list(walk(self, tk.Toplevel)) and not self.grab_current()
                opened = task_controls().keys() - before.keys()
                return editor, opened

            def cards(editor):
                return named(editor, ttk.Treeview, "action_cards")

            def titles(editor):
                table = cards(editor)
                return [table.set(row, "title") for row in table.get_children()]

            def draft(editor, title, note):
                def fill():
                    form = named(self, tk.Toplevel, "action_card_editor", mapped=True)
                    named(form, ttk.Entry, "title").insert(0, title)
                    named(form, tk.Text, "movement").insert("1.0", note)
                    click(form, "确认")

                self.after(60, fill)
                click(editor, "新建")

            def preview_images_ready(gallery):
                for part in ("start", "beat", "end"):
                    value = named(gallery, ttk.Button, f"frame_{part}").cget("image")
                    photos = self.tk.splitlist(value)
                    if not photos or int(self.tk.call("image", "width", photos[0])) <= 10:
                        return False
                return True

            first_editor, (first_tab,) = open_task(first)
            draft(first_editor, "甲组保留的备注", "先等对方望过来，然后抬手。")
            named(first_editor, ttk.Button, "browse_action_cards").invoke()
            gallery = named(first_editor, ttk.Frame, "action_presets")
            category = named(gallery, ttk.Combobox, "preset_category")
            category.current(tuple(category.cget("values")).index("日常与表演"))
            category.event_generate("<<ComboboxSelected>>")
            named(gallery, ttk.Button, "cover_performance-03").invoke()
            wait_for(self, lambda: preview_images_ready(gallery), "Selected card did not render all three preview frames")
            named(gallery, ttk.Button, "frame_beat").invoke()
            self.update_idletasks()
            picture = named(gallery, ttk.Frame, "enlarged_action_frame", mapped=True)
            assert not list(walk(self, tk.Toplevel)) and not self.grab_current()

            initial_tabs[REVIEW_TAB].invoke()
            self.update_idletasks()
            assert not picture.winfo_ismapped() and page_at(self, REVIEW_TAB).winfo_ismapped()
            buttons_for(first_tab)[0].invoke()
            self.update_idletasks()
            assert picture.winfo_ismapped()
            click(self, "中文 / English")
            self.update_idletasks()
            assert picture.winfo_ismapped() and initial_tabs[REVIEW_TAB].cget("text") == "Inspection & validation"
            assert "Action sequencing" in buttons_for(first_tab)[0].cget("text")
            click(self, "中文 / English")
            named(picture, ttk.Button, "back_to_presets").invoke()
            assert named(gallery, ttk.Label, "preset_title").cget("text") == "递出后松手"
            named(gallery, ttk.Button, "add_preset").invoke()
            assert titles(first_editor) == ["甲组保留的备注", "递出后松手"]
            assert not ProductionProject.open(first).action_cards

            second_editor, (second_tab,) = open_task(second)
            draft(second_editor, "乙组待丢弃的备注", "站到门内。")
            duplicate, opened = open_task(first)
            assert duplicate is first_editor and not opened
            assert titles(duplicate) == ["甲组保留的备注", "递出后松手"]
            assert titles(second_editor) == ["乙组待丢弃的备注"]
            alternate, (alternate_tab,) = open_task(same_group)
            assert titles(alternate) == [] and alternate is not first_editor
            buttons_for(alternate_tab)[1].invoke()
            assert not alternate.winfo_exists() and len(task_controls()) == 2

            def close_with(name, decision):
                buttons_for(name)[1].invoke()
                self.update_idletasks()
                confirm = named(self, tk.Frame, "task_close_confirmation", mapped=True)
                assert not list(walk(self, tk.Toplevel)) and not self.grab_current()
                named(confirm, ttk.Button, decision).invoke()
                self.update_idletasks()

            close_with(first_tab, "keep_editing")
            assert first_editor.winfo_exists() and titles(first_editor)[0] == "甲组保留的备注"
            assert not ProductionProject.open(first).action_cards
            updated = ProductionProject.open(first)
            approved = updated.import_source("另一编辑器已批准的段落", "R2", "A character puts down a letter.")
            updated.save(first)
            close_with(first_tab, "save_and_close")
            assert not first_editor.winfo_exists()
            saved = ProductionProject.open(first)
            assert saved.action_cards[0]["movement"] == "先等对方望过来，然后抬手。"
            assert saved.action_cards[1]["preset_id"] == "performance-03" and saved.rules == ENGLISH
            assert approved in saved.sources
            assert titles(second_editor) == ["乙组待丢弃的备注"]
            close_with(second_tab, "discard_changes")
            assert not second_editor.winfo_exists()
            discarded = ProductionProject.open(second)
            assert not discarded.action_cards and discarded.rules == CHINESE
            assert not ProductionProject.open(same_group).action_cards

            reopened, _ = open_task(first)
            assert titles(reopened) == ["甲组保留的备注", "递出后松手"]
            initial_tabs[PRODUCTION_TAB].invoke()
            with patch.object(filedialog, "askopenfilename", return_value=str(first)):
                click(page_at(self, PRODUCTION_TAB), "继续已有项目")
                self.update()
            production = next(walk(self, tk.Toplevel))
            next(walk(production, ttk.Notebook)).select(1)
            click(production, "人物动作编排")
            assert wait_for(self, visible_editor, "The shot-list action button did not return to the existing task") is reopened
            assert not production.winfo_exists() and len(task_controls()) == 1
            self.geometry("900x700")
            for path, *_ in paths[3:]:
                open_task(path)
            self.update_idletasks()
            overflow = named(nav, ttk.Menubutton, "open_tasks", mapped=True)
            menu = overflow.nametowidget(overflow.cget("menu"))
            index = next(index for index in range(menu.index("end") + 1)
                         if menu.type(index) == "command" and "SB03" in menu.entrycget(index, "label"))
            menu.invoke(index)
            self.update_idletasks()
            assert visible_editor() is reopened and all(button.winfo_ismapped() for button in initial_tabs)
            click(self, "中文 / English")
            self.update_idletasks()
            right = self.winfo_rootx() + self.winfo_width()
            assert all(button.winfo_rootx() + button.winfo_width() <= right and
                       button.winfo_width() >= button.winfo_reqwidth() for button in initial_tabs)
            click(self, "中文 / English")
            print("Verified fixed pages, independent groups and projects, duplicate reuse, retained gallery preview, save/discard/cancel and narrow task navigation", flush=True)
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def inspect_dialogue_blocking(self):
            from dataclasses import replace
            from hashlib import sha256

            from src import dialogue_blocking
            from src.production_project import ProductionProject, Shot

            role_names = {"A": "岚", "B": "尧", "C": "澄"}
            cast = tuple(role_names.values())
            lines = ("Keep the side door open.", "I'll wait by the window.", "Someone is coming.")
            project = ProductionProject("对话样例", "EP04", "SB03")
            source = project.import_source("窗边对话", "R1", "\n".join(lines))
            project.import_dialogue(source, json.dumps([
                {"id": f"D{index}", "speaker": speaker, "text": line}
                for index, (speaker, line) in enumerate(zip((cast[1], cast[0], cast[2]), lines), 1)
            ], ensure_ascii=False))
            camera_fields = {"景别", "机位/角度", "机位空间", "人物站位"}
            project.shots = [
                Shot(source=source.id, anchor=f"窗边第 {index} 句", scene="门厅", plate_note="固定窗框不能移动",
                     fields={**dict.fromkeys(camera_fields, "原机位记录"), "画面/事件": "说话时保持空间",
                             "动作起止": "抬眼停顿", "声音": "门外脚步声"},
                     dialogue=[(f"D{index}", 0, len(line))])
                for index, line in enumerate(lines, 1)
            ]
            project.save(project_path)
            before_bytes = project_path.read_bytes()
            before = ProductionProject.open(project_path)
            card_ids = ("dialogue-01", "dialogue-02", "dialogue-03")
            image_folder = Path(dialogue_blocking.__file__).resolve().parents[1] / "assets" / "dialogue_previews"
            checksums = set()
            for identity in card_ids:
                for variant in ("map", "1", "2"):
                    image_path = image_folder / f"{identity}-{variant}.webp"
                    checksums.add(sha256(image_path.read_bytes()).digest())
                    with Image.open(image_path) as illustration:
                        illustration.load()
                        assert illustration.format == "WEBP" and illustration.width * 9 == illustration.height * 16
            assert len(checksums) == 9

            def open_editor():
                production = show_page(self, PRODUCTION_TAB)
                click(production, "人物动作编排")
                self.update_idletasks()
                picker = named(self, ttk.Frame, "action_project_picker", mapped=True)
                with patch.object(filedialog, "askopenfilename", return_value=str(project_path)):
                    named(picker, ttk.Button, "open_project").invoke()
                return wait_for(self, lambda: next((widget for widget in walk(self, ttk.Frame)
                                if widget.winfo_name() == "action_sequence_editor" and widget.winfo_ismapped()), None),
                                "The dialogue example project did not open")

            def open_library(editor):
                named(editor, ttk.Button, "browse_action_cards", mapped=True).invoke()
                self.update_idletasks()
                named(editor, ttk.Button, "dialogue_card_library", mapped=True).invoke()
                self.update_idletasks()
                return named(editor, ttk.Frame, "dialogue_cards", mapped=True)

            def photo_ready(widget):
                photos = self.tk.splitlist(widget.cget("image"))
                return any(int(self.tk.call("image", "width", photo)) > 10 for photo in photos)

            def choose(library, identity, view):
                named(library, ttk.Button, f"card_{identity}").invoke()
                named(library, ttk.Button, f"dialogue_show_{view}").invoke()
                wait_for(self, lambda: photo_ready(named(library, ttk.Label, "dialogue_image", mapped=True)),
                         f"{identity}-{view} did not show its decoded image")

            def map_roles(library, identities):
                widgets = {}
                for role in identities:
                    field = named(library, ttk.Combobox, f"dialogue_role_{role.lower()}", mapped=True)
                    value = role_names[role]
                    assert value in field.cget("values"), (role, field.cget("values"))
                    field.set(value)
                    field.event_generate("<<ComboboxSelected>>")
                    widgets[role] = field
                return widgets

            def preview_and_apply(library, target):
                control = named(library, ttk.Combobox, "dialogue_target", mapped=True)
                control.current(target)
                control.event_generate("<<ComboboxSelected>>")
                on_disk = project_path.read_bytes()
                named(library, ttk.Button, "dialogue_apply", mapped=True).invoke()
                self.update_idletasks()
                assert project_path.read_bytes() == on_disk, "Preview wrote to the approved project"
                assert not self.grab_current() and not list(walk(self, tk.Toplevel))
                changes = named(library, ttk.Label, "dialogue_changes", mapped=True).cget("text")
                assert camera_fields <= {line.split("  ", 1)[0] for line in changes.splitlines()}
                if target:
                    assert "对白" in changes
                named(library, ttk.Button, "dialogue_confirm", mapped=True).invoke()
                self.update_idletasks()

            editor = open_editor()
            library = open_library(editor)
            for identity in card_ids:
                for view in ("map", 1, 2):
                    choose(library, identity, view)
            roles = map_roles(library, "ABC")
            named(library, ttk.Button, "dialogue_enlarge", mapped=True).invoke()
            self.update_idletasks()
            assert named(library, ttk.Button, "dialogue_restore", mapped=True)
            assert not self.grab_current() and not list(walk(self, tk.Toplevel))
            show_page(self, REVIEW_TAB)
            task = next(widget for widget in walk(self, ttk.Button)
                        if widget.winfo_name() == "select" and "SB03" in widget.cget("text"))
            task.invoke()
            self.update_idletasks()
            assert named(library, ttk.Button, "dialogue_restore", mapped=True)
            click(self, "中文 / English")
            self.update_idletasks()
            assert self.title() == APP_NAME_EN and named(library, ttk.Button, "dialogue_restore", mapped=True)
            named(library, ttk.Button, "dialogue_restore", mapped=True).invoke()
            click(self, "中文 / English")
            assert {role: widget.get() for role, widget in roles.items()} == role_names
            roles["C"].set(role_names["B"])
            named(library, ttk.Button, "dialogue_apply", mapped=True).invoke()
            self.update_idletasks()
            assert named(library, ttk.Label, "dialogue_error", mapped=True).cget("text")
            assert not named(library, ttk.Button, "dialogue_confirm").winfo_ismapped()
            roles["C"].set(role_names["C"])
            preview_and_apply(library, 0)
            assert project_path.read_bytes() == before_bytes, "Adding a dialogue card saved the draft unexpectedly"
            table = named(editor, ttk.Treeview, "action_cards", mapped=True)
            assert len(table.get_children()) == 1
            assert all(name in table.set(table.get_children()[0], "actor") for name in cast)

            for view in (1, 2):
                library = open_library(editor)
                choose(library, "dialogue-02", view)
                map_roles(library, "AB")
                preview_and_apply(library, view)
            edited = ProductionProject.open(project_path)
            assert not edited.action_cards
            assert edited.lines == before.lines and edited.sources == before.sources
            assert len(edited.shots) == len(before.shots)
            assert edited.shots[-1] == before.shots[-1]
            for index, (original, changed) in enumerate(zip(before.shots, edited.shots), 1):
                if index == 3:
                    continue
                expected = dialogue_blocking.dialogue_fields(
                    "dialogue-02", index, {"A": "岚", "B": "尧"}, english=True,
                )
                assert set(expected) == camera_fields
                assert changed == replace(original, fields={**original.fields, **expected})
            assert edited.shots[0].fields["机位空间"] != edited.shots[1].fields["机位空间"]

            click(editor, "保存动作编排")
            close = next(widget for widget in walk(task.master, ttk.Button) if widget.winfo_name() == "close")
            close.invoke()
            assert not editor.winfo_exists()
            editor = open_editor()
            table = named(editor, ttk.Treeview, "action_cards", mapped=True)
            (card,) = table.get_children()
            table.selection_set(card)
            table.event_generate("<<TreeviewSelect>>")
            card_preview = named(editor, ttk.Label, "selected_action_preview")
            wait_for(self, lambda: photo_ready(card_preview), "Saved dialogue card did not restore its camera illustration")
            snapshot = project_path.read_bytes()
            with patch.object(messagebox, "showerror") as error:
                click(editor, "带入正式分镜")
                assert error.call_count == 1 and "对话与站位" in error.call_args.args[1]
            assert project_path.read_bytes() == snapshot, "Generic action handoff rewrote a dialogue camera reference"
            saved = ProductionProject.open(project_path)
            assert saved.action_cards[0]["preset_id"] == "dialogueview-06"
            assert all(name in saved.action_cards[0]["actor"] for name in cast)
            assert saved.lines == before.lines and saved.shots == edited.shots
            print("Verified three dialogue cards and nine offline images, in-page preview, cast mapping, "
                  "draft reopening and formal camera-only update with approved dialogue intact", flush=True)
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def inspect_release_notes(self):
            from tkinter.scrolledtext import ScrolledText

            version = next(w for w in walk(self, ttk.Button) if w.winfo_name() == "release_version")
            help_control = next(w for w in walk(self, ttk.Menubutton) if w.winfo_name() == "workbench_help")
            menu = self.nametowidget(help_control.cget("menu"))
            self.geometry("900x700")
            self.update_idletasks()
            for control in (version, help_control):
                assert control.winfo_ismapped()
                assert self.winfo_rootx() <= control.winfo_rootx()
                assert control.winfo_rootx() + control.winfo_width() <= self.winfo_rootx() + self.winfo_width()
            assert self.title() == APP_NAME_ZH and menu.entrycget(0, "label") == "更新日志"
            assert version.cget("text") == f"v{VERSION}"
            version.invoke()
            dialog = self.nametowidget("release_notes")
            notes = next(walk(dialog, ScrolledText))
            assert dialog.title() == "更新日志" and str(notes.cget("state")) == "disabled"
            content = notes.get("1.0", "end")
            assert f"{VERSION} · " in content and "漫剧镜序制片台" in content
            assert "The new name appears" not in content

            click(self, "中文 / English")
            assert self.title() == APP_NAME_EN and help_control.cget("text") == "Help"
            assert menu.entrycget(0, "label") == "Changelog" and dialog.title() == "Changelog"
            content = notes.get("1.0", "end")
            assert "The new name appears" in content and "软件定名为" not in content
            click(dialog, "Close")
            assert not dialog.winfo_exists()
            menu.invoke(0)
            latest = self.nametowidget("release_notes")
            assert latest.title() == "Changelog"
            click(latest, "Close")
            click(self, "中文 / English")
            print(f"Verified branded header and offline bilingual changelog at {mode}", flush=True)

        def inspect_a_workbench(self):
            from tkinter.scrolledtext import ScrolledText

            from src import batch_runner
            from src.batch_runner import BatchQueue
            from src.batch_workspace import BatchWorkspace
            from src.image_api import IMAGE_PROVIDERS, ImageReply, ImageSettings
            from src.production_project import ProductionProject
            from src.production_rules import ENGLISH

            path = project_path.with_suffix(".cfbatch")
            workspace = BatchWorkspace.create(path, "Harbor pilot", ENGLISH)
            script = "\n".join(["INT. HARBOR STATION - NIGHT", *(
                f"The lighthouse lamp pulses brightly over position {index}." for index in range(1, 19)
            )])
            workspace.add_episode("EP04", "Fog at the pier", script)
            workspace.approve_plan("EP04")
            group_path = workspace.group_path("EP04", "SB02")
            queue = BatchQueue(workspace)
            queue.enqueue_asset("EP04", "SB02", "道具", "Harbor signal", "lit", "PNG test fixture")
            png = BytesIO()
            Image.new("RGB", (256, 144), "#946342").save(png, format="PNG")
            provider = "OpenAI GPT Image"
            config = IMAGE_PROVIDERS[provider]
            model = ImageSettings(provider, config.base, config.model, "offline-only-test-key")
            with patch.object(batch_runner, "submit_image", return_value=ImageReply((png.getvalue(),))):
                assert queue.run(image_settings=model, max_requests=1) == {"review": 1}
            group = ProductionProject.open(group_path)
            assert group.image_jobs[0]["outputs"] and not group.images and group.impacts()

            def named(scope, kind, name):
                return next(control for control in walk(scope, kind) if control.winfo_name() == name)

            def after_ready(test, done, reason):
                deadline = time.monotonic() + 5

                def check():
                    if value := test():
                        done(value)
                    elif time.monotonic() < deadline:
                        self.after(40, check)
                    else:
                        fail(reason)

                self.after(40, check)

            def measured_bounds(window, button):
                left, top = window.winfo_rootx(), window.winfo_rooty()
                right, bottom = left + window.winfo_width(), top + window.winfo_height()
                caption = button.cget("text")
                x, y = button.winfo_rootx(), button.winfo_rooty()
                size = (button.winfo_width(), button.winfo_height())
                requested = (button.winfo_reqwidth(), button.winfo_reqheight())
                ancestry = []
                current = button
                while current is not window:
                    ancestry.append((current.winfo_name(), current.winfo_manager(), current.winfo_ismapped(),
                                     current.winfo_width(), current.winfo_height()))
                    current = current.master
                details = (caption, window.winfo_geometry(), (x - left, y - top), size, requested, ancestry)
                assert button.winfo_ismapped(), ("control not visible", details)
                assert left <= x and x + size[0] <= right, ("horizontal clipping", details)
                assert top <= y and y + size[1] <= bottom, ("vertical clipping", details)
                assert size[0] >= requested[0] and size[1] >= requested[1], ("label may be clipped", details)
                return x, y

            def measure(window, buttons):
                rows = {}
                for button in buttons:
                    _, y = measured_bounds(window, button)
                    rows.setdefault(y, []).append(button)
                for controls in rows.values():
                    assert len({control.winfo_height() for control in controls}) == 1
                    coordinates = sorted((control.winfo_rootx(), control.winfo_width()) for control in controls)
                    assert all(x + width <= next_x for (x, width), (next_x, _) in zip(coordinates, coordinates[1:]))

            def layout(window, get_buttons, after):
                narrow, height = window.minsize()
                sizes = iter(dict.fromkeys(((max(narrow, 1160), max(height, 780)), (narrow, height))))

                def apply_size():
                    size = next(sizes, None)
                    if size is None:
                        after()
                        return
                    window.geometry(f"{size[0]}x{size[1]}")
                    window.after(90, verify_size)

                def verify_size():
                    window.update_idletasks()
                    measure(window, get_buttons())
                    apply_size()

                apply_size()

            step_names = ("import", "plan", "assets", "queue", "delivery")

            def start_language(english):
                production = show_page(self, PRODUCTION_TAB)

                def home_steps():
                    return [named(production, ttk.Button, "a_home_" + name) for name in step_names]

                home_delivery = home_steps()[-1]
                assert ("Review & delivery" if english else "验收交付") in home_delivery.cget("text")
                layout(self, home_steps, lambda: launch(english, home_delivery, production))

            def launch(english, home_delivery, production):
                home_delivery.invoke()
                panel = visible_frame(self, "batch_workspace")
                assert not self.grab_current()
                tabs = next(walk(panel, ttk.Notebook))
                assert tabs.index(tabs.select()) == 3, "home delivery route must select the real delivery page"
                if not english:
                    with patch.object(filedialog, "askopenfilename", return_value=str(path)):
                        click(panel, "打开批次")

                def loaded():
                    groups = named(panel, ttk.Treeview, "delivery_groups")
                    return groups if groups.get_children() == ("SB01", "SB02") else None

                after_ready(loaded, lambda groups: inspect_delivery(english, production, panel, groups),
                            "saved group states did not load into the A delivery table")

            def inspect_delivery(english, production, panel, groups):
                status = "Review panels" if english else "待逐格复核"
                assert status in groups.item("SB02", "values"), groups.item("SB02", "values")
                groups.selection_set("SB02")
                groups.event_generate("<<TreeviewSelect>>")
                detail = named(panel, ScrolledText, "delivery_detail")
                headings = [str(label.getvar(variable)) for label in walk(panel, ttk.Label)
                            if (variable := label.cget("textvariable"))]
                assert "SB01 → SB02" in headings, headings
                body = detail.get("1.0", "end")
                assert "SB01" in body and "SB02" in body and status in body, body
                export_title = "Export episode ZIP" if english else "导出整集 ZIP"
                export = next(control for control in walk(panel, ttk.Button) if control.cget("text") == export_title)
                panel.update_idletasks()
                assert export.instate(["disabled"]), (export_title, export.state(), groups.item("SB02", "values"))
                measured_bounds(panel, export)
                with patch.object(filedialog, "asksaveasfilename") as choose:
                    export.invoke()
                    assert not choose.called

                def batch_steps():
                    footer = export.master.master
                    measure(panel, list(walk(footer, ttk.Button)))
                    return [named(panel, ttk.Button, "step_" + name) for name in step_names]

                layout(self, batch_steps, lambda: open_group_review(english, production, panel))

            def open_group_review(english, production, panel):
                caption = "Open group for review" if english else "打开本组复核"

                def editor_for_selected_group():
                    header = next((frame for frame in walk(self, ttk.Frame) if
                                   frame.winfo_name() == "production_task_header" and frame.winfo_ismapped()), None)
                    return header and any("EP04" in label.cget("text") and "SB02" in label.cget("text")
                                          for label in walk(header, ttk.Label))

                def close_editor(_editor):
                    close_current_task(self)
                    close_caption = "Close" if english else "关闭"
                    after_ready(lambda: panel.winfo_ismapped() and any(
                        control.cget("text") == close_caption and control.instate(["!disabled"])
                        for control in walk(panel, ttk.Button)),
                                lambda _ready: finish(english, production, panel),
                                "Batch review did not resume after closing the group")

                after_ready(editor_for_selected_group, close_editor, "A review did not open selected batch group SB02")
                click(panel, caption)

            def finish(english, production, panel):
                click(panel, "Close" if english else "关闭")
                show_page(self, PRODUCTION_TAB)
                if not english:
                    click(self, "中文 / English")
                    start_language(True)
                    return
                resume = named(production, ttk.Button, "a_home_resume")
                resume.invoke()
                reopened = visible_frame(self, "batch_workspace")

                def resumed():
                    episode = named(reopened, ttk.Combobox, "episode")
                    return episode.get().startswith("EP04")

                def complete(_ready):
                    assert ProductionProject.open(group_path).impacts(), "selecting a review row must not approve the project"
                    click(reopened, "Close")
                    print(f"Verified A layout {mode.rsplit('-', 1)[1]}%, both languages at normal/minimum widths, real batch resume and unapproved delivery guard", flush=True)
                    print("COMICFLOW_GUI_OK", flush=True)
                    self.after_idle(self.destroy)

                after_ready(resumed, complete, "A home did not resume the current episode")

            start_language(False)

        def inspect_batch_center(self):
            from src.batch_delivery import publish_episode
            from src.batch_runner import BatchQueue
            from src.batch_workspace import BatchWorkspace
            from src.bundled_validators import bundled_validator
            from src.production_project import ProductionProject
            from src.production_rules import ENGLISH

            workspace_path = project_path.with_suffix(".cfbatch")
            scripts = []
            for index, line in enumerate(("The lantern is lit.", "I see the bridge.", "We can go."), 1):
                path = project_path.with_name(f"EP{index:02d}-script.txt")
                newline = "\r\n" if index % 2 else "\n"
                path.write_bytes(newline.join(("INT. STATION - DAY", "Mira opens the door.", f'Mira: "{line}"', "")).encode("utf-8"))
                scripts.append(path)
            gallery = show_page(self, PRODUCTION_TAB)

            def wait_for(ready, then, reason):
                deadline = time.monotonic() + 8

                def poll():
                    value = ready()
                    if value:
                        then(value)
                    elif time.monotonic() < deadline:
                        self.after(45, poll)
                    else:
                        fail(reason)

                self.after(45, poll)

            def visible(name):
                return next((panel for panel in walk(self, ttk.Frame)
                             if panel.winfo_name() == name and panel.winfo_ismapped()), None)

            def named(panel, kind, name):
                return next(widget for widget in walk(panel, kind) if widget.winfo_name() == name)

            def imported(panel, count):
                combo = named(panel, ttk.Combobox, "episode")
                return len(self.tk.splitlist(combo.cget("values"))) == count

            def click_import(panel, paths):
                with patch.object(filedialog, "askopenfilenames", return_value=tuple(map(str, paths))):
                    click(panel, "导入剧本")

            def create(panel):
                named(panel, ttk.Button, "step_import").invoke()
                self.exercise_page_help(panel, "batch_import")
                with patch.object(filedialog, "asksaveasfilename", return_value=str(workspace_path)):
                    click(panel, "新建批次")
                wait_for(lambda: any(button.cget("text") == "导入剧本" and button.instate(["!disabled"])
                                     for button in walk(panel, ttk.Button)) and workspace_path.is_file(),
                         lambda _ok: first_import(panel), "batch creation did not finish")

            def first_import(panel):
                click_import(panel, scripts[:1])
                wait_for(lambda: imported(panel, 1), lambda _ok: add_more(panel), "single script did not import")

            def add_more(panel):
                workspace = BatchWorkspace.open(workspace_path)
                first = workspace.episodes[0]
                group = ProductionProject.open(workspace.group_paths(first.id)[0])
                assert any("The lantern is lit." in item.text for item in group.sources)
                click_import(panel, scripts[1:])
                wait_for(lambda: imported(panel, 3), lambda _ok: test_reopen(panel), "multi-script import failed")

            def test_reopen(panel):
                workspace = BatchWorkspace.open(workspace_path)
                assert len(workspace.episodes) == 3
                for episode, script in zip(workspace.episodes, scripts):
                    assert workspace.source_text(episode.id).encode("utf-8") == script.read_bytes()
                click(panel, "关闭")
                show_page(self, PRODUCTION_TAB)
                wait_for(lambda: visible("batch_workspace"), reopen, "batch center did not reopen")
                click(gallery, "批量制作中心")

            def reopen(panel):
                with patch.object(filedialog, "askopenfilename", return_value=str(workspace_path)):
                    click(panel, "打开批次")
                wait_for(lambda: imported(panel, 3), lambda _ok: show_trace(panel), "saved batch did not reopen")

            def show_trace(panel):
                selector = named(panel, ttk.Combobox, "episode")
                selector.current(2)
                selector.event_generate("<<ComboboxSelected>>")
                trace = named(panel, ttk.Treeview, "trace")

                def locate_line():
                    return next((iid for iid in trace.get_children() if "We can go." in str(trace.item(iid))), None)

                def inspect_group(iid):
                    trace.selection_set(iid)
                    trace.event_generate("<<TreeviewSelect>>")
                    self.update_idletasks()
                    selector = named(panel, ttk.Combobox, "batch_group")
                    assert selector.get().startswith("SB01")
                    self.exercise_page_help(panel, "batch_plan")
                    assert trace.selection() == (iid,) and selector.get().startswith("SB01")
                    wait_for(lambda: visible("production_task_header"), finish, "could not open group from batch")
                    click(panel, "打开单组制片")

                wait_for(locate_line, inspect_group, "could not trace episode 3 dialogue to its group")

            def finish(group_header):
                def loaded():
                    return any("EP03" in label.cget("text") and "SB01" in label.cget("text")
                               for label in walk(group_header, ttk.Label))
                def close_editor(_ok):
                    named(group_header, ttk.Button, "return_to_batch").invoke()

                    def inspect_target(panel):
                        assert named(panel, ttk.Combobox, "episode").get().startswith("EP03")
                        assert named(panel, ttk.Combobox, "batch_group").get() == "SB01"
                        self.after(100, prepare_queue)

                    wait_for(lambda: visible("batch_workspace"), inspect_target, "case could not return to the batch locator")

                wait_for(loaded, close_editor, "incorrect group opened from source trace")

            def prepare_queue():
                panel = visible_frame(self, "batch_workspace")
                def enabled(label):
                    return any(b.cget("text") == label and b.instate(["!disabled"]) for b in walk(panel, ttk.Button))

                def approve(_ready):
                    click(panel, "确认本集规划")
                    wait_for(lambda: BatchWorkspace.open(workspace_path).plan_approved("EP03") and enabled("本集加入队列"),
                             enqueue, "episode plan approval was not persisted")

                def enqueue(_ready):
                    named(panel, ttk.Button, "step_queue").invoke()
                    self.update_idletasks()
                    episode = named(panel, ttk.Combobox, "episode").get()
                    group = named(panel, ttk.Combobox, "batch_group").get()
                    self.exercise_page_help(panel, "batch_queue")
                    assert next(walk(panel, ttk.Notebook)).index("current") == 2
                    named(panel, ttk.Button, "open_api").invoke()
                    self.update()
                    api = page_at(self, API_TAB)
                    back = named(api, ttk.Button, "api_return")
                    assert back.winfo_ismapped()
                    back.invoke()
                    self.update_idletasks()
                    assert panel.winfo_ismapped()
                    assert named(panel, ttk.Combobox, "episode").get() == episode
                    assert named(panel, ttk.Combobox, "batch_group").get() == group
                    assert next(walk(panel, ttk.Notebook)).index("current") == 2

                    def enqueue_loaded(_ready):
                        click(panel, "本集加入队列")
                        jobs = named(panel, ttk.Treeview, "jobs")
                        wait_for(lambda: jobs.get_children(), lambda _rows: preflight(panel),
                                 "approved episode tasks did not enter the queue")

                    wait_for(lambda: enabled("本集加入队列"), enqueue_loaded, "API return lost the batch queue")

                wait_for(lambda: enabled("确认本集规划"), approve, "batch editor did not resume")

            def preflight(panel):
                workspace = BatchWorkspace.open(workspace_path)
                queue = BatchQueue(workspace)
                assert queue.jobs() and queue.spent() == 0
                assert all(row["episode"] == "EP03" for row in queue.jobs())
                show_page(panel, 3)
                self.update()
                self.exercise_page_help(panel, "batch_delivery")
                target = workspace_path.with_name("未验收的整集.zip")
                export = next(button for button in walk(panel, ttk.Button) if button.cget("text") == "导出整集 ZIP")
                assert export.winfo_ismapped() and export.instate(["disabled"])
                with patch.object(filedialog, "asksaveasfilename", return_value=str(target)) as picker:
                    export.invoke()
                    assert not picker.called
                try:
                    publish_episode(workspace, "EP03", bundled_validator(ENGLISH), target)
                except ValueError as error:
                    assert "尚未逐格确认" in str(error), str(error)
                else:
                    fail("unreviewed episode was accepted by the delivery engine")
                assert not target.exists(), "draft episode presented as a completed delivery"
                click(panel, "关闭")
                print("Verified batch creation, source-to-shot trace, three-episode reopen, offline queue and blocked draft delivery", flush=True)
                print("COMICFLOW_GUI_OK", flush=True)
                self.after_idle(self.destroy)

            wait_for(lambda: visible("batch_workspace"), create, "batch center did not open")
            click(gallery, "批量制作中心")

        def inspect_ecommerce(self):
            from src.ecommerce_delivery import PRODUCT_FILE, label_board_sheet
            from src.ecommerce_project import EcommerceProject, EcommerceShot, render_shots
            from src.workbench_tutorial import __file__ as tutorial_file

            page = show_page(self, ECOMMERCE_TAB)
            navigation = next(walk(self, ttk.Notebook))
            assert navigation.tab(navigation.select(), "text") == "电商信息流视频复刻"
            materials = Path(tutorial_file).resolve().parents[1] / "Examples" / "Workbench" / "Ecommerce"
            video, product = (materials / name for name in ("Reference.mp4", "Product.png"))
            with Image.open(product) as downloaded:
                photo = downloaded.convert("RGB")
            ecommerce_path = project_path.with_suffix(".cfecom")
            delivery_path = ecommerce_path.with_suffix(".zip")

            def visible(kind, caption):
                matches = [widget for widget in walk(page, kind) if widget.cget("text") == caption]
                return next((widget for widget in matches if widget.winfo_ismapped()), matches[0])

            def status_text():
                return "\n".join(str(self.getvar(var)) if (var := label.cget("textvariable")) else label.cget("text")
                                 for label in walk(page, ttk.Label))

            def after_ready(ready, run):
                if ready():
                    run()
                else:
                    self.after(50, lambda: after_ready(ready, run))

            with patch.object(filedialog, "askopenfilename", return_value=str(video)):
                click(page, "导入参考视频")

            def assert_product_gate(expected_error):
                stages = next(walk(page, ttk.Notebook))
                with patch.object(messagebox, "showerror") as missing:
                    click(page, "下一步：分镜分析")
                assert missing.call_count == 1 and expected_error in str(missing.call_args), missing.call_args
                assert stages.index(stages.select()) == 0

            def confirm_references():
                assert_product_gate("产品名称")
                self.exercise_page_help(visible_frame(page, "ecommerce_workflow"), "ecommerce_import")
                name_label = visible(ttk.Label, "自有产品名")
                row = int(name_label.grid_info()["row"])
                entry = next(widget for widget in name_label.master.grid_slaves(row=row)
                             if isinstance(widget, ttk.Entry))
                entry.delete(0, "end")
                entry.insert(0, "试用瓶")
                assert_product_gate("清晰照片")
                with patch.object(filedialog, "askopenfilenames", return_value=(str(product),)):
                    click(page, "导入产品照片")
                after_ready(lambda: next(walk(page, tk.Listbox)).size() == 1, detect)

            def detect():
                assert_product_gate("角度和状态")
                visible(ttk.Checkbutton, "确认产品照片覆盖所需角度").invoke()
                click(page, "下一步：分镜分析")
                click(page, "检测镜头切点")
                shots = next(walk(page, ttk.Treeview))
                after_ready(lambda: len(shots.get_children()) == 3, lambda: verify_cuts(shots))

            def verify_cuts(table):
                ranges = tuple(table.set(item, "time") for item in table.get_children())
                assert ranges == ("00:00.000-00:01.000", "00:01.000-00:02.000", "00:02.000-00:03.000"), ranges
                table.selection_set(table.get_children()[1])
                self.exercise_page_help(visible_frame(page, "ecommerce_workflow"), "ecommerce_shots")
                assert table.selection() == (table.get_children()[1],)
                shot_file = project_path.with_suffix(".json")
                shot_file.write_text(render_shots([
                    EcommerceShot(
                        id=identity, start_ms=index * 1000, end_ms=(index + 1) * 1000,
                        scene="厨房" if index < 2 else "客厅", size="特写", angle="平视", camera="固定",
                        action="演员把产品放在桌上", positions="桌前，产品始终在画面中间",
                        performance="轻轻扬眉，认真地强调产品名", dialogue="“See this bottle?”" if index == 0 else "无",
                        sound="原声对白" if index == 0 else "安静", continuity="品牌朝向保持一致",
                        constraints="固定产品外观", characters=("主持人",), props=("展示底座",) if index == 0 else (),
                        contains_product=True, axis="从桌左侧拍摄",
                    ) for index, identity in enumerate(table.get_children())
                ]), encoding="utf-8")
                with (patch.object(filedialog, "askopenfilename", return_value=str(shot_file)),
                      patch.object(messagebox, "askyesno", return_value=True)):
                    click(page, "导入分镜 JSON")
                with patch.object(messagebox, "askyesno", return_value=True):
                    click(page, "确认分镜并分析资产")
                after_ready(lambda: next(walk(page, ttk.Notebook)).index("current") == 2, verify_asset_plan)

            def verify_asset_plan():
                with patch.object(filedialog, "asksaveasfilename", return_value=str(ecommerce_path)):
                    click(page, "保存电商项目")
                project = EcommerceProject.open(ecommerce_path)
                assert project.product_name == "试用瓶" and project.product_reviewed
                assert project.shot_approval == project.shot_key()
                assert project.shots[0].dialogue == "“See this bottle?”"
                assert [group.scene for group in project.groups()] == ["厨房", "客厅"]
                with patch.object(filedialog, "askopenfilename", return_value=str(ecommerce_path)):
                    click(page, "打开电商项目")
                assert "已打开电商项目" in status_text()

                stages = next(walk(page, ttk.Notebook))
                stages.select(2)
                click(page, "刷新资产清单")
                assets = next(walk(stages.nametowidget(stages.select()), ttk.Treeview))
                fixtures = {
                    "character:主持人": ("character", "#456272", (640, 360)),
                    "scene:厨房": ("kitchen", "#253e4b", (640, 360)),
                    "scene:客厅": ("hall", "#457632", (640, 360)),
                    "props:SB01": ("stand", "#7b4025", (640, 360)),
                    "board:SB01": ("board-01", "#33368e", (1080, 1920)),
                    "board:SB02": ("board-02", "#2b4865", (1080, 1920)),
                }
                assert set(assets.get_children()) == {"product", *fixtures}
                assets.selection_set("scene:厨房")
                selected = assets.selection()
                self.exercise_page_help(visible_frame(page, "ecommerce_workflow"), "ecommerce_assets")
                assert assets.selection() == selected
                click(stages.nametowidget(stages.select()), "API 设置")
                api = page_at(self, API_TAB)
                self.update()
                assert api.winfo_ismapped()
                model_label = next(label for label in walk(api, ttk.Label)
                                   if label.cget("text") == "模型 ID" and label.winfo_ismapped())
                model = model_label.master.grid_slaves(row=int(model_label.grid_info()["row"]), column=1)[0]
                model.insert(0, "unsent-local-ecommerce-model-")
                unsent = model.get()
                self.exercise_page_help(visible_frame(api, "api_settings"), "api")
                assert model.get() == unsent
                named(api, ttk.Button, "api_return", mapped=True).invoke()
                self.update_idletasks()
                assert page.winfo_ismapped() and stages.index(stages.select()) == 2 and assets.selection() == selected

                images = {}
                for key, (name, color, size) in fixtures.items():
                    path = ecommerce_path.with_name(f"{name}.png")
                    image = Image.new("RGB", size, color)
                    ImageDraw.Draw(image).ellipse((40, 50, 240, 250), "#ddcc92")
                    image.save(path)
                    if key.startswith("board:"):
                        group = next(group for group in project.groups() if group.id == key.removeprefix("board:"))
                        labeled = path.with_stem(f"{name}-labeled")
                        label_board_sheet(path, labeled, [shot.id for shot in group.shots])
                        path = labeled
                    images[key] = path

                def confirm_image(title, done):
                    panel = next((frame for frame in walk(page, ttk.Frame)
                                  if frame.winfo_name() == "ecommerce_detail" and frame.winfo_ismapped()), None)
                    if panel is None:
                        self.after(50, lambda: confirm_image(title, done))
                        return
                    assert named(panel, ttk.Label, "ecommerce_detail_title").cget("text") == title
                    assert not list(walk(self, tk.Toplevel)) and self.grab_current() is None
                    click(panel, "确认使用这张图")
                    done()

                def bind_images(iterator):
                    selected = next(iterator, None)
                    if selected is None:
                        click(page, "下一步：提示词与交付")
                        self.exercise_page_help(visible_frame(page, "ecommerce_workflow"), "ecommerce_delivery")
                        click(page, "生成交付预览")
                        after_ready(lambda: "交付预览已准备" in status_text(), export_zip)
                        return
                    key, path = selected
                    assets.selection_set(key)
                    with patch.object(filedialog, "askopenfilename", return_value=str(path)):
                        click(page, "导入批准图像")
                    confirm_image("核对导入资产", lambda: bind_images(iterator))

                assets.selection_set("product")
                click(page, "合成自有产品总图")
                confirm_image("自有产品总图", lambda: bind_images(iter(images.items())))

            def export_zip():
                with patch.object(messagebox, "showerror") as missing_review:
                    click(page, "验收并导出 ZIP")
                assert missing_review.call_count == 1 and "逐项复核" in str(missing_review.call_args)
                visible(ttk.Checkbutton, "已逐格核对画面、原语言对白、产品细节及独立人物资产").invoke()
                with patch.object(filedialog, "asksaveasfilename", return_value=str(delivery_path)):
                    click(page, "验收并导出 ZIP")
                after_ready(lambda: "已通过验收并导出" in status_text(), verify_zip)

            def verify_zip():
                with ZipFile(delivery_path) as package:
                    assert package.testzip() is None
                    storyboard_names = [name for name in package.namelist() if "storyboard_sheet_" in name]
                    product_names = [name for name in package.namelist() if name.endswith("/" + PRODUCT_FILE)]
                    assert len(storyboard_names) == len(product_names) == 2
                    assert package.read(product_names[0]) == package.read(product_names[1])
                    with Image.open(BytesIO(package.read(product_names[0]))) as sheet:
                        assert sheet.size == (1920, 1080)
                        assert sheet.crop((832, 412, 1088, 668)).tobytes() == photo.tobytes()
                    for name in storyboard_names:
                        with Image.open(BytesIO(package.read(name))) as board:
                            assert board.size == (1080, 1920)
                    first_group = storyboard_names[0].split("/", 1)[0]
                    detail = package.read(f"{first_group}/SB01_shot_details.txt").decode("utf-8-sig")
                    prompt = package.read(f"{first_group}/prompts/SD2_prompt.txt").decode("utf-8-sig")
                    assert "“See this bottle?”" in detail and "“See this bottle?”" in prompt
                detail = visible_frame(page, "ecommerce_detail")
                assert named(detail, ttk.Label, "ecommerce_detail_title").cget("text") == "交付完成"
                click(detail, "关闭")
                click(page, "保存电商项目")
                print("Verified ecommerce reference import, product gate, local cuts, asset binding and validated ZIP", flush=True)
                print("COMICFLOW_GUI_OK", flush=True)
                self.tk.eval(self.protocol("WM_DELETE_WINDOW"))

            after_ready(lambda: "144" in status_text() and "256" in status_text(), confirm_references)

        def inspect_new_tools(self):
            from src import reference_tools_dialog
            from src.production_project import ProductionProject

            parent = project_path.parent
            draft = parent / "本地剧本草稿.md"
            reference_png = parent / "动作参考.png"
            director_png = parent / "director-pose" / "frame.png"
            Image.new("RGB", (640, 360), "tan").save(reference_png)

            def receive_still(_parent, path, mode, callback, *, language):
                assert path.samefile(project_path)
                assert (mode, language) == ("pose", "zh")
                callback(director_png)

            show_page(self, PRODUCTION_TAB)
            click(self, "剧本创作")
            script = visible_frame(self, "planning_editor")
            named(script, tk.Text, "planning_source").insert("1.0", "场景一：灯亮了。")
            filedialog.asksaveasfilename = lambda **_kwargs: str(draft)
            click(script, "另存左侧稿件")
            assert draft.read_text(encoding="utf-8") == "场景一：灯亮了。"
            close_current_task(self)
            show_page(self, PRODUCTION_TAB)
            click(self, "资产分析")
            picker = visible_frame(self, "production_project_picker")
            named(picker, ttk.Button, "local_source").invoke()
            analysis = visible_frame(self, "planning_editor")
            assert analysis is not script
            filedialog.askopenfilename = lambda **_kwargs: str(draft)
            click(analysis, "导入 TXT / Markdown")
            assert named(analysis, tk.Text, "planning_source").get("1.0", "end-1c").strip() == "场景一：灯亮了。"
            close_current_task(self)
            print("Verified offline script drafting and the asset analysis entry", flush=True)

            ProductionProject("服装动作试用", "EP01", "SB01").save(project_path)
            def open_reference(button):
                pick_production_project(self, button, project_path)
                self.after(150, lambda: use_reference(button))

            def use_reference(button):
                costume = button == "角色服装设计"
                if costume:
                    from src.reference_tools_dialog import COSTUMES

                    chooser = visible_frame(self, "costume_reference_editor")
                    gallery = next(walk(chooser, tk.Listbox))
                    categories = next(walk(chooser, ttk.Combobox))
                    search = next(widget for widget in walk(chooser, ttk.Entry)
                                  if widget.winfo_name() == "costume_search")
                    assert gallery.size() == len(COSTUMES)
                    assert not any("PoseWear" in widget.cget("text") for widget in walk(chooser, ttk.Button))
                    categories.set("通勤与职业")
                    categories.event_generate("<<ComboboxSelected>>")
                    assert gallery.get(0, "end") == ("石色风衣与九分裤", "黑色三件套西装",
                                                     "医生白大褂与浅蓝衬衫", "白底浅蓝边护士服")
                    confirm = next(widget for widget in walk(chooser, ttk.Button)
                                   if widget.cget("text") == "使用参考图进入生图")
                    search.insert(0, "no matching item")
                    assert gallery.size() == 0 and confirm.instate(["disabled"])
                    search.delete(0, "end")
                    search.insert(0, "c259")
                    assert gallery.get(0, "end") == ("白底浅蓝边护士服",)
                    assert gallery.curselection() == (0,) and confirm.instate(["!disabled"])
                    click(chooser, "使用参考图进入生图")
                    image_job = visible_frame(self, "image_production_editor")
                    assert not list(walk(self, tk.Toplevel)) and self.grab_current() is None
                    check_image_configuration(image_job, costume)
                    close_current_task(self)
                    open_reference("角色动作设计")
                else:
                    chooser = visible_frame(self, "pose_reference_editor")
                    with patch.object(reference_tools_dialog, "open_director", side_effect=receive_still):
                        click(chooser, "打开内置 3D 导演台")
                    click(chooser, "使用参考图进入生图")
                    image_job = visible_frame(self, "image_production_editor")
                    assert not list(walk(self, tk.Toplevel)) and self.grab_current() is None
                    check_image_configuration(image_job, False)
                    close_current_task(self)
                    verify_reference_files()

            def check_image_configuration(image_job, costume):
                assert any(widget.get() == "参考图生图" for widget in walk(image_job, ttk.Combobox))
                refs = next(walk(image_job, tk.Listbox))
                assert len(refs.curselection()) == 1

                click(image_job, "预览本次发送")
                preview = visible_frame(self, "image_report")
                payload = next(walk(preview, tk.Text)).get("1.0", "end-1c")
                assert ("仅指定服装" if costume else "仅指定人物动作") in payload
                named(preview, ttk.Button, "close_preview").invoke()
                assert image_job.winfo_exists()

            def verify_reference_files():
                saved = ProductionProject.open(project_path)
                assert len(saved.images) == 2 and all(image.reference_only for image in saved.images)
                assert "costume_C259_front.webp | WEBP SHA-256 " in saved.images[0].origin, saved.images[0].origin
                assert saved.checked_image(project_path, saved.images[-1]).read_bytes() == director_png.read_bytes()
                assert not saved.image_jobs
                show_page(self, REVIEW_TAB)
                filedialog.askopenfilename = lambda **_kwargs: str(reference_png)
                click(self, "图片大小与比例")
                check = next(walk(self, tk.Toplevel))
                click(check, "选择本地图片")
                assert any("640 × 360 px · 16:9" in self.getvar(variable) for widget in walk(check, ttk.Label)
                           if (variable := widget.cget("textvariable")))
                check.destroy()
                click(self, "开始验收")
                self.after(150, verify_cut)

            def verify_cut():
                selector = next(walk(page_at(self, REVIEW_TAB), ttk.Combobox))
                if not selector["values"]:
                    self.after(100, verify_cut)
                    return
                click(self, "景别机位与格间衔接")
                review = next(walk(self, tk.Toplevel))
                pair = next(walk(review, ttk.Combobox))
                assert "SB01-01 → SB01-02" in pair.get()
                review.destroy()
                print("Verified costume and 3D reference handoff, picture facts and adjacent-cut review", flush=True)
                print("COMICFLOW_GUI_OK", flush=True)
                self.destroy()

            open_reference("角色服装设计")

        def inspect_mode_switch(self, validator):
            from src.bundled_validators import bundled_validator
            from src.production_project import ProductionProject
            from src.production_rules import CHINESE, ENGLISH

            english, chinese = walk(self, ttk.Radiobutton)
            assert english.cget("text") == "英文影片制作" and english.instate(["selected"])
            assert chinese.cget("text") == "中文影片制作"
            scripts = Path(archive).with_name("validator.py"), Path(archive).with_name("中文校验.py")
            select_script = next(widget for widget in walk(self, ttk.Button) if widget.cget("text") == "浏览"
                                 and int(widget.grid_info().get("row", -1)) == 1)
            for choice, script in zip((english, chinese), scripts):
                choice.invoke()
                if choice is english:
                    assert Path(validator.get()) == bundled_validator(ENGLISH)
                else:
                    assert not validator.get()
                filedialog.askopenfilename = lambda **_kwargs: str(script)
                select_script.invoke()
                assert validator.get() == str(script)
            english.invoke()
            assert Path(validator.get()).resolve() == scripts[0].resolve()
            chinese.invoke()
            assert Path(validator.get()).resolve() == scripts[1].resolve()

            show_page(self, PRODUCTION_TAB)
            click(self, "单组制片")
            dialog = next(walk(self, tk.Toplevel))
            filedialog.asksaveasfilename = lambda **_kwargs: str(project_path)
            click(dialog, "新建单组项目")
            assert ProductionProject.open(project_path).rules == CHINESE
            tabs = next(walk(dialog, ttk.Notebook))
            assert tabs.tab(3, "text") == "文本与排版"
            previous = project_path.with_name("旧英文制片.cfproject")
            ProductionProject("旧英文制片", "EP01", "SB01").save(previous)
            for path, choice, script, title in ((previous, english, scripts[0], "复核与交付"),
                                                (project_path, chinese, scripts[1], "文本与排版")):
                filedialog.askopenfilename = lambda **_kwargs: str(path)
                click(dialog, "打开单组项目")
                assert choice.instate(["selected"]) and tabs.tab(3, "text") == title
                assert Path(validator.get()).resolve() == script.resolve()
            self.exercise_chinese_text(dialog, tabs)
            self.exercise_chinese_layout(dialog, tabs)
            dialog.destroy()
            self.inspect_home_workflow(chinese, validator, scripts[1])

        def inspect_home_workflow(self, chinese, validator, script):
            from src.production_project import ProductionProject
            from src.production_rules import CHINESE

            click(self, "中文 / English")
            assert self.title() == APP_NAME_EN
            assert chinese.instate(["selected"]) and chinese.cget("text") == "Chinese film production"
            assert Path(validator.get()).resolve() == script.resolve()
            assert next(walk(page_at(self, REVIEW_TAB), ttk.Entry)).get() == archive
            self.geometry("900x700")
            self.update_idletasks()
            home_actions = ("Batch production center", "Script writing", "Shot planning", "Asset analysis", "Asset image generation",
                            "Storyboard generation", "Prompt drafting", "Costume design", "Character pose design",
                            "Package storyboard group")
            for name in home_actions:
                button = next(w for w in walk(self, ttk.Button) if w.cget("text") == name)
                assert button.winfo_viewable() and button.winfo_rooty() + button.winfo_height() <= self.winfo_rooty() + 700
            print("Verified bilingual home controls at the minimum window size", flush=True)
            routes = iter((
                ("Shot planning", "production_panel", "Shot list"),
                ("Approved images", "production_panel", "Approved images"),
                ("Layout & handoff", "layout_editor", "16:9 layout"),
                ("Prompt drafting", "production_panel", "Prompt drafting"),
                ("Asset image generation", "image_production_editor", "New image job"),
                ("Storyboard generation", "image_production_editor", "New image job"),
                ("Package storyboard group", "production_panel", "Text, layout & delivery"),
            ))

            def next_route():
                route = next(routes, None)
                if route is None:
                    finish()
                    return
                print(f"Opening home route {route[0]}", flush=True)
                pick_production_project(self, route[0], project_path)
                verify_view(route)

            def verify_view(route):
                shortcut, frame_name, tab_name = route
                tool = visible_frame(self, frame_name)
                assert not list(walk(self, tk.Toplevel)) and self.grab_current() is None
                tabs = next(walk(tool, ttk.Notebook))
                assert tabs.tab(tabs.select(), "text") == tab_name
                if shortcut == "Prompt drafting":
                    assert named(tool, tk.Text, "production_prompt")
                if shortcut == "Storyboard generation":
                    assert any(w.get() == "Storyboard" for w in walk(tool, ttk.Combobox))
                close_current_task(self)
                self.after_idle(next_route)

            def verify_repair():
                panel = next(walk(self, tk.Toplevel))
                assert panel.title() == f"{APP_NAME_EN} · Assets & repairs"
                panel.destroy()

            def finish():
                assert ProductionProject.open(project_path).rules == CHINESE
                show_page(self, REVIEW_TAB)
                self.after(80, verify_repair)
                click(self, "Assets & repairs")
                click(self, "中文 / English")
                assert chinese.cget("text") == "中文影片制作" and chinese.instate(["selected"])
                print("Verified seven production routes and the bilingual five-page workbench", flush=True)
                click(self, "开始验收")
                self.after(100, self.inspect_chinese_report)

            next_route()

        def exercise_chinese_text(self, dialog, tabs):
            from src.production_project import SHOT_FIELDS, ProductionProject, Shot
            from src.production_rules import CHINESE

            first = "停" * 98 + " A2。  "
            text = first + "走！"
            example = ProductionProject("中文对白试用", "EP01", "SB01", rules=CHINESE)
            source = example.import_source("批准文本.md", "R1", text)
            example.import_dialogue(source, json.dumps([{"id": "D001", "speaker": "值班员", "text": text}]))
            example.notes.update({"分组状态": "常规", "对白规格": "三句以上或长对白", "覆盖段落": "试用片段",
                                  "本组进入状态": "门关着", "本组退出状态": "灯灭", "连续性锁定": "门保持关闭"})
            example.prompt = {"场景/总体状态": "空走廊", "公共限制": "保持门灯位置"}
            for index in range(6):
                fields = dict.fromkeys(SHOT_FIELDS, "合成镜头")
                fields["唯一角色数量锁定"] = "无"
                fields["声源位置"] = "画外同期"
                example.shots.append(Shot(source=source.id, anchor=f"镜头 {index + 1}", fields=fields))
            example.shots[0].dialogue = [("D001", 0, len(first))]
            example.shots[0].fields.update({"景别": "中近景", "机位/角度": "平视",
                                            "动作阶段与机位变化": "从门右侧移到左侧看灯"})
            example.shots[1].fields.update({"景别": "近中景", "机位/角度": "俯拍"})
            path = project_path.with_name("中文对白制片.cfproject")
            example.save(path)
            filedialog.askopenfilename = lambda **_kwargs: str(path)
            click(dialog, "打开单组项目")
            tabs.select(1)

            def inspect_camera_warning():
                preflight = next(walk(dialog, tk.Toplevel))
                assert preflight.title() == "景别与角度预检"
                content = next(walk(preflight, tk.Text)).get("1.0", "end-1c")
                assert "SB01-01 → SB01-02" in content and "分镜记录景别相同" in content
                preflight.destroy()

            self.after(75, inspect_camera_warning)
            click(dialog, "景别与角度预检")
            print("Verified repeated Chinese shot scales are flagged before generation", flush=True)

            def adopt():
                drafting = next(walk(dialog, tk.Toplevel))
                assert next(walk(drafting, ttk.Notebook)).tab(0, "text") == "中文对白预排"
                click(drafting, "预排中文对白")
                rows = next(walk(drafting, ttk.Combobox)).cget("values")
                assert len(rows) == 2 and "100 字" in rows[0] and "1 字" in rows[1], rows
                ask = messagebox.askyesno
                try:
                    messagebox.askyesno = lambda *_args, **_kwargs: True
                    click(drafting, "采用所选对白组")
                finally:
                    messagebox.askyesno = ask
                drafting.destroy()

            self.after(50, adopt)
            click(dialog, "对白与分镜起草")
            assert ProductionProject.open(path).dialogue_scope == {"D001": [0, len(first)]}
            tabs.select(3)
            click(dialog, "预览两份 TXT")
            filedialog.askdirectory = lambda **_kwargs: str(path.parent)
            click(dialog, "导出两份 TXT")
            export = path.parent / "SB01_文字稿"
            record = (export / "SB01_shot_details.txt").read_text(encoding="utf-8-sig")
            prompt = (export / "SD2_prompt.txt").read_text(encoding="utf-8-sig")
            approved_line = f"对白：值班员：“{first}”"
            assert "总发声字数：100" in record and approved_line in record and approved_line in prompt
            assert "动作阶段与机位变化：从门右侧移到左侧看灯" in record and "动作阶段与机位变化" not in prompt
            assert "走！" in (export / "待制作分镜.txt").read_text(encoding="utf-8-sig")
            print("Verified Chinese 100/101 dialogue preview and TXT export through Tk", flush=True)

        def exercise_chinese_layout(self, dialog, tabs):
            from src.production_project import SHOT_FIELDS, ProductionProject, Shot
            from src.production_rules import CHINESE

            folder = project_path.parent / "合成排版"
            folder.mkdir()
            path = folder / "中文十格.cfproject"
            project = ProductionProject("中文十格", "EP01", "SB01", rules=CHINESE)
            source = project.import_source("批准片段.md", "R1", "灯灭后，转到北侧廊道观察。")
            project.notes.update({"分组状态": "常规", "对白规格": "无对白", "覆盖段落": "合成样例",
                                  "本组进入状态": "门关着", "本组退出状态": "灯灭", "连续性锁定": "保持门灯位置",
                                  "组间镜头衔接核对": "前段先看门，后段换走廊",
                                  "景别衔接核对": "先交代门位置，再到各设备",
                                  "主角判定": "建筑与设施，无人物或角色型实体",
                                  "武器轴线核对": "无", "镜头节奏核对": "先看门再转走廊",
                                  "空间合理性核对": "以门框和墙灯为锚点",
                                  "群像差异化核对": "无群像", "追击节奏核对": "无追击"})
            project.prompt = {"场景/总体状态": "南厅与北廊", "公共限制": "保持两个独立场景"}
            for index in range(10):
                fields = dict.fromkeys(SHOT_FIELDS, "本镜环境示意")
                fields["唯一角色数量锁定"] = "无"
                project.shots.append(Shot(source=source.id, anchor=f"观察 {index+1}", fields=fields))
            attach_chinese_layout(project, path, folder, distinct=2)
            project.save(path)
            filedialog.askopenfilename = lambda **_kwargs: str(path)
            click(dialog, "打开单组项目")

            def inspect_sheets():
                layout = next(walk(dialog, tk.Toplevel))
                mixed = next(widget for widget in walk(layout, ttk.Checkbutton) if widget.cget("text") == "多场景共用净板合辑")
                mixed.invoke()

                def inspect_pages():
                    preview = next(walk(layout, tk.Toplevel))
                    book = next(walk(preview, ttk.Notebook))
                    assert [book.tab(index, "text") for index in range(2)] == ["故事板 01–06", "故事板 07–10"]
                    preview.destroy()

                self.after(50, inspect_pages)
                click(layout, "生成排版预览")
                original = simpledialog.askstring
                try:
                    simpledialog.askstring = lambda *_args, **_kwargs: "合成样例，核对页码、地点和局部窗"
                    click(layout, "确认排版并更新正式图")
                finally:
                    simpledialog.askstring = original
                layout.destroy()

            self.after(50, inspect_sheets)
            click(dialog, "排版与交接")
            tabs.select(3)
            filedialog.askdirectory = lambda **_kwargs: str(folder)
            click(dialog, "导出排版图与 TXT")
            output = folder / "SB01_排版复核"
            assert (output / "storyboard_01_6panel_bw_16x9.png").is_file()
            assert (output / "storyboard_02_4panel_bw_16x9.png").is_file()
            text = (output / "SB01_shot_details.txt").read_text(encoding="utf-8-sig")
            assert "场景资产模式：多场景局部" in text
            assert "SB01-07 | storyboard_02_4panel" in text and "最终总图数=4" in text
            print("Verified Chinese 6+4 storyboard tabs and multi-scene PNG/TXT export through Tk", flush=True)

            def inspect_delivery():
                review = next(walk(dialog, tk.Toplevel))
                shots = next(walk(review, ttk.Combobox))
                assert shots.get() == "SB01 / SB01-01"
                shots.current(5)
                shots.event_generate("<<ComboboxSelected>>")
                click(review, "下一镜")
                assert shots.get() == "SB01 / SB01-07"
                review.destroy()

            self.after(100, inspect_delivery)
            click(dialog, "正式交付预览")
            original = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *_args, **_kwargs: True
                click(dialog, "确认本版画面")
            finally:
                messagebox.askyesno = original
            archive = folder / "中文正式交付.zip"
            filedialog.asksaveasfilename = lambda **_kwargs: str(archive)
            click(dialog, "验收并导出 ZIP")
            with ZipFile(archive) as exported:
                assert exported.testzip() is None
                assert "README.txt" in exported.namelist()
                assert "SB01/SD2_prompt.txt" in exported.namelist()
            print("Verified Chinese strict single ZIP publish through Tk with the fixture validator", flush=True)

        def inspect_chinese_report(self):
            table = next(walk(page_at(self, REVIEW_TAB), ttk.Treeview))
            if not table.get_children():
                self.after(100, self.inspect_chinese_report)
                return
            assert "Chinese mode validator" in table.item("0", "values")[-1]
            click(self, "中文 / English")
            assert "Chinese film production" in self.getvar(next(
                label.cget("textvariable") for label in walk(self, ttk.Label)
                if label.cget("textvariable") and "Automated checks passed" in self.getvar(label.cget("textvariable"))
            ))
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def inspect_file_only(self):
            for label in walk(self, ttk.Label):
                if (variable := label.cget("textvariable")) and "工作流未验" in self.getvar(variable):
                    dialog_buttons = list(walk(self, ttk.Button))
                    review = next(button for button in dialog_buttons if button.cget("text") == "逐格复核")
                    assert review.instate(["!disabled"])
                    print("COMICFLOW_GUI_OK", flush=True)
                    self.destroy()
                    return
            self.after(100, self.inspect_file_only)

        def inspect_result(self):
            table = next(walk(page_at(self, REVIEW_TAB), ttk.Treeview))
            if not table.get_children():
                self.after(100, self.inspect_result)
                return
            assert len(table.get_children()) == 1
            assert table.item("0", "values")[1:4] == ("SB01", "SB01-01", "SB01_shot_details.txt")
            selector = next(walk(page_at(self, REVIEW_TAB), ttk.Combobox))
            table.selection_set("0")
            self.update()
            assert selector.get() == "SB01/SB01_shot_details.txt"
            selector.set("SB01/storyboard_2panel.png")
            selector.event_generate("<<ComboboxSelected>>")
            self.update()
            assert any(widget.cget("image") for widget in walk(self, ttk.Label))
            self.after(50, self.inspect_shot_dialog)
            click(self, "逐格复核")
            self.after(50, self.inspect_asset_dialog)
            click(self, "资产与返修")
            show_page(self, PRODUCTION_TAB)
            click(self, "对白与九图预算")
            next(walk(self, tk.Toplevel)).destroy()
            click(self, "单组制片")
            self.inspect_production_dialog()
            print("COMICFLOW_GUI_OK", flush=True)
            self.destroy()

        def inspect_shot_dialog(self):
            from src.shot_review_dialog import ImagePane

            dialog = next(walk(self, tk.Toplevel))
            field = next(walk(dialog, ttk.Combobox))
            board = next(walk(dialog, ImagePane))
            # Paned windows negotiate geometry only after the dialog is mapped.
            if not board.canvas.winfo_viewable() or board.canvas.winfo_width() < 40:
                self.after(100, self.inspect_shot_dialog)
                return
            assert field.get() == "SB01 / SB01-01"
            click(dialog, "下一镜")
            assert field.get() == "SB01 / SB01-02"
            dialog.update_idletasks()
            left, top, width, height = board.image_bounds
            assert width >= 40 and height >= 30, (board.image_bounds, board.canvas.winfo_geometry())
            x, y = left + width // 2, top + height // 2
            board.canvas.event_generate("<ButtonPress-1>", x=left + 4, y=top + 4, when="now")
            assert board.drag_start is not None, "Tk did not process the canvas button press"
            board.canvas.event_generate("<Motion>", x=x, y=y, state=0x100, when="now")
            board.canvas.event_generate("<ButtonRelease-1>", x=x, y=y, state=0x100, when="now")
            assert board.zoomed and board.regions.get(("SB01", "SB01-02")), (
                board.image_bounds, board.canvas.winfo_geometry(), board.drag_start,
            )
            dialog.destroy()

        def inspect_asset_dialog(self):
            dialog = next(walk(self, tk.Toplevel))
            tabs = next(walk(dialog, ttk.Notebook))
            assert [tabs.tab(index, "text") for index in range(2)] == ["资产登记", "返修打包"]
            tabs.select(1)
            dialog.destroy()

        def inspect_production_dialog(self):
            from src import drafting_dialog, image_production_dialog
            from src.image_api import ImageReply, ImageRequestError
            from src.production_project import ProductionProject
            from src.text_api import TextReply

            original = filedialog.askopenfilename
            request = drafting_dialog.request_text
            submit_image = image_production_dialog.submit_image
            askyesno = messagebox.askyesno
            askstring = simpledialog.askstring
            try:
                filedialog.asksaveasfilename = lambda **_kwargs: str(project_path)
                filedialog.askopenfilename = lambda **_kwargs: str(project_path)
                dialog = next(walk(self, tk.Toplevel))
                tabs = next(walk(dialog, ttk.Notebook))
                assert [tabs.tab(index, "text") for index in range(4)] == ["项目与组", "镜头清单", "批准图像", "复核与交付"]
                click(dialog, "新建单组项目")
                assert project_path.is_file()
                assert tabs.tab(1, "state") == "normal"
                name = next(walk(dialog, ttk.Entry))
                name.delete(0, "end")
                name.insert(0, "制片窗口验收")
                script = project_path.with_suffix(".md")
                script.write_text("信号灯亮起。", encoding="utf-8")
                filedialog.askopenfilename = lambda **_kwargs: str(script)
                simpledialog.askstring = lambda *_args, **_kwargs: "R1"
                click(dialog, "导入批准剧本")
                click(dialog, "保存项目")
                filedialog.askopenfilename = lambda **_kwargs: str(project_path)
                click(dialog, "打开单组项目")
                assert name.get() == "制片窗口验收"

                mock_output = ('{"shots":[{"line_start":1,"line_end":1,'
                               '"fields":{"画面/事件":"信号灯亮起","景别":"特写"}}]}')
                drafting_dialog.request_text = lambda *_args: TextReply(mock_output, "smoke")
                messagebox.askyesno = lambda *_args, **_kwargs: True
                self.after(50, lambda: self.inspect_drafting_dialog(dialog))
                click(dialog, "对白与分镜起草")
                saved = ProductionProject.open(project_path)
                assert len(saved.text_drafts) == len(saved.shots) == 1
                assert saved.shots[0].fields["画面/事件"] == "信号灯亮起"
                picture = BytesIO()
                Image.new("RGB", (320, 180), "steelblue").save(picture, format="PNG")
                def submit_synthetic(_settings, request):
                    if request.get_header("Authorization") == "Bearer first-try":
                        raise ImageRequestError("服务返回 HTTP 401。请核对 API Key。", request_id="smoke-error-401")
                    return ImageReply((picture.getvalue(),), request_id="smoke-image")

                image_production_dialog.submit_image = submit_synthetic
                self.after(50, lambda: self.inspect_image_dialog(dialog))
                click(dialog, "图像制片")
                saved = ProductionProject.open(project_path)
                assert len(saved.image_jobs) == 2 and len(saved.images) == 1
                assert saved.image_jobs[-1]["status"] == "approved"
                self.after(50, lambda: self.inspect_layout_dialog(dialog))
                click(dialog, "排版与交接")
                restored = ProductionProject.open(project_path)
                assert len(restored.shots) == 1 and not restored.pending_shots
                assert restored.shots[0].id == saved.shots[0].id
                dialog.destroy()
            finally:
                filedialog.askopenfilename = original
                drafting_dialog.request_text = request
                image_production_dialog.submit_image = submit_image
                messagebox.askyesno = askyesno
                simpledialog.askstring = askstring

        def inspect_drafting_dialog(self, production):
            dialog = next(walk(production, tk.Toplevel))
            tabs = next(walk(dialog, ttk.Notebook))
            assert [tabs.tab(index, "text") for index in range(2)] == ["对白与九图预排", "文本模型与历史"]
            click(dialog, "预排批准整句")
            tabs.select(1)
            for label_text in ("文本模型 ID", "API Key"):
                label = next(widget for widget in walk(dialog, ttk.Label) if widget.cget("text") == label_text)
                entry = label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]
                entry.insert(0, "synthetic")
            click(dialog, "调用模型起草")
            self.after(100, lambda: self.finish_drafting(dialog))

        def finish_drafting(self, dialog):
            from src.production_project import ProductionProject

            if not ProductionProject.open(project_path).text_drafts:
                self.after(100, lambda: self.finish_drafting(dialog))
                return
            click(dialog, "采纳已选建议")
            dialog.destroy()

        def inspect_image_dialog(self, production):
            from src.production_project import ProductionProject

            dialog = next(walk(production, tk.Toplevel))
            tabs = next(walk(dialog, ttk.Notebook))
            assert [tabs.tab(index, "text") for index in range(2)] == ["新建生图任务", "候选与任务"]
            label = next(widget for widget in walk(dialog, ttk.Label) if widget.cget("text") == "API Key")
            key = label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]
            assert not key.get()
            label = next(widget for widget in walk(dialog, ttk.Label) if widget.cget("text") == "API 基础地址")
            base = label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]
            original_base, showerror = base.get(), messagebox.showerror
            errors = []
            try:
                base.delete(0, "end")
                base.insert(0, "http://example.test")
                messagebox.showerror = lambda _title, message, **_kwargs: errors.append(message)
                click(dialog, "预览本次发送")
                assert len(errors) == 1 and "HTTPS" in errors[0], errors
                base.delete(0, "end")
                base.insert(0, original_base)
                click(dialog, "确认并提交生图")
                assert len(errors) == 2 and "API 密钥" in errors[1], errors
            finally:
                messagebox.showerror = showerror

            def inspect_preview():
                report = next(walk(dialog, tk.Toplevel))
                content = next(walk(report, tk.Text)).get("1.0", "end-1c")
                report.destroy()
                assert "本地预览，尚未发送" in content
                assert "https://ark.cn-beijing.volces.com/api/v3/images/generations" in content
                assert "输出一张图。" in content
                assert "软件锁定规则" in content and "用户资料" in content

            self.after(50, inspect_preview)
            click(dialog, "预览本次发送")
            assert not ProductionProject.open(project_path).image_jobs
            print("Verified offline image preview and required API key for submission through Tk", flush=True)
            key.insert(0, "first-try")
            click(dialog, "确认并提交生图")
            self.after(100, lambda: self.inspect_image_error(dialog, tabs, key))

        def inspect_image_error(self, dialog, tabs, key):
            from src.production_project import ProductionProject

            saved = ProductionProject.open(project_path)
            if saved.image_jobs[0]["status"] == "submitting":
                self.after(100, lambda: self.inspect_image_error(dialog, tabs, key))
                return
            error = saved.image_jobs[0]
            assert error["status"] == "failed" and error["request_id"] == "smoke-error-401"
            assert "first-try" not in project_path.read_text(encoding="utf-8")
            assert any("请求号 smoke-error-401" in widget.get("1.0", "end-1c") for widget in walk(dialog, tk.Text))
            print("Verified failed image submission preserves guidance and request ID through Tk", flush=True)
            tabs.select(0)
            key.delete(0, "end")
            key.insert(0, "synthetic")
            click(dialog, "确认并提交生图")
            self.after(100, lambda: self.inspect_candidate(dialog))

        def inspect_layout_dialog(self, production):
            from src.production_project import ProductionProject

            dialog = next(walk(production, tk.Toplevel))
            tabs = next(walk(dialog, ttk.Notebook))
            assert [tabs.tab(index, "text") for index in range(2)] == ["16:9 排版", "相邻组交接"]
            table = next(walk(dialog, ttk.Treeview))
            table.selection_set(table.get_children()[0])
            tabs.select(1)
            click(dialog, "暂存所选及后续镜头")
            saved = ProductionProject.open(project_path)
            assert len(saved.pending_shots) == 1 and not saved.shots
            click(dialog, "恢复本组待制作")
            dialog.destroy()

        def inspect_image_entry(self):
            from threading import Event

            from src.production_project import ProductionProject

            pick_production_project(self, "资产图生成", "")
            assert next(walk(self, tk.Toplevel), None) is None

            project = ProductionProject("制片测试", "EP01", "SB06")
            project.image_jobs = [{"kind": "角色", "provider": "历史配置", "status": "ready"}]
            project.save(project_path)
            original_bytes = project_path.read_bytes()
            real_open = ProductionProject.open
            reading, release = Event(), Event()

            def delayed_read(path):
                reading.set()
                assert release.wait(5), "Opening the project blocked the Tk event loop"
                return real_open(path)

            opening = patch.object(ProductionProject, "open", side_effect=delayed_read)
            forbidden_save = patch.object(ProductionProject, "save", side_effect=AssertionError("Opening rewrote the project"))
            with opening, forbidden_save as write:
                parent = pick_production_project(self, "资产图生成", project_path)
                wait_for(self, reading.is_set, "The selected project was not read in the background")
                variables = (widget.cget("textvariable") for widget in walk(parent, ttk.Label))
                assert any("正在打开项目" in self.getvar(value) for value in variables if value)
                assert not list(walk(self, tk.Toplevel)) and self.grab_current() is None
                assert not any(w.winfo_ismapped() and w.winfo_name() == "image_production_editor"
                               for w in walk(self, ttk.Frame))
                release.set()
                panel = visible_frame(self, "image_production_editor")
                assert self.grab_current() is None
                assert project_path.read_bytes() == original_bytes and not write.called
                tabs = next(walk(panel, ttk.Notebook))
                tabs.select(1)
                assert any("历史图像任务的记录不完整" in widget.get("1.0", "end")
                           for widget in walk(panel, tk.Text))
                close_current_task(self)
            print("Verified responsive direct asset opening with a delayed read and incomplete job history")
            print("COMICFLOW_GUI_OK", flush=True)
            self.after_idle(self.destroy)

        def inspect_candidate(self, dialog):
            from src.production_project import ProductionProject

            saved = ProductionProject.open(project_path)
            if len(saved.image_jobs) < 2 or saved.image_jobs[-1]["status"] != "ready":
                self.after(100, lambda: self.inspect_candidate(dialog))
                return
            assert not saved.images
            self.after(50, lambda: self.approve_image(dialog))
            click(dialog, "批准并加入正式交付")
            dialog.destroy()

        def approve_image(self, dialog):
            panel = next(walk(dialog, tk.Toplevel))
            if panel.title() == "图像核对":
                assert next(walk(panel, ttk.Notebook)).tab(0, "text") == "模型返回原图"
                panel.destroy()
                self.after(50, lambda: self.approve_image(dialog))
                return
            assert panel.title() == "批准候选图"
            for name, value in (("实际处理理由", "补缺合成测试图"), ("实际核图结果", "核对实际尺寸和画面范围")):
                label = next(widget for widget in walk(panel, ttk.Label) if widget.cget("text") == name)
                label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0].insert(0, value)
            click(panel, "确认批准")

    tk.Tk = SmokeWindow
    filedialog.askopenfilename = lambda **_kwargs: archive
    messagebox.showerror = lambda title, message, **_kwargs: fail(f"{title}: {message}")


def drive_native_director(output, language, mode):
    """Use the real Edge window to operate the shipped upstream editor."""
    from threading import Thread
    import webview
    from src.director_desk import run_window

    real_start = webview.start
    errors = []

    def start_with_driver(wait_for_result, **options):
        window = webview.windows[0]

        def drive():
            deadline = time.monotonic() + {"pose": 42, "action": 26, "motion": 85}[mode]

            def until(script, message):
                while time.monotonic() < deadline:
                    if result := window.run_js(script):
                        return result
                    time.sleep(0.15)
                status = window.run_js('document.querySelector("#status")?.textContent')
                raise RuntimeError(f"{message}. URL: {window.get_current_url()}, status: {status}")

            def desk(script):
                return f"(() => {{const desk = document.querySelector('#desk')?.contentDocument; return desk && ({script});}})()"

            def click(selector):
                target = f"desk.querySelector({json.dumps(selector)})"
                until(desk(f"Boolean({target})"), f"Missing 3D control {selector}")
                window.run_js(desk(f"{target}.click()"))

            try:
                if not window.events.before_load.wait(20):
                    raise RuntimeError("The native WebView page never reached navigation.")
                if window.gui.renderer != "edgechromium":
                    raise RuntimeError(f"Expected Edge WebView2, found {window.gui.renderer}")
                until('document.querySelector("#send") && !document.querySelector("#send").disabled',
                      "Local 3D director bridge did not initialize")
                until(desk('Boolean(desk.querySelector("canvas"))'), "Local 3D viewport did not load")
                if mode == "pose":
                    click('[aria-label="选择画幅比例"]')
                    click('.viewport-aspect-option:has(.viewport-aspect-option-frame-16-9)')
                    exercise_director_pose_regression(window.run_js, until, desk, click, Path(output))
                elif mode == "motion":
                    motion_smoke = run_path(str(Path(__file__).with_name("director_motion_clip_smoke.py")))
                    motion_smoke["exercise_director_motion_clip"](window.run_js, until, desk, click, Path(output), language)
                else:
                    click('[role="treeitem"][aria-label="角色01"] .object-select-button')
                    click('[aria-label="角色面板标签"] button:last-child')
                    click(".character-route-add")
                    click(".character-route-add")
                    second_point = json.dumps('[aria-label="选择路线点 2"]')
                    until(desk(f"Boolean(desk.querySelector({second_point}))"),
                          "The second route point was not recorded")
                external = window.run_js("""[...performance.getEntriesByType('resource'),
                    ...document.querySelector('#desk').contentWindow.performance.getEntriesByType('resource')]
                    .map(entry => new URL(entry.name)).filter(url => /^https?:$/.test(url.protocol) &&
                     url.origin !== location.origin).map(url => url.origin)""")
                if external:
                    raise RuntimeError(f"Unexpected external resources: {external}")
                window.run_js('void setTimeout(() => document.querySelector("#send").click(), 75)')
            except Exception as error:
                errors.append(str(error))
                window.destroy()

        def on_start():
            Thread(target=drive, daemon=True).start()
            wait_for_result()

        return real_start(on_start, **options)

    with patch.object(webview, "start", side_effect=start_with_driver):
        run_window(Path(output), "windows-smoke", language, "pose" if mode == "motion" else mode)
    if errors:
        raise RuntimeError(errors[0])


def mannequin_connected_fraction(frame):
    """Measure the largest connected blue silhouette in a clean camera export."""
    import numpy as np

    with Image.open(BytesIO(frame)) as image:
        assert image.format == "PNG" and image.size == (1280, 720), image.size
        red, green, blue = np.asarray(image.convert("RGB"), dtype=np.int16).transpose(2, 0, 1)
    y, x = np.nonzero((blue > red + 14) & (blue > green + 8) & (blue > 30))
    pixels = set(zip(x.tolist(), y.tolist()))
    total, largest = len(pixels), 0
    assert total > 2_000, "No readable mannequin silhouette in the exported image"
    while pixels:
        pending, size = [pixels.pop()], 0
        while pending:
            px, py = pending.pop()
            size += 1
            for neighbor in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if neighbor in pixels:
                    pixels.remove(neighbor)
                    pending.append(neighbor)
        largest = max(largest, size)
    return largest / total


def exercise_director_pose_regression(run_js, until, desk, click, output):
    """Use real pose, playback and reopen controls, then check rendered joints from clean frames."""
    def bridge_response(action, options=None):
        run_js(f"""void (() => {{
            const frame = document.querySelector('#desk').contentWindow;
            const requestId = crypto.randomUUID();
            window.studioDirectorSmoke = null;
            const receive = (event) => {{
                if (event.source !== frame || event.origin !== location.origin ||
                    event.data?.type !== 'storyai:director-desk:response' ||
                    event.data.payload?.requestId !== requestId) return;
                window.removeEventListener('message', receive);
                window.studioDirectorSmoke = event.data.payload;
            }};
            window.addEventListener('message', receive);
            frame.postMessage({{
                type: 'storyai:director-desk:request',
                payload: {{requestId, action: {json.dumps(action)}, options: {json.dumps(options or {})}}}
            }}, location.origin);
        }})()""")
        return until("window.studioDirectorSmoke", f"No director response to {action}")

    def read_data(action):
        answer = bridge_response(action)
        assert answer["ok"], answer.get("error")
        return answer["data"]

    def set_range(label, value):
        selector = f'input[type=range][aria-label="{label}"]'
        target = f"desk.querySelector({json.dumps(selector)})"
        until(desk(f"Boolean({target})"), f"Missing director slider {label}")
        run_js(desk(f"""(() => {{
            const input = {target};
            const view = desk.defaultView;
            Object.getOwnPropertyDescriptor(view.HTMLInputElement.prototype, 'value').set.call(input, {json.dumps(value)});
            input.dispatchEvent(new view.Event('input', {{bubbles: true}}));
            input.dispatchEvent(new view.Event('change', {{bubbles: true}}));
        }})()"""))

    def pose(label):
        buttons = "Array.from(desk.querySelectorAll('.pose-preset-section .preset-grid button'))"
        match = f"{buttons}.find(button => button.textContent.trim() === {json.dumps(label)})"
        until(desk(f"Boolean({match})"), f"Missing mannequin pose {label}")
        run_js(desk(f"{match}.click()"))

    def rig():
        objects = read_data("project.get")["project"]["objects"]
        character, = (item for item in objects if item["kind"] == "character")
        return character["characterRig"]

    def capture(label):
        for attempt in range(3):
            answer = bridge_response("export.frame", {"quality": "720p", "position": "current"})
            if answer["ok"]:
                break
            # A newly remounted viewport may still be initializing its clean export surface.
            assert attempt < 2 and answer["error"]["message"] in {
                "当前浏览器无法导出成片帧", "成片帧导出器尚未准备好",
            }, (label, answer["error"])
            time.sleep(.25)
        frame = b64decode(answer["data"]["dataUrl"].partition(",")[2], validate=True)
        (output / f"mannequin-{label}.png").write_bytes(frame)
        connected = mannequin_connected_fraction(frame)
        assert connected >= .97, f"{label}: {connected:.1%} of the mannequin silhouette remains attached"
        return frame

    actor = '[role="treeitem"][aria-label="角色01"] .object-select-button'
    tabs = '[aria-label="角色面板标签"] button'
    click(actor)
    click(tabs + ":nth-child(2)")
    pose("T型")
    stand = capture("arms-raised")
    set_range("躯干 · 侧倾 滑杆", "55")
    assert rig()["controls"]["torso.roll"] == 55, "The torso-roll slider did not apply"
    # Raising both arms prevents them from hiding a detached hip in the front camera.
    tilted = capture("side-bend")
    assert tilted != stand, "The viewport did not render the roll setting"

    click('[aria-label="返回首页"]')
    click(".director-home-card.is-active .director-home-card-main")
    until(desk('Boolean(desk.querySelector("canvas"))'), "The saved director project did not reopen")
    assert rig()["controls"]["torso.roll"] == 55, "Reopening lost the stored pose"
    capture("reopened")

    click(actor)
    click(tabs + ":nth-child(2)")
    pose("站立")
    set_range("身体 · 转身 滑杆", "35")
    assert rig()["controls"]["body.yaw"] == 35, "The body turn slider did not apply"
    capture("turn")
    for name, label, preset in (("bow", "鞠躬", "bow"), ("crouch", "蹲下", "crouch")):
        pose(label)
        assert rig()["posePresetId"] == preset
        capture(name)

    click(tabs + ":nth-child(3)")
    click('[aria-label="播放动作 挥手打招呼"]')
    until(desk('Boolean(desk.querySelector(\'[aria-label="暂停人物和物品动作"]\'))'), "The preset did not play")
    set_range("场景动作时间轴", "0.22")
    timeline = read_data("timeline.get")
    assert .20 < timeline["progress"] < .24 and not timeline["playing"], "The timeline did not seek and pause"
    capture("playback-midpoint")
    print("Verified connected built-in mannequin in raised arms, side bend, turn, bow, crouch, reopened pose and action playback", flush=True)


def verify_embedded_director(root, folder, env):
    """Exercise the installed WebView, motion clip editor, and both file handoffs."""
    sys.path.insert(0, str(root))
    from src.director_action_import import import_director_cards

    driver = ("import runpy, sys; "
              "runpy.run_path(sys.argv[1])['drive_native_director'](*sys.argv[2:])")
    for mode, language in (("pose", "zh"), ("action", "en"), ("motion", "en")):
        output = folder / f"director-{mode}"
        output.mkdir()
        browser_args = "--use-angle=swiftshader --enable-unsafe-swiftshader --disable-background-networking"
        webview_env = {**env, "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": browser_args,
                       "LOCALAPPDATA": str(folder / f"WebView-{mode}")}
        result = subprocess.run(
            [sys.executable, "-c", driver, str(Path(__file__).resolve()), str(output), language, mode],
            cwd=root, env=webview_env, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=110 if mode == "motion" else 65,
        )
        assert result.returncode == 0, result.stderr
        print(result.stdout, end="")
        assert (output / "ready").is_file(), "No real protocol initialization was received"
        if mode in {"pose", "motion"}:
            with Image.open(output / "frame.png") as frame:
                frame.load()
                assert frame.format == "PNG" and frame.size == (1280, 720)
                assert any(lo < hi for lo, hi in frame.convert("RGB").getextrema()), "The rendered PNG was blank"
        else:
            cards = import_director_cards(output / "project.json", language="en")
            assert len(cards) == 1 and cards[0]["actor"] == "角色01" and cards[0]["movement"]
        print(f"Verified native offline 3D director {mode} handoff from the packaged upstream renderer", flush=True)


def verify_windows_launcher(root=ROOT):
    if os.name != "nt":
        raise SystemExit("This smoke test requires Windows.")
    with TemporaryDirectory(prefix="comicflow-smoke-", ignore_cleanup_errors=True) as temporary:
        folder = Path(temporary)
        archive = folder / "漫画 交付.zip"
        picture = BytesIO()
        Image.new("RGB", (640, 360), "steelblue").save(picture, format="PNG")
        with ZipFile(archive, "w") as package:
            package.writestr("README.txt", "Synthetic desktop smoke fixture.")
            package.writestr("SB01/storyboard_2panel.png", picture.getvalue())
            package.writestr("SB01/details.png", picture.getvalue())
            package.writestr("SB01/SB01_shot_details.txt", (
                "分镜 SB01-01\n动作：等待\n分镜 SB01-02\n动作：开门\n场景局部对应表：\n"
                "- SB01-01 | details.png | 局部01 | 走廊 | 等待\n"
                "- SB01-02 | details.png | 局部02 | 走廊 | 开门\n"
            ))
            package.writestr("SB01/SD2_prompt.txt", "分镜编号：SB01-01\n动作：等待\n分镜编号：SB01-02\n动作：开门\n")
        validator = folder / "validator.py"
        validator.write_text(
            'print("WARNING: SB01/SB01_shot_details.txt: shot SB01-01: smoke fixture")\n'
            'print("RESULT: 0 error(s), 1 warning(s)")\n', encoding="utf-8",
        )
        (folder / "中文校验.py").write_text(
            'print("WARNING: SB01/SB01_shot_details.txt: shot SB01-01: Chinese mode validator")\n'
            'print("RESULT: 0 error(s), 1 warning(s)")\n', encoding="utf-8",
        )
        (folder / "sitecustomize.py").write_text(
            "import os, sys\n"
            "if '-m' in getattr(sys, 'orig_argv', []) and 'src.windows_launcher' in sys.orig_argv:\n"
            "    import runpy\n"
            "    sys.path.insert(0, os.getcwd())\n"
            "    runpy.run_path(os.environ['COMICFLOW_SMOKE_HELPER'])['run_inside_launcher']()\n",
            encoding="utf-8",
        )
        env = {
            **os.environ, "COMICFLOW_STORYBOARD_VALIDATOR": str(validator), "COMICFLOW_SMOKE_ZIP": str(archive),
            "COMICFLOW_SMOKE_HELPER": str(Path(__file__).resolve()), "PYTHONPATH": str(folder), "PYTHONUTF8": "1",
            "LOCALAPPDATA": str(folder / "AppData"),
        }
        env.pop("COMICFLOW_CHINESE_STORYBOARD_VALIDATOR", None)
        verify_embedded_director(root, folder, env)
        for mode, argument in (("empty", ""), ("drop-argument", f' "{archive}"'), ("file-only", f' "{archive}"'),
                               ("a-layout-125", ""), ("a-layout-150", ""),
                               ("mode-switch", f' "{archive}"'), ("ui-language-restore", f' "{archive}"'),
                               ("api-settings", f' "{archive}"'), ("new-tools", f' "{archive}"'),
                               ("production-handoff", f' "{archive}"'), ("production-workspace", f' "{archive}"'),
                               ("storyboard-guide", f' "{archive}"'), ("workbench-guide", f' "{archive}"'),
                               ("workbench-bridges", f' "{archive}"'), ("job-recovery", f' "{archive}"'),
                               ("image-entry", ""),
                               ("action-sequence", f' "{archive}"'), ("task-navigation", f' "{archive}"'),
                               ("dialogue-blocking", f' "{archive}"'),
                               ("ecommerce", f' "{archive}"'),
                               ("batch-center", f' "{archive}"'),
                               ("batch-file", f' "{folder / "制片-batch-center.cfbatch"}"')):
            launch_env = {**env, "COMICFLOW_SMOKE_MODE": mode}
            if mode in {"file-only", "mode-switch", "production-workspace", "storyboard-guide", "workbench-guide"}:
                launch_env.pop("COMICFLOW_STORYBOARD_VALIDATOR")
            if mode.startswith("a-layout-") or mode in {
                "task-navigation", "dialogue-blocking", "production-workspace", "storyboard-guide", "workbench-guide",
                "workbench-bridges", "job-recovery",
            }:
                launch_env["LOCALAPPDATA"] = str(folder / f"AppData-{mode}")
            completed = subprocess.run(
                f'cmd.exe /d /c .\\Comic-Sequence-Studio.bat{argument}', cwd=root, env=launch_env,
                stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace", timeout=35,
            )
            print(completed.stdout, end="")
            assert completed.returncode == 0 and "COMICFLOW_GUI_OK" in completed.stdout, completed.stderr
            print(f"Verified {mode} launch and Tk window actions")

        project = folder / "制片-mode-switch.cfproject"
        env["COMICFLOW_SMOKE_MODE"] = "shell-project"
        env["COMICFLOW_SMOKE_PROJECT"] = str(project)
        previous = os.environ.copy()
        try:
            os.environ.update(env)
            os.environ.pop("COMICFLOW_STORYBOARD_VALIDATOR", None)
            os.environ.pop("COMICFLOW_CHINESE_STORYBOARD_VALIDATOR", None)
            os.startfile(str(root / "Comic-Sequence-Studio.bat"), "open", subprocess.list2cmdline([str(project)]), str(root))
            deadline = time.monotonic() + 30
            marker = project.with_suffix(".status")
            while time.monotonic() < deadline:
                if marker.is_file() and (value := marker.read_text(encoding="utf-8")):
                    assert value == "COMICFLOW_GUI_OK", value
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("Windows shell did not open the .cfproject in Tk")
        finally:
            os.environ.clear()
            os.environ.update(previous)
        print("Verified Windows shell reopened the Chinese .cfproject and restored its mode")


if __name__ == "__main__":
    verify_windows_launcher(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT)
