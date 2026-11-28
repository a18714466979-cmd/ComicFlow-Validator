"""Exercise the batch file and real Tk widgets with a synthetic local ZIP."""

import faulthandler
import json
import os
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_TAB, ECOMMERCE_TAB, REVIEW_TAB, API_TAB, TUTORIAL_TAB = range(5)


def make_ecommerce_video(folder):
    """Make a local vertical reference with hard cuts at 1 and 2 seconds."""
    from src.ecommerce_video import resolve_ffmpeg

    target = folder / "竖屏广告参考.mp4"
    colors = ("black", "white", "black")
    inputs = [value for color in colors for value in ("-f", "lavfi", "-i", f"color=c={color}:s=144x256:r=24:d=1")]
    subprocess.run(
        [resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", *inputs,
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[out]", "-map", "[out]",
         "-c:v", "mpeg4", "-threads", "2", "-pix_fmt", "yuv420p", "-y", str(target)],
        check=True, timeout=15, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return target


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

    def page_at(root, index):
        navigation = next(walk(root, ttk.Notebook))
        return navigation.nametowidget(navigation.tabs()[index])

    def show_page(root, index):
        navigation = next(walk(root, ttk.Notebook))
        navigation.select(index)
        root.update_idletasks()
        return navigation.nametowidget(navigation.select())

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
                panel = next((w for w in walk(self, tk.Toplevel) if w.title() == "批量制作中心"), None)
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
            if mode == "batch-center":
                self.inspect_batch_center()
                return
            if mode == "ecommerce":
                self.inspect_ecommerce()
                return
            if mode == "production-handoff":
                self.inspect_production_handoff()
                return
            if mode == "mode-switch":
                self.inspect_mode_switch(validator)
                return
            if mode == "ui-language-restore":
                assert self.title() == "ComicFlow Storyboard Workbench"
                click(self, "中文 / English")
                assert self.title() == "ComicFlow 漫剧制片工作台"
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
            from src.production_project import ProductionProject

            def input_field(scope, caption):
                label = next(w for w in walk(scope, ttk.Label) if w.cget("text") == caption)
                return label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]

            def enter(scope, caption, value):
                field = input_field(scope, caption)
                field.delete(0, "end")
                field.insert(0, value)
                return field

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
            click(text, "保存本次设置")

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
            click(vision, "保存本次设置")

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
            click(image, "保存本次设置")

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
                assert options["title"] == "打开已保存的 ComicFlow 项目（.cfproject）"
                assert options["filetypes"] == (("ComicFlow 单组项目", "*.cfproject"),)
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

                def check_vision():
                    dialog = next(walk(self, tk.Toplevel))
                    assert not input_field(dialog, "审图重点（可选）").get()
                    with patch.object(messagebox, "showinfo") as info:
                        click(dialog, "查看固定审图规则")
                        title, instructions = info.call_args.args
                        assert title == "查看固定审图规则" and "英文影片制作 v14.10.4" in instructions
                    check_panel(self, "模型 ID", "image-review-test", key)

                self.after(60, check_vision)
                click(self, "AI 辅助看图")
                saved = project_path.read_text(encoding="utf-8")
                assert key not in saved and "synthetic-image-key" not in saved
                appdata = Path(os.environ["LOCALAPPDATA"]) / "ComicFlow"
                assert all(key not in path.read_text(encoding="utf-8")
                           and "synthetic-image-key" not in path.read_text(encoding="utf-8")
                           for path in appdata.iterdir() if path.is_file())
                print("Verified all API settings routes, scoped key reuse, and no credential writes", flush=True)
                print("COMICFLOW_GUI_OK", flush=True)
                self.destroy()

            self.after(120, check_project_tools)

        def inspect_tutorial(self, navigation):
            from src import workbench_tutorial

            self.geometry("900x700")
            tutorial = show_page(self, TUTORIAL_TAB)
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
            show_page(self, PRODUCTION_TAB)
            click(self, "剧本创作")
            editor = next(walk(self, tk.Toplevel))
            title_box = next(walk(editor, ttk.Entry))
            title_box.delete(0, "end")
            title_box.insert(0, title)
            left = next(walk(editor, tk.Text))
            left.insert("1.0", body)

            def choose_project(cancel=False):
                choice = next(walk(editor, tk.Toplevel))
                assert choice.title() == "将剧本带入分镜"
                if cancel:
                    click(choice, "取消")
                else:
                    click(choice, "加入已有项目")

            def fake_shots(settings, instructions, payload):
                data = json.loads(payload)
                assert data["approved_source"]["version"] == "R1"
                assert "值班员拿钥匙。" in data["approved_source"]["lines"].values()
                return TextReply('{"shots":[{"line_start":1,"line_end":3,'
                                 '"fields":{"画面/事件":"值班员拿起钥匙","人物站位":"门右侧"}}]}',
                                 "fixture-shot-handoff")

            def inspect_project():
                project = next(walk(editor, tk.Toplevel))
                tabs = next(walk(project, ttk.Notebook))
                assert tabs.tab(tabs.select(), "text") == "镜头清单"
                assert any(w.get() == f"{title} · R1" for w in walk(project, ttk.Combobox))
                self.after(90, lambda: use_draft(project))
                click(project, "AI 拆分镜")
                project.destroy()

            def use_draft(project):
                tool = next(walk(project, tk.Toplevel))
                tabs = next(walk(tool, ttk.Notebook))
                assert tabs.tab(tabs.select(), "text") == "文本模型与历史"
                for caption in ("文本模型 ID", "API Key"):
                    label = next(widget for widget in walk(tool, ttk.Label) if widget.cget("text") == caption)
                    entry = label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0]
                    entry.insert(0, "synthetic")
                click(tool, "调用模型起草")
                self.after(100, lambda: accept_shots(tool))

            def accept_shots(tool):
                if not ProductionProject.open(project_path).text_drafts:
                    self.after(100, lambda: accept_shots(tool))
                    return
                click(tool, "采纳已选建议")
                saved = ProductionProject.open(project_path)
                assert len(saved.shots) == 1 and saved.shots[0].source == base.id
                self.after(75, lambda: inspect_assets(tool, saved.shots[0].id))
                click(tool, "下一步：分析资产")
                tool.destroy()

            def inspect_assets(tool, shot_id):
                analysis = next(walk(tool, tk.Toplevel))
                assert analysis.title() == "资产分析"
                before = project_path.read_bytes()
                original_source = next(walk(analysis, tk.Text))
                assert original_source.get("1.0", "end-1c") == body
                assert original_source.cget("state") == "disabled"

                def inspect_request():
                    preview = next(walk(analysis, tk.Toplevel))
                    editor = next(walk(preview, tk.Text))
                    assert editor.cget("state") == "disabled"
                    content = editor.get("1.0", "end-1c")
                    policy, material = content.split("\n\n用户资料\n", 1)
                    assert policy.startswith("软件锁定规则\n") and "英文影片制作 v14.10.4" in policy
                    assert shot_id not in policy and shot_id in material
                    assert shot_id in content and "SB01-01" in content and "值班员拿起钥匙" in content
                    assert alternate not in content and '"3": "值班员拿钥匙。"' in content
                    preview.destroy()

                self.after(60, inspect_request)
                click(analysis, "预览发送内容")
                click(analysis, "关闭")
                assert project_path.read_bytes() == before

            old_confirm, old_request, old_picker = messagebox.askyesno, drafting_dialog.request_text, filedialog.askopenfilename
            try:
                messagebox.askyesno = lambda *_args, **_kwargs: True
                drafting_dialog.request_text = fake_shots
                filedialog.askopenfilename = lambda **_kwargs: str(project_path)
                self.after(75, lambda: choose_project(cancel=True))
                click(editor, "用左侧稿件拆分镜")
                assert project_path.read_bytes() == original and left.get("1.0", "end-1c") == body
                self.after(75, choose_project)
                self.after(220, inspect_project)
                click(editor, "用左侧稿件拆分镜")
                assert left.get("1.0", "end-1c") == body
                click(editor, "关闭")
            finally:
                messagebox.askyesno, drafting_dialog.request_text, filedialog.askopenfilename = old_confirm, old_request, old_picker
            print("Verified script-to-shots-to-assets with the exact approved revision, shot evidence and cancellation", flush=True)
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
                library = next(w for w in walk(workbench, tk.Toplevel) if w.title() == "动作参考库")
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
                library = next(w for w in walk(workbench, tk.Toplevel) if w.title() == "动作参考库")

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
                assert (path, mode, language) == (project_path, "action", "zh")
                callback(director_path)
            gallery = show_page(self, PRODUCTION_TAB)
            click(gallery, "人物动作编排")
            picker = next(w for w in walk(self, tk.Toplevel) if w.title() == "人物动作编排")
            with patch.object(filedialog, "askopenfilename", return_value=str(project_path)):
                click(picker, "打开单组项目")

            def inspect_sequence():
                workbench = next((w for w in walk(self, tk.Toplevel) if w.title() == "人物动作编排"), None)
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
                    editor = next(walk(workbench, tk.Toplevel))
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
                    handoff = next(walk(workbench, tk.Toplevel))
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
                workbench.tk.eval(workbench.protocol("WM_DELETE_WINDOW"))
                self.after_idle(self.destroy)

            self.after(60, inspect_sequence)

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

            def batch_panel(english):
                expected = "Batch production center" if english else "批量制作中心"
                return next((panel for panel in walk(self, tk.Toplevel) if panel.title() == expected), None)

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

            def measure(window, buttons):
                window.update_idletasks()
                left, top = window.winfo_rootx(), window.winfo_rooty()
                right, bottom = left + window.winfo_width(), top + window.winfo_height()
                rows = {}
                for button in buttons:
                    caption = button.cget("text")
                    assert button.winfo_ismapped(), caption
                    x, y = button.winfo_rootx(), button.winfo_rooty()
                    assert left <= x and x + button.winfo_width() <= right, (caption, x, right)
                    assert top <= y and y + button.winfo_height() <= bottom, (caption, y, bottom)
                    assert button.winfo_width() >= button.winfo_reqwidth(), (caption, button.winfo_width(), button.winfo_reqwidth())
                    assert button.winfo_height() >= button.winfo_reqheight(), (caption, button.winfo_height(), button.winfo_reqheight())
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
                panel = batch_panel(english)
                assert panel is not None
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
                assert export.winfo_ismapped() and export.instate(["disabled"])
                with patch.object(filedialog, "asksaveasfilename") as choose:
                    export.invoke()
                    assert not choose.called

                def batch_steps():
                    return [named(panel, ttk.Button, "step_" + name) for name in step_names]

                layout(panel, batch_steps, lambda: open_group_review(english, production, panel))

            def open_group_review(english, production, panel):
                caption = "Open group for review" if english else "打开本组复核"

                def editor_for_selected_group():
                    title = "ComicFlow Group Production" if english else "ComicFlow 单组制片"
                    for editor in walk(panel, tk.Toplevel):
                        if editor.title() == title:
                            values = {field.get() for field in walk(editor, ttk.Entry)}
                            if {"EP04", "SB02"} <= values:
                                return editor
                    return None

                def close_editor(editor):
                    with patch.object(messagebox, "askyesnocancel", return_value=False):
                        editor.tk.eval(editor.protocol("WM_DELETE_WINDOW"))
                    close_caption = "Close" if english else "关闭"
                    after_ready(lambda: any(control.cget("text") == close_caption and control.instate(["!disabled"])
                                            for control in walk(panel, ttk.Button)),
                                lambda _ready: finish(english, production, panel),
                                "Batch review did not resume after closing the group")

                after_ready(editor_for_selected_group, close_editor, "A review did not open selected batch group SB02")
                click(panel, caption)

            def finish(english, production, panel):
                click(panel, "Close" if english else "关闭")
                if not english:
                    click(self, "中文 / English")
                    start_language(True)
                    return
                resume = named(production, ttk.Button, "a_home_resume")
                resume.invoke()
                reopened = batch_panel(True)
                assert reopened is not None

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

            def titled(label):
                return next((panel for panel in walk(self, tk.Toplevel) if panel.title() == label), None)

            def named(panel, kind, name):
                return next(widget for widget in walk(panel, kind) if widget.winfo_name() == name)

            def imported(panel, count):
                combo = named(panel, ttk.Combobox, "episode")
                return len(self.tk.splitlist(combo.cget("values"))) == count

            def click_import(panel, paths):
                with patch.object(filedialog, "askopenfilenames", return_value=tuple(map(str, paths))):
                    click(panel, "导入剧本")

            def create(panel):
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
                wait_for(lambda: titled("批量制作中心"), reopen, "batch center did not reopen")
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
                    wait_for(lambda: titled("ComicFlow 单组制片"), finish, "could not open group from batch")
                    click(panel, "打开单组制片")

                wait_for(locate_line, inspect_group, "could not trace episode 3 dialogue to its group")

            def finish(group_editor):
                def loaded():
                    entries = {widget.get() for widget in walk(group_editor, ttk.Entry)}
                    return {"EP03", "SB01"} <= entries
                def close_editor(_ok):
                    with patch.object(messagebox, "askyesnocancel", return_value=False):
                        group_editor.tk.eval(group_editor.protocol("WM_DELETE_WINDOW"))
                    self.after(100, prepare_queue)

                wait_for(loaded, close_editor, "incorrect group opened from source trace")

            def prepare_queue():
                panel = titled("批量制作中心")
                def enabled(label):
                    return any(b.cget("text") == label and b.instate(["!disabled"]) for b in walk(panel, ttk.Button))

                def approve(_ready):
                    click(panel, "确认本集规划")
                    wait_for(lambda: BatchWorkspace.open(workspace_path).plan_approved("EP03") and enabled("本集加入队列"),
                             enqueue, "episode plan approval was not persisted")

                def enqueue(_ready):
                    show_page(panel, 2)
                    click(panel, "本集加入队列")
                    jobs = named(panel, ttk.Treeview, "jobs")
                    wait_for(lambda: jobs.get_children(), lambda _rows: preflight(panel),
                             "approved episode tasks did not enter the queue")

                wait_for(lambda: enabled("确认本集规划"), approve, "batch editor did not resume")

            def preflight(panel):
                workspace = BatchWorkspace.open(workspace_path)
                queue = BatchQueue(workspace)
                assert queue.jobs() and queue.spent() == 0
                assert all(row["episode"] == "EP03" for row in queue.jobs())
                show_page(panel, 3)
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

            wait_for(lambda: titled("批量制作中心"), create, "batch center did not open")
            click(gallery, "批量制作中心")

        def inspect_ecommerce(self):
            from src.ecommerce_delivery import PRODUCT_FILE, label_board_sheet
            from src.ecommerce_project import EcommerceProject, EcommerceShot, render_shots

            page = show_page(self, ECOMMERCE_TAB)
            navigation = next(walk(self, ttk.Notebook))
            assert navigation.tab(navigation.select(), "text") == "电商信息流视频复刻"
            video = make_ecommerce_video(project_path.parent)
            product = project_path.with_name("产品照片 正面.png")
            photo = Image.new("RGB", (256, 256), "#f1ded2")
            paint = ImageDraw.Draw(photo)
            paint.rounded_rectangle((75, 48, 180, 215), radius=16, fill="#804086")
            paint.text((100, 111), "CF", fill="white")
            photo.save(product)
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
                    panel = next((window for window in walk(self, tk.Toplevel) if window.title() == title), None)
                    canvas = next(walk(panel, tk.Canvas), None) if panel else None
                    if canvas is None or not canvas.winfo_viewable() or not canvas.find_all():
                        self.after(50, lambda: confirm_image(title, done))
                        return
                    click(panel, "确认使用这张图")
                    done()

                def bind_images(iterator):
                    selected = next(iterator, None)
                    if selected is None:
                        click(page, "下一步：提示词与交付")
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
                dialog = next(window for window in walk(self, tk.Toplevel) if window.title() == "交付完成")
                click(dialog, "关闭")
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
                assert (path, mode, language) == (project_path, "pose", "zh")
                callback(director_png)

            show_page(self, PRODUCTION_TAB)
            click(self, "剧本创作")
            script = next(walk(self, tk.Toplevel))
            assert script.title() == "剧本创作"
            next(walk(script, tk.Text)).insert("1.0", "场景一：灯亮了。")
            filedialog.asksaveasfilename = lambda **_kwargs: str(draft)
            click(script, "另存左侧稿件")
            assert draft.read_text(encoding="utf-8") == "场景一：灯亮了。"
            click(script, "关闭")
            click(self, "资产分析")
            analysis = next(walk(self, tk.Toplevel))
            assert analysis.title() == "资产分析"
            filedialog.askopenfilename = lambda **_kwargs: str(draft)
            click(analysis, "导入 TXT / Markdown")
            assert next(walk(analysis, tk.Text)).get("1.0", "end-1c").strip() == "场景一：灯亮了。"
            click(analysis, "关闭")
            print("Verified offline script drafting and the asset analysis entry", flush=True)

            ProductionProject("服装动作试用", "EP01", "SB01").save(project_path)
            def open_reference(button):
                filedialog.askopenfilename = lambda **_kwargs: str(project_path)
                click(self, button)
                self.after(150, lambda: use_reference(button))

            def use_reference(button):
                project = next(walk(self, tk.Toplevel))
                chooser = next(walk(project, tk.Toplevel))
                costume = button == "角色服装设计"
                assert chooser.title() == button
                if costume:
                    from src.reference_tools_dialog import COSTUMES

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
                else:
                    with patch.object(reference_tools_dialog, "open_director", side_effect=receive_still):
                        click(chooser, "打开内置 3D 导演台")
                self.after(80, lambda: check_image_job(project, costume))
                click(chooser, "使用参考图进入生图")
                project.destroy()
                if costume:
                    open_reference("角色动作设计")
                else:
                    verify_reference_files()

            def check_image_job(project, costume):
                image_job = next(walk(project, tk.Toplevel))
                assert image_job.title() == "ComicFlow 图像制片"
                assert any(widget.get() == "参考图生图" for widget in walk(image_job, ttk.Combobox))
                refs = next(walk(image_job, tk.Listbox))
                assert len(refs.curselection()) == 1
                def preview():
                    window = next(walk(image_job, tk.Toplevel))
                    payload = next(walk(window, tk.Text)).get("1.0", "end-1c")
                    assert ("仅指定服装" if costume else "仅指定人物动作") in payload
                    window.destroy()

                self.after(80, preview)
                click(image_job, "预览本次发送")
                image_job.destroy()

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
            assert self.title() == "ComicFlow Storyboard Workbench"
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
            original_picker = filedialog.askopenfilename
            filedialog.askopenfilename = lambda **_kwargs: str(project_path)
            routes = iter((
                ("Shot planning", "Shot list", "", ""),
                ("Approved images", "Approved images", "", ""),
                ("Layout & handoff", "Approved images", "ComicFlow Layout & Handoff", "16:9 layout"),
                ("Prompt drafting", "Shot list", "ComicFlow Text Production", "Text model & history"),
                ("Asset image generation", "Approved images", "ComicFlow Image Production", "New image job"),
                ("Storyboard generation", "Approved images", "ComicFlow Image Production", "New image job"),
                ("Package storyboard group", "Text, layout & delivery", "", ""),
            ))

            def next_route():
                route = next(routes, None)
                if route is None:
                    finish()
                    return
                print(f"Opening home route {route[0]}", flush=True)
                click(self, route[0])
                self.after(120, lambda: verify_view(route))

            def verify_view(route):
                shortcut, tab_name, modal_name, modal_tab = route
                panel = next(walk(self, tk.Toplevel), None)
                tool = next(walk(panel, tk.Toplevel), None) if panel else None
                image_route = shortcut in {"Asset image generation", "Storyboard generation"}
                if panel is None or (modal_name and tool is None) or (image_route and not tool.winfo_viewable()):
                    self.after(25, lambda: verify_view(route))
                    return
                tabs = next(walk(panel, ttk.Notebook))
                assert tabs.tab(tabs.select(), "text") == tab_name
                if modal_name:
                    tool_tabs = next(walk(tool, ttk.Notebook))
                    assert tool.title() == modal_name and tool_tabs.tab(tool_tabs.select(), "text") == modal_tab
                    if shortcut == "Prompt drafting":
                        assert any(w.get() == "SD2 prompts" for w in walk(tool, ttk.Combobox))
                    if shortcut == "Storyboard generation":
                        assert any(w.get() == "Storyboard" for w in walk(tool, ttk.Combobox))
                    tool.destroy()
                self.after(30, lambda: close_route(panel))

            def close_route(panel):
                panel.destroy()
                next_route()

            def verify_repair():
                panel = next(walk(self, tk.Toplevel))
                assert panel.title() == "ComicFlow Assets & Repairs"
                panel.destroy()

            def finish():
                assert ProductionProject.open(project_path).rules == CHINESE
                show_page(self, REVIEW_TAB)
                self.after(80, verify_repair)
                click(self, "Assets & repairs")
                filedialog.askopenfilename = original_picker
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

            show_page(self, PRODUCTION_TAB)
            with patch.object(filedialog, "askopenfilename", return_value="") as picker:
                click(self, "资产图生成")
                assert picker.call_args.kwargs["parent"] is self
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
            opening.start()
            write = forbidden_save.start()
            with patch.object(filedialog, "askopenfilename", return_value=str(project_path)) as picker:
                click(self, "资产图生成")
                assert picker.call_args.kwargs["parent"] is self
            parent = next(walk(self, tk.Toplevel))

            def allow_read():
                if not reading.is_set():
                    self.after(25, allow_read)
                    return
                variables = (widget.cget("textvariable") for widget in walk(parent, ttk.Label))
                assert any("正在打开项目" in self.getvar(value) for value in variables if value)
                assert next(walk(parent, tk.Toplevel), None) is None
                release.set()
                self.after(25, inspect_loaded)

            def inspect_loaded():
                panel = next(walk(parent, tk.Toplevel), None)
                if panel is None or not panel.winfo_viewable() or self.grab_current() is not panel:
                    self.after(25, inspect_loaded)
                    return
                assert panel.title() == "ComicFlow 图像制片"
                assert project_path.read_bytes() == original_bytes and not write.called
                tabs = next(walk(panel, ttk.Notebook))
                tabs.select(1)
                assert any("历史图像任务的记录不完整" in widget.get("1.0", "end")
                           for widget in walk(panel, tk.Text))
                panel.destroy()
                opening.stop()
                forbidden_save.stop()
                print("Verified responsive direct asset opening with a delayed read and incomplete job history")
                print("COMICFLOW_GUI_OK", flush=True)
                self.after_idle(self.destroy)

            self.after(25, allow_read)

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
            deadline = time.monotonic() + 26

            def until(script, message):
                while time.monotonic() < deadline:
                    if window.run_js(script):
                        return
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
        run_window(Path(output), "windows-smoke", language, mode)
    if errors:
        raise RuntimeError(errors[0])


def verify_embedded_director(root, folder, env):
    """Exercise the real installed WebView, its renderer, and both file handoffs."""
    sys.path.insert(0, str(root))
    from src.director_action_import import import_director_cards

    driver = ("import runpy, sys; "
              "runpy.run_path(sys.argv[1])['drive_native_director'](*sys.argv[2:])")
    for mode, language in (("pose", "zh"), ("action", "en")):
        output = folder / f"director-{mode}"
        output.mkdir()
        browser_args = "--use-angle=swiftshader --enable-unsafe-swiftshader --disable-background-networking"
        webview_env = {**env, "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": browser_args,
                       "LOCALAPPDATA": str(folder / f"WebView-{mode}")}
        result = subprocess.run(
            [sys.executable, "-c", driver, str(Path(__file__).resolve()), str(output), language, mode],
            cwd=root, env=webview_env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert (output / "ready").is_file(), "No real protocol initialization was received"
        if mode == "pose":
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
            "import sys\n"
            "if '-m' in getattr(sys, 'orig_argv', []) and 'src.windows_launcher' in sys.orig_argv:\n"
            "    import runpy, os\n"
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
                               ("production-handoff", f' "{archive}"'), ("image-entry", ""),
                               ("action-sequence", f' "{archive}"'), ("ecommerce", f' "{archive}"'),
                               ("batch-center", f' "{archive}"'),
                               ("batch-file", f' "{folder / "制片-batch-center.cfbatch"}"')):
            launch_env = {**env, "COMICFLOW_SMOKE_MODE": mode}
            if mode in {"file-only", "mode-switch"}:
                launch_env.pop("COMICFLOW_STORYBOARD_VALIDATOR")
            if mode.startswith("a-layout-"):
                launch_env["LOCALAPPDATA"] = str(folder / f"AppData-{mode}")
            completed = subprocess.run(
                f'cmd.exe /d /c .\\ComicFlow-Windows.bat{argument}', cwd=root, env=launch_env,
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
            os.startfile(str(root / "ComicFlow-Windows.bat"), "open", subprocess.list2cmdline([str(project)]), str(root))
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
