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
from zipfile import ZipFile

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


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

    def fail(reason):
        print(reason, file=sys.stderr, flush=True)
        faulthandler.dump_traceback()
        if mode == "shell-project":
            marker.write_text(str(reason), encoding="utf-8")
        os._exit(10)

    class SmokeWindow(tk.Tk):
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
            field, validator, *_ = walk(self, ttk.Entry)
            assert field.get() == ("" if mode == "empty" else archive), field.get()
            if mode == "api-settings":
                self.inspect_api_settings()
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
                assert not validator.get()
                click(self, "开始验收")
                self.after(100, self.inspect_file_only)
                return
            if mode == "empty":
                click(self, "浏览")
                assert field.get() == archive
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
            click(self, "API 设置")
            settings = next(walk(self, tk.Toplevel))
            assert settings.title() == "ComicFlow API 设置"
            tabs = next(walk(settings, ttk.Notebook))
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
            click(settings, "关闭")

            click(self, "中文 / English")
            click(self, "API settings")
            settings = next(walk(self, tk.Toplevel))
            tabs = next(walk(settings, ttk.Notebook))
            assert [tabs.tab(i, "text") for i in range(3)] == ["Text drafting", "AI image review", "Image generation"]
            click(settings, "Close")
            click(self, "中文 / English")

            ProductionProject("API smoke test", "EP01", "SB01").save(project_path)
            original_picker = filedialog.askopenfilename
            filedialog.askopenfilename = lambda **_kwargs: str(project_path)
            click(self, "打开项目")

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
                click(self, "开始验收")
                self.after(100, check_review)

            def check_review():
                selector = next(walk(self, ttk.Combobox))
                if not selector["values"]:
                    self.after(100, check_review)
                    return
                selector.set("SB01/storyboard_2panel.png")
                selector.event_generate("<<ComboboxSelected>>")
                self.after(60, lambda: check_panel(self, "模型 ID", "image-review-test", key))
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

        def inspect_mode_switch(self, validator):
            from src.production_project import ProductionProject
            from src.production_rules import CHINESE

            english, chinese = walk(self, ttk.Radiobutton)
            assert english.cget("text") == "英文影片制作" and english.instate(["selected"])
            assert chinese.cget("text") == "中文影片制作"
            scripts = Path(archive).with_name("validator.py"), Path(archive).with_name("中文校验.py")
            select_script = next(widget for widget in walk(self, ttk.Button) if widget.cget("text") == "浏览"
                                 and int(widget.grid_info().get("row", -1)) == 1)
            for choice, script in zip((english, chinese), scripts):
                choice.invoke()
                assert not validator.get()
                filedialog.askopenfilename = lambda **_kwargs: str(script)
                select_script.invoke()
                assert validator.get() == str(script)
            english.invoke()
            assert Path(validator.get()).resolve() == scripts[0].resolve()
            chinese.invoke()
            assert Path(validator.get()).resolve() == scripts[1].resolve()

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
            assert next(walk(self, ttk.Entry)).get() == archive
            self.geometry("900x700")
            self.update_idletasks()
            home_actions = ("Plan shots", "Prepare assets", "Arrange storyboard", "Write prompts",
                            "Review & export", "Assets & repairs", "Validate ZIP")
            for name in home_actions:
                button = next(w for w in walk(self, ttk.Button) if w.cget("text") == name)
                assert button.winfo_viewable() and button.winfo_rooty() + button.winfo_height() <= self.winfo_rooty() + 700
            print("Verified bilingual home controls at the minimum window size", flush=True)
            original_picker = filedialog.askopenfilename
            filedialog.askopenfilename = lambda **_kwargs: str(project_path)
            routes = iter((
                ("Plan shots", "Shot list", "", ""),
                ("Prepare assets", "Approved images", "", ""),
                ("Arrange storyboard", "Approved images", "ComicFlow Layout & Handoff", "16:9 layout"),
                ("Write prompts", "Shot list", "ComicFlow Text Production", "Text model & history"),
                ("Review & export", "Text, layout & delivery", "", ""),
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
                panel = next(walk(self, tk.Toplevel))
                tabs = next(walk(panel, ttk.Notebook))
                assert tabs.tab(tabs.select(), "text") == tab_name
                if modal_name:
                    tool = next(walk(panel, tk.Toplevel))
                    tool_tabs = next(walk(tool, ttk.Notebook))
                    assert tool.title() == modal_name and tool_tabs.tab(tool_tabs.select(), "text") == modal_tab
                    if shortcut == "Write prompts":
                        assert any(w.get() == "SD2 prompts" for w in walk(tool, ttk.Combobox))
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
                self.after(80, verify_repair)
                click(self, "Assets & repairs")
                filedialog.askopenfilename = original_picker
                click(self, "中文 / English")
                assert chinese.cget("text") == "中文影片制作" and chinese.instate(["selected"])
                print("Verified five home routes and bilingual UI independent from production rules", flush=True)
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
            path = project_path.with_name("中文对白制片.cfproject")
            example.save(path)
            filedialog.askopenfilename = lambda **_kwargs: str(path)
            click(dialog, "打开单组项目")

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
            table = next(walk(self, ttk.Treeview))
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
            table = next(walk(self, ttk.Treeview))
            if not table.get_children():
                self.after(100, self.inspect_result)
                return
            assert len(table.get_children()) == 1
            assert table.item("0", "values")[1:4] == ("SB01", "SB01-01", "SB01_shot_details.txt")
            selector = next(walk(self, ttk.Combobox))
            table.selection_set("0")
            self.update()
            assert selector.get() == "SB01/SB01_shot_details.txt"
            selector.set("SB01/storyboard_2panel.png")
            selector.event_generate("<<ComboboxSelected>>")
            self.update()
            assert any(widget.cget("image") for widget in walk(self, ttk.Label))
            self.after(50, self.inspect_shot_dialog)
            click(self, "逐格复核")
            click(self, "对白与九图预算")
            next(walk(self, tk.Toplevel)).destroy()
            self.after(50, self.inspect_asset_dialog)
            click(self, "资产与返修")
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


def verify_windows_launcher(root=ROOT):
    if os.name != "nt":
        raise SystemExit("This smoke test requires Windows.")
    with TemporaryDirectory(prefix="comicflow-smoke-") as temporary:
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
        for mode, argument in (("empty", ""), ("drop-argument", f' "{archive}"'), ("file-only", f' "{archive}"'),
                               ("mode-switch", f' "{archive}"'), ("ui-language-restore", f' "{archive}"'),
                               ("api-settings", f' "{archive}"')):
            env["COMICFLOW_SMOKE_MODE"] = mode
            if mode == "file-only":
                env.pop("COMICFLOW_STORYBOARD_VALIDATOR")
            completed = subprocess.run(
                f'cmd.exe /d /c .\\ComicFlow-Windows.bat{argument}', cwd=root, env=env,
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
