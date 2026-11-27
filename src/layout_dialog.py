"""Local sheet composition and pair review in the production workbench."""

import tkinter as tk
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import filedialog, messagebox, simpledialog, ttk
from zipfile import ZipFile

from PIL import Image, ImageTk

from .image_production_dialog import display_picture, select_image_region
from .production_dialog import PROJECT_FILES, fields_text, write_text
from .production_export import project_registry, publish_batch
from .production_handoff import active_scope, adjacent, adopt_pending, boundary_report, confirm_boundary, defer_tail, pending_record, restore_tail
from .production_layout import COLORS, add_mark, apply_layout, bind_window, render_layout, windows_for_shots
from .production_project import GROUP_FIELDS, ProductionProject
from .shot_review_dialog import open_shot_review
from .storyboard_review import ReviewResult, index_members


class LayoutDialog:
    def __init__(self, production):
        self.production = production
        self.project, self.path = production.project, production.path
        self.workspace = None
        self.draft = None
        self.next_group = None
        self.boundary_seen = None
        self.window = tk.Toplevel(production.window)
        self.window.title("ComicFlow 排版与交接")
        self.window.geometry("1070x755")
        self.window.minsize(830, 650)
        self.window.transient(production.window)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Destroy>", self.cleanup, add="+")
        tabs = ttk.Notebook(self.window)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        page, handoff = (ttk.Frame(tabs, padding=10) for _ in range(2))
        tabs.add(page, text="16:9 排版")
        tabs.add(handoff, text="相邻组交接")
        self.layout_page(page)
        self.handoff_page(handoff)

    def close(self):
        self.window.destroy()

    def cleanup(self, event):
        if event.widget == self.window and self.workspace:
            self.workspace.cleanup()

    def protect(self, action):
        try:
            action()
        except (ValueError, OSError, IndexError, KeyError) as exc:
            messagebox.showerror("排版与交接", str(exc), parent=self.window)

    def buttons(self, bar, *items):
        for label, action in items:
            ttk.Button(bar, text=label, command=lambda run=action: self.protect(run)).pack(side="left", padx=(0, 5))

    def layout_page(self, page):
        ttk.Label(page, text="选择镜头，再绑定已批准的黑白板格和同机位彩色净板。可用整图或已有同用途图内的实际窗口。",
                  wraplength=960).pack(anchor="w")
        self.rows = self.production.table(page, ("镜头", "来源", "黑白板格", "彩色净板", "箭头"), (105, 185, 260, 260, 65))
        self.rows.bind("<<TreeviewSelect>>", self.sync_source)
        bind = ttk.Frame(page)
        bind.pack(fill="x", pady=6)
        self.purpose = ttk.Combobox(bind, state="readonly", width=10, values=("故事板格", "彩色净板"))
        self.purpose.pack(side="left", padx=(0, 5))
        self.purpose.current(0)
        self.purpose.bind("<<ComboboxSelected>>", self.sync_source)
        self.asset = ttk.Combobox(bind, state="readonly", width=36)
        self.asset.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.buttons(bind, ("绑定整图", lambda: self.bind_image(False)), ("在原图框选", lambda: self.bind_image(True)))

        marks = ttk.Frame(page)
        marks.pack(fill="x", pady=(0, 6))
        self.color = ttk.Combobox(marks, state="readonly", width=13, values=tuple(COLORS))
        self.color.pack(side="left", padx=(0, 6))
        self.color.current(0)
        ttk.Label(marks, text="运动对象").pack(side="left", padx=(0, 4))
        self.mark_target = ttk.Entry(marks, width=20)
        self.mark_target.pack(side="left", padx=(0, 6))
        self.buttons(marks, ("为选中镜头画箭头", self.mark), ("撤销最近箭头", self.unmark))

        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=6)
        self.mixed = tk.BooleanVar(self.window, self.project.notes.get("场景资产模式") == "多场景局部")
        ttk.Checkbutton(controls, text="多场景共用净板合辑", variable=self.mixed).pack(side="left", padx=(0, 7))
        self.buttons(controls, ("生成排版预览", self.preview_layout), ("确认排版并更新正式图", self.use_layout))
        self.layout_status = tk.StringVar(self.window)
        ttk.Label(page, textvariable=self.layout_status, wraplength=955).pack(anchor="w")
        self.refresh()

    def handoff_page(self, page):
        files = ttk.Frame(page)
        files.pack(fill="x")
        self.buttons(files, ("载入下一组", self.load_next), ("对照前末后首", self.compare_boundary),
                     ("确认本处交接", self.approve_boundary), ("导出相邻组 ZIP", self.batch))
        work = ttk.Frame(page)
        work.pack(fill="x", pady=8)
        self.buttons(work, ("暂存所选及后续镜头", self.defer), ("恢复本组待制作", self.restore),
                     ("接收前组待制作", self.receive_pending), ("导出待制作 TXT", self.export_pending))
        self.partner = tk.StringVar(self.window, "请选择同一集的下一组项目。")
        ttk.Label(page, textvariable=self.partner, wraplength=940).pack(anchor="w")
        self.report = self.production.editor(page, 16)
        self.report.pack(fill="both", expand=True, pady=(7, 0))
        self.report.configure(state="disabled")

    def refresh(self):
        before = self.rows.selection()
        self.images = list(self.project.images)
        names = {asset.id: asset.filename for asset in self.images}
        self.asset["values"] = tuple(f"{asset.filename} · {asset.version}" for asset in self.images)
        self.rows.delete(*self.rows.get_children())
        for index, shot in enumerate(self.project.shots, 1):
            data = self.project.layout.get("inputs", {}).get(shot.id, {})
            self.rows.insert("", "end", iid=shot.id, values=(
                f"{self.project.group}-{index:02d}", shot.anchor,
                names.get(data.get("board", {}).get("image"), "待绑定"),
                names.get(data.get("plate", {}).get("image"), "待绑定"), len(data.get("marks", [])),
            ))
        children = self.rows.get_children()
        if children:
            self.rows.selection_set(before[0] if before and before[0] in children else children[0])
        self.sync_source()
        self.layout_status.set(f"{len(self.project.shots)} 镜 · 待制作 {len(self.project.pending_shots)} 镜")

    def chosen(self):
        selected = self.rows.selection()
        if not selected:
            raise ValueError("请选择一个实际镜头。")
        return selected[0]

    def kind(self):
        return "board" if self.purpose.current() == 0 else "plate"

    def sync_source(self, _event=None):
        selected = self.rows.selection()
        slot = self.project.layout.get("inputs", {}).get(selected[0], {}).get(self.kind(), {}) if selected else {}
        index = next((i for i, item in enumerate(self.images) if item.id == slot.get("image")), None)
        if index is not None:
            self.asset.current(index)
        elif self.images:
            current = next((shot.plate for shot in self.project.shots if selected and shot.id == selected[0]), "")
            existing = next((i for i, item in enumerate(self.images) if self.kind() == "plate" and item.id == current), 0)
            self.asset.current(existing)
        else:
            self.asset.set("")

    def save(self):
        self.project.save(self.path)
        self.production.refresh()

    def bind_image(self, cropped):
        identity = self.chosen()
        index = self.asset.current()
        if index < 0:
            raise ValueError("请在「批准图像」里导入原图，再选作排版输入。")
        asset = self.images[index]
        path = self.project.checked_image(self.path, asset)
        box = select_image_region(self.window, path, "框选同镜的有效画面，保存时调整为 16:9") if cropped else None
        if cropped and box is None:
            return
        old = self.project.layout.get("inputs", {}).get(identity, {}).get("marks", [])
        if self.kind() == "board" and old and not messagebox.askyesno(
            "更新故事板绑定", "换图或换选区需重新确认原有箭头。是否更新本镜绑定？", parent=self.window
        ):
            return
        actual = bind_window(self.project, self.path, identity, self.kind(), asset.id, box)
        self.save()
        self.refresh()
        self.layout_status.set(f"当前窗口 {actual} · {actual[2]-actual[0]}×{actual[3]-actual[1]}")

    def mark(self):
        shot_id = self.chosen()
        row = self.project.layout.get("inputs", {}).get(shot_id, {})
        original = row.get("board")
        if not original or not self.mark_target.get().strip():
            raise ValueError("请先绑定故事板格，并填写实际运动对象。")
        asset = next((image for image in self.project.images if image.id == original["image"]), None)
        if asset is None:
            raise ValueError("批准的故事板原图已移除。")
        path = self.project.checked_image(self.path, asset)
        points = select_image_region(self.window, path, f"只在绑定窗口 {tuple(original['box'])} 内画箭头", direction=True)
        if points:
            add_mark(self.project, shot_id, self.color.get(), self.mark_target.get(), *points)
            self.save()
            self.refresh()

    def unmark(self):
        history = self.project.layout.get("inputs", {}).get(self.chosen(), {}).get("marks", [])
        if history:
            history.pop()
            self.save()
            self.refresh()

    def preview_layout(self):
        if self.workspace:
            self.workspace.cleanup()
        self.draft = None
        self.workspace = TemporaryDirectory(prefix="comicflow-layout-")
        self.draft = render_layout(self.project, self.path, Path(self.workspace.name), self.mixed.get())
        dialog = tk.Toplevel(self.window)
        dialog.title("排版预览")
        dialog.transient(self.window)
        dialog.geometry("1020x700")
        tabs = ttk.Notebook(dialog)
        tabs.pack(fill="both", expand=True, padx=8, pady=8)
        detail = []
        for sheet in self.draft.sheets:
            page = ttk.Frame(tabs)
            tabs.add(page, text="故事板" if sheet.kind == "board" else sheet.path.stem.removeprefix("scene_").removesuffix("_16x9"))
            display_picture(page, sheet.path)
            notes = []
            if sheet.shrunken:
                notes.append("部分画面等比缩小")
            if sheet.padding:
                notes.append("当前格数保留必要板面余量")
            if notes:
                detail.append(sheet.path.name + " · " + "、".join(notes))
        self.layout_status.set(f"排版预览 {len(self.draft.sheets)} 张。 " + ("；".join(detail) or "板面无空槽。"))
        self.wait(dialog)

    def use_layout(self):
        if not self.draft or self.draft.mixed != self.mixed.get():
            raise ValueError("请先生成并检查当前设置的排版预览。")
        review = simpledialog.askstring("批准本次排版", "记录实际核对结果，包含板格、净板与可读性。", parent=self.window)
        if review is None:
            return
        apply_layout(self.project, self.path, self.draft, review)
        self.draft = None
        write_text(self.production.notes, fields_text(GROUP_FIELDS, self.project.notes))
        self.production.refresh()
        self.refresh()
        self.layout_status.set("正式图和镜头绑定已更新。请在「复核与交付」核对最终图片和双 TXT。")

    def load_next(self):
        filename = filedialog.askopenfilename(parent=self.window, filetypes=PROJECT_FILES)
        if filename:
            path = Path(filename)
            project = ProductionProject.open(path)
            adjacent(self.project, project)
            self.next_group = (project, path)
            self.boundary_seen = None
            self.partner.set(f"{self.project.group} → {project.group} · {path.name}")
            self.report_text("")

    def projects(self):
        if self.next_group is None:
            raise ValueError("请先载入下一组项目。")
        expected, path = self.next_group
        actual = ProductionProject.open(path)
        if actual.fingerprint() != expected.fingerprint():
            raise ValueError("下一组文件已修改，请重新载入后复核。")
        return [(self.project, self.path), (actual, path)]

    def planner(self):
        return self.production.validator_path().with_name("plan_english_dialogue.py")

    def report_text(self, content):
        self.report.configure(state="normal")
        write_text(self.report, content)
        self.report.configure(state="disabled")

    def compare_boundary(self):
        groups = self.projects()
        right = groups[1][0]
        summary, issues = boundary_report(self.project, right, self.planner())
        self.report_text(summary)
        dialog = tk.Toplevel(self.window)
        dialog.title("对照前组末镜与后组首镜")
        dialog.transient(self.window)
        body = ttk.Frame(dialog, padding=8)
        body.pack(fill="both", expand=True)
        for n, ((project, path), index) in enumerate(zip(groups, (-1, 0))):
            shot = project.shots[index]
            assets = {asset.id: asset for asset in project.images if not asset.reference_only}
            exact = windows_for_shots(project, assets).get(shot.id, {})
            box = ttk.LabelFrame(body, text=f"{project.group}-{'01' if index == 0 else f'{len(project.shots):02d}'}", padding=5)
            box.grid(row=0, column=n, sticky="nsew", padx=5)
            for kind, title in (("board", "故事板格"), ("plate", "彩色净板")):
                fallback = (assets.get(shot.plate) if kind == "plate"
                            else next((asset for asset in assets.values() if "storyboard" in asset.filename.lower()), None))
                asset, coords = exact.get(kind, (fallback, None))
                if asset is None:
                    raise ValueError(f"{project.group} 缺少可对照的{title}。")
                with Image.open(project.checked_image(path, asset)) as source:
                    preview = source.crop(coords) if coords else source.copy()
                preview.thumbnail((410, 231), Image.Resampling.LANCZOS)
                label = ttk.Label(box, text=title + (" · 本镜窗口" if coords else " · 整图"), compound="top")
                label.photo = ImageTk.PhotoImage(preview, master=label)
                label.configure(image=label.photo)
                label.pack(pady=4)
        editor = self.production.editor(dialog, 9)
        editor.pack(fill="x", padx=9, pady=(0, 8))
        editor.insert("1.0", summary)
        editor.configure(state="disabled")
        self.wait(dialog)
        if not issues:
            self.boundary_seen = (self.project.fingerprint(), right.fingerprint())

    def approve_boundary(self):
        right = self.projects()[1][0]
        if self.boundary_seen != (self.project.fingerprint(), right.fingerprint()):
            raise ValueError("请先打开当前版本的前末后首对照，并处理列出的差异。")
        review = simpledialog.askstring("确认本处交接", "记录已核对的方位、动作、状态延续或合理变化。", parent=self.window)
        if review is None:
            return
        confirm_boundary(self.project, right, self.planner(), review)
        self.save()
        self.report_text("跨组交接已确认。两组分别确认正式画面后，可导出相邻组 ZIP。\n\n" + review)

    def batch(self):
        groups = self.projects()
        validator = self.production.validator_path()
        filename = filedialog.asksaveasfilename(parent=self.window, defaultextension=".zip",
                                               filetypes=(("故事板批次 ZIP", "*.zip"),))
        if not filename:
            return
        self.window.configure(cursor="watch")
        self.window.update_idletasks()
        try:
            result = publish_batch(groups, validator, Path(filename))
        finally:
            self.window.configure(cursor="")
        self.production.registry.set(str(project_registry(self.path)))
        suffix = f"\n\n已导出 {result.output}\nSHA-256 {result.sha256}" if result.output else "\n\n此版未导出。"
        self.report_text(result.report + suffix)
        if result.output:
            with ZipFile(result.output) as archive:
                members = index_members(archive)
            open_shot_review(self.window, ReviewResult(0, result.report, result.output, members, []), group=self.project.group,
                             shot=f"{self.project.group}-{len(self.project.shots):02d}")
            self.window.grab_set()

    def defer(self):
        identity = self.chosen()
        index = self.rows.index(identity)
        if messagebox.askyesno("暂存尾部镜头", f"把第 {index + 1} 镜和后续镜头移入批尾待制作？", parent=self.window):
            defer_tail(self.project, index)
            self.save()
            self.refresh()
            self.report_text(f"待制作 {len(self.project.pending_shots)} 镜。正式组的板格和净板请按剩余镜头更新。")

    def restore(self):
        if self.project.pending_shots:
            restore_tail(self.project)
            self.save()
            self.refresh()

    def receive_pending(self):
        filename = filedialog.askopenfilename(parent=self.window, filetypes=PROJECT_FILES)
        if filename:
            previous = ProductionProject.open(Path(filename))
            adopt_pending(previous, self.project)
            self.production.refresh_sources()
            self.save()
            self.refresh()
            self.report_text(f"已接收 {len(previous.pending_shots)} 镜，沿用批准来源和源镜 ID。请补绑本组板格与净板。")

    def export_pending(self):
        scope = active_scope(self.project, self.planner()) if self.project.shots else {}
        text = pending_record(self.project, scope)
        if not text:
            raise ValueError("当前没有待制作镜头或批准对白余文。")
        filename = filedialog.asksaveasfilename(parent=self.window, defaultextension=".txt",
                                               initialfile="待制作分镜.txt", filetypes=(("文本", "*.txt"),))
        if filename:
            with Path(filename).open("x", encoding="utf-8-sig") as file:
                file.write(text)
            self.report_text(f"已导出 {filename}\n\n" + text)

    def wait(self, dialog):
        dialog.grab_set()
        self.window.wait_window(dialog)
        self.window.grab_set()
