"""Workbench project selection and project-scoped sessions for action sequencing."""

import os
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .action_sequence import cards_from_records
from .action_sequence_dialog import ActionSequenceDialog
from .production_dialog import choose_project_file, project_filetypes
from .production_project import ProductionProject
from .ui_language import translate


class ActionWorkspace:
    def __init__(self, window, navigation, selected_rules, current_path, on_project, open_project):
        self.window = window
        self.navigation = navigation
        self.selected_rules = selected_rules
        self.current_path = current_path
        self.on_project = on_project
        self.open_project = open_project
        self.reading = None

    def mount(self, parent, label_text):
        self.parent = parent
        self.picker = ttk.Frame(parent, name="action_project_picker", padding=(16, 10))
        label_text(ttk.Label(self.picker), "为人物动作编排选择单组项目").pack(anchor="w", pady=(0, 6))
        bar = ttk.Frame(self.picker)
        bar.pack(fill="x")
        self.current_button = label_text(ttk.Button(bar, name="current_project", command=self.use_current),
                                         "使用当前项目")
        self.current_button.pack(side="left", padx=(0, 6))
        for caption, name, command in (
            ("打开单组项目", "open_project", self.choose),
            ("新建单组项目", "new_project", self.create),
            ("取消", "cancel", self.hide),
        ):
            control = label_text(ttk.Button(bar, name=name, command=command), caption)
            control.pack(side="left", padx=(0, 6))
            if name == "open_project":
                self.open_button = control
        self.status = tk.StringVar(self.window)
        ttk.Label(self.picker, textvariable=self.status, wraplength=650).pack(anchor="w")

    def show(self):
        self.navigation.select(self.parent)
        self.current_button.state(["!disabled"] if self.current_path() else ["disabled"])
        siblings = self.parent.pack_slaves()
        if not self.picker.winfo_manager():
            self.picker.pack(fill="x", **({"before": siblings[0]} if siblings else {}))
        if self.reading is None:
            self.open_button.focus_set()

    def hide(self):
        self.picker.pack_forget()
        self.reading = None
        self.status.set("")

    def use_current(self):
        if path := self.current_path():
            self.open(path)

    def choose(self):
        if value := choose_project_file(self.window):
            self.open(value)

    def create(self):
        value = filedialog.asksaveasfilename(
            parent=self.window, title=self.tr("保存新建的单组项目"),
            filetypes=project_filetypes(self.window), defaultextension=".cfproject",
        )
        if value:
            self.open(value, create=True)

    def tr(self, caption):
        return translate(self.window, caption)

    def open(self, path, *, create=False):
        path = Path(path).expanduser().absolute()
        self.reading = None
        self.status.set(self.tr("正在打开项目…") + f" {path.name}")
        rules = self.selected_rules()
        result = Queue()
        self.reading = result

        def load():
            try:
                location = path.resolve()
                if create:
                    if location.exists():
                        raise ValueError("这个项目文件已存在，请选择新文件名。")
                    project = ProductionProject(location.stem, "EP01", "SB01", rules=rules)
                    project.save(location)
                else:
                    project = ProductionProject.open(location)
                result.put((location, project))
            except (OSError, ValueError, TypeError, AttributeError) as error:
                result.put(error)

        def receive():
            if self.reading is not result:
                return
            try:
                value = result.get_nowait()
            except Empty:
                self.window.after(35, receive)
                return
            self.reading = None
            self.status.set("")
            if isinstance(value, Exception):
                self.show_error(value)
                return
            location, project = value
            try:
                key = (os.path.normcase(str(location)), "action_sequence")
                task = self.navigation.open(
                    key, lambda page, changed: ActionWorkspaceTask(
                        self.window, page, location, project, changed, self.on_project, self.open_project,
                    ),
                )
                self.on_project(task.project, task.path)
                self.hide()
            except (OSError, ValueError, RuntimeError, tk.TclError) as error:
                self.show_error(error)

        Thread(target=load, daemon=True).start()
        self.window.after(20, receive)

    def show_error(self, error):
        self.show()
        messagebox.showerror(self.tr("人物动作编排"), self.tr(str(error)), parent=self.window)


class ActionWorkspaceTask:
    def __init__(self, window, page, path, project, changed, on_project, open_project):
        self.window = window
        self.page = page
        self.path = path
        self.project = project
        self._changed = changed
        self._on_project = on_project
        self._open_project = open_project
        self.confirmation = None
        self.breadcrumb = ttk.Label(page, style="A.Muted.TLabel", padding=(12, 5))
        self.breadcrumb.pack(fill="x")
        self.breadcrumb.bind("<Configure>", lambda e: self.breadcrumb.configure(wraplength=max(120, e.width - 24)))
        self.editor = ActionSequenceDialog(self, parent=page)
        self.refresh_breadcrumb()

    def caption(self, *, distinguish=False):
        suffix = " •" if self.editor.dirty() else ""
        label = f"{self.project.group} · {translate(self.window, '人物动作编排')}"
        if distinguish:
            title = self.project.name or self.path.parent.name or self.path.stem
            label = f"{label} / {title[:16]}{'…' if len(title) > 16 else ''}"
        return label + suffix

    def full_caption(self):
        title = self.project.name or self.path.stem
        return f"{title} / {self.project.episode} / {self.caption()}"

    def refresh_breadcrumb(self):
        self.breadcrumb.configure(text=self.full_caption())

    def refresh_language(self):
        self.refresh_breadcrumb()
        self.editor.set_language(getattr(self.window, "ui_language", "zh"))

    def changed(self):
        self._changed()

    def update_group(self):
        pass

    def open_project(self):
        return self._open_project(self.path)

    def latest_project(self):
        project = ProductionProject.open(self.path)
        if (project.episode, project.group, project.rules) != (self.project.episode, self.project.group, self.project.rules):
            raise ValueError(translate(self.window, "项目的集次、组号或制作规则已变化。请先导出动作卡草稿，再重新打开项目。"))
        return project

    def prepare_action_save(self, saved_cards, saved_images, images):
        latest = self.latest_project()
        if cards_from_records(latest.action_cards) != saved_cards:
            raise ValueError(translate(self.window, "此项目的动作编排已在别处修改。请先导出这份草稿，再重新打开项目。"))
        original = {image.id: image for image in saved_images}
        merged = {image.id: image for image in latest.images}
        current = {image.id: image for image in images}
        referenced = {card.reference for card in self.editor.cards if card.reference}
        if (referenced & original.keys()) - merged.keys():
            raise ValueError(translate(self.window, "动作卡引用的图片已从项目移除。请解除或更换该引用后再保存。"))
        for identity, image in current.items():
            if identity in original:
                continue
            if identity in merged and merged[identity] != image:
                raise ValueError(translate(self.window, "项目已有同 ID 的图像，请重新选择动作参考图。"))
            merged[identity] = image
        return latest, list(merged.values())

    def refresh(self):
        self._on_project(self.project, self.path)
        self.refresh_breadcrumb()
        self.changed()
