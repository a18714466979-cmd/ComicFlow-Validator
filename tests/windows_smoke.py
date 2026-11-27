"""Exercise the batch file and real Tk widgets with a synthetic local ZIP."""

import os
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


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
        button = next(widget for widget in walk(root, ttk.Button) if widget.cget("text") == title)
        assert button.instate(["!disabled"]), title
        button.invoke()

    def fail(reason):
        print(reason, file=sys.stderr, flush=True)
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
                assert tabs.tab(1, "state") == "normal" and tabs.tab(3, "state") == "disabled"
                assert any(widget.instate(["selected"]) for widget in walk(self, ttk.Radiobutton)
                           if widget.cget("text") == "中文制作")
                assert any("中文制作 · v14.8.8" in self.getvar(variable)
                           for label in walk(dialog, ttk.Label) if (variable := label.cget("textvariable")))
                self.destroy()
                marker.write_text("COMICFLOW_GUI_OK", encoding="utf-8")
                return
            field, validator, *_ = walk(self, ttk.Entry)
            assert field.get() == ("" if mode == "empty" else archive), field.get()
            if mode == "mode-switch":
                self.inspect_mode_switch(validator)
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

        def inspect_mode_switch(self, validator):
            from src.production_project import ProductionProject
            from src.production_rules import CHINESE

            english, chinese = walk(self, ttk.Radiobutton)
            assert english.cget("text") == "英文制作" and english.instate(["selected"])
            assert chinese.cget("text") == "中文制作"
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
            assert tabs.tab(3, "state") == "disabled"
            previous = project_path.with_name("旧英文制片.cfproject")
            ProductionProject("旧英文制片", "EP01", "SB01").save(previous)
            for path, choice, script, state in ((previous, english, scripts[0], "normal"),
                                                (project_path, chinese, scripts[1], "disabled")):
                filedialog.askopenfilename = lambda **_kwargs: str(path)
                click(dialog, "打开单组项目")
                assert choice.instate(["selected"]) and tabs.tab(3, "state") == state
                assert Path(validator.get()).resolve() == script.resolve()
            dialog.destroy()
            click(self, "开始验收")
            self.after(100, self.inspect_chinese_report)

        def inspect_chinese_report(self):
            table = next(walk(self, ttk.Treeview))
            if not table.get_children():
                self.after(100, self.inspect_chinese_report)
                return
            assert "Chinese mode validator" in table.item("0", "values")[-1]
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
            click(self, "生图前预检")
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
            from src.image_api import ImageReply
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
                click(dialog, "文本制片")
                saved = ProductionProject.open(project_path)
                assert len(saved.text_drafts) == len(saved.shots) == 1
                assert saved.shots[0].fields["画面/事件"] == "信号灯亮起"
                picture = BytesIO()
                Image.new("RGB", (320, 180), "steelblue").save(picture, format="PNG")
                image_production_dialog.submit_image = lambda *_args: ImageReply((picture.getvalue(),), request_id="smoke-image")
                self.after(50, lambda: self.inspect_image_dialog(dialog))
                click(dialog, "图像制片")
                saved = ProductionProject.open(project_path)
                assert len(saved.image_jobs) == len(saved.images) == 1
                assert saved.image_jobs[0]["status"] == "approved"
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
            dialog = next(walk(production, tk.Toplevel))
            tabs = next(walk(dialog, ttk.Notebook))
            assert [tabs.tab(index, "text") for index in range(2)] == ["新建生图任务", "候选与任务"]
            label = next(widget for widget in walk(dialog, ttk.Label) if widget.cget("text") == "API Key")
            label.master.grid_slaves(row=int(label.grid_info()["row"]), column=1)[0].insert(0, "synthetic")
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
            finally:
                base.delete(0, "end")
                base.insert(0, original_base)
                messagebox.showerror = showerror
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
            if not saved.image_jobs or saved.image_jobs[0]["status"] != "ready":
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
                               ("mode-switch", f' "{archive}"')):
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
