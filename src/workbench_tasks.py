"""Permanent workbench pages and independently editable task tabs."""

from itertools import count
import tkinter as tk
from tkinter import messagebox, ttk

from .ui_language import translate
from .workbench_style import ACCENT, BACKGROUND, INK, LINE, MUTED, SURFACE, TINT


class WorkbenchTasks:
    def __init__(self, window, captions):
        self.window = window
        self.captions = captions
        self.tasks = {}
        self.serial = count(1)
        self.recent = []
        self.pending = None
        self.active_page = ""
        styles = ttk.Style(window)
        styles.configure("A.Task.TButton", background=SURFACE, bordercolor=LINE, padding=(9, 6))
        styles.configure("A.Active.Task.TButton", background=TINT, bordercolor=ACCENT, foreground=ACCENT)
        styles.configure("A.Close.Task.TButton", background=SURFACE, bordercolor=LINE, padding=(5, 6))
        styles.configure("A.Active.Close.Task.TButton", background=TINT, bordercolor=ACCENT, foreground=ACCENT)
        styles.configure("A.Tasks.TMenubutton", background=SURFACE, foreground=INK, bordercolor=LINE, padding=(8, 6))
        styles.map("A.Task.TButton", background=[("active", TINT)], bordercolor=[("focus", ACCENT)])

        self.bar = ttk.Frame(window, name="workbench_nav")
        self.bar.pack(fill="x", padx=12, pady=(0, 3))
        self.fixed = ttk.Frame(self.bar)
        self.bar.columnconfigure(1, weight=1)
        self.fixed.grid(row=0, column=0, sticky="w")
        self.primary = []
        self.strip = ttk.Frame(self.bar, name="task_tabs")
        self.strip.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.more = ttk.Menubutton(self.strip, name="open_tasks", style="A.Tasks.TMenubutton", takefocus=True)
        self.menu = tk.Menu(self.more, tearoff=False)
        self.more.configure(menu=self.menu)

        self.notebook = ttk.Notebook(window, style="A.Hidden.TNotebook", takefocus=False)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.pages = tuple(ttk.Frame(self.notebook) for _ in captions)
        for index, page in enumerate(self.pages):
            self.notebook.add(page)
            button = ttk.Button(self.fixed, name=f"primary_{index}", style="A.Task.TButton",
                                command=lambda target=page: self.select(target))
            button.pack(side="left", padx=(0, 3))
            self.primary.append(button)

        self.notebook.bind("<<NotebookTabChanged>>", self.selection_changed, add="+")
        self.strip.bind("<Configure>", self.fit, add="+")
        self.bar.bind("<Configure>", self.fit, add="+")

    def select(self, page):
        self.notebook.select(page)
        self.selection_changed()

    def selection_changed(self, event=None):
        if event is not None and event.widget is not self.notebook:
            return
        selected = self.notebook.select()
        if not selected:
            return
        if selected in self.recent:
            self.recent.remove(selected)
        self.recent.append(selected)
        if self.pending is not None and str(self.pending.page) != selected:
            self.dismiss_confirmation()
        for page, button in zip(self.pages, self.primary):
            button.configure(style="A.Active.Task.TButton" if str(page) == selected else "A.Task.TButton")
        if selected != self.active_page:
            self.active_page = selected
            task = next((item for item in self.tasks.values() if str(item.page) == selected), None)
            activated = getattr(task, "activate", None)
            if activated:
                activated()
        self.fit()

    def refresh_language(self):
        for page, button, caption in zip(self.pages, self.primary, self.captions):
            text = translate(self.window, caption)
            button.configure(text=text)
            self.notebook.tab(page, text=text)
        for task in self.tasks.values():
            task.refresh_language()
        self.refresh_confirmation()
        self.fit()
        self.window.after_idle(self.fit)

    def open(self, key, task_factory):
        if key in self.tasks:
            task = self.tasks[key]
            self.select(task.page)
            return task

        page = ttk.Frame(self.notebook, name=f"task_page_{next(self.serial)}")
        try:
            task = task_factory(page, self.fit)
        except Exception:
            page.destroy()
            raise
        self.tasks[key] = task
        self.notebook.add(page)
        chip = ttk.Frame(self.strip, name=page.winfo_name().replace("task_page_", "task_"))
        task.chip = chip
        task.button = ttk.Button(chip, name="select", command=lambda: self.select(page))
        task.button.pack(side="left")
        task.close_button = ttk.Button(chip, name="close", text="×", width=2,
                                       command=lambda: self.request_close(key))
        task.close_button.pack(side="left")
        self.select(page)
        self.window.after_idle(self.fit)
        return task

    def fit(self, _event=None):
        selected = self.notebook.select()
        self.more.configure(text=translate(self.window, "已打开任务（{count}）").format(count=len(self.tasks)))
        self.menu.delete(0, "end")
        items = list(self.tasks.values())
        groups = {}
        for task in items:
            if task.project is not None:
                groups.setdefault(task.project.group, set()).add(task.path)
        for task in items:
            distinct = task.project is not None and len(groups[task.project.group]) > 1
            caption = task.caption(distinguish=distinct)
            self.notebook.tab(task.page, text=caption)
            active = str(task.page) == selected
            task.button.configure(text=caption, style="A.Active.Task.TButton" if active else "A.Task.TButton")
            task.close_button.configure(style="A.Active.Close.Task.TButton" if active else "A.Close.Task.TButton")
            self.menu.add_command(label=task.full_caption(), command=lambda page=task.page: self.select(page))
        widths = {task: task.button.winfo_reqwidth() + task.close_button.winfo_reqwidth() + 4 for task in items}
        wrap = bool(items and self.fixed.winfo_reqwidth() + self.more.winfo_reqwidth() + 12 > self.bar.winfo_width())
        row = int(wrap)
        if int(self.strip.grid_info()["row"]) != row:
            self.strip.grid_configure(row=row, column=0 if wrap else 1, columnspan=2 if wrap else 1,
                                      padx=(0 if wrap else 8, 0), pady=(3 if wrap else 0, 0))
        available = self.strip.winfo_width()
        overflow = sum(widths.values()) > available
        visible = set(items)
        if overflow:
            remaining = max(0, available - self.more.winfo_reqwidth() - 4)
            visible = set()
            for task in sorted(items, key=lambda value: str(value.page) != selected):
                if widths[task] <= remaining:
                    visible.add(task)
                    remaining -= widths[task]
        selected_key = next((key for key, task in self.tasks.items() if str(task.page) == selected), None)
        if selected_key is not None and self.tasks[selected_key] not in visible:
            self.menu.add_separator()
            self.menu.add_command(label=translate(self.window, "关闭当前任务"),
                                  command=lambda: self.request_close(selected_key))
        # Repack only when visibility changes. This preserves keyboard focus on task buttons.
        desired = [task.chip for task in items if task in visible]
        if overflow and items:
            desired.append(self.more)
        if self.strip.pack_slaves() != desired:
            for widget in self.strip.pack_slaves():
                widget.pack_forget()
            for widget in desired:
                widget.pack(side="left" if widget is not self.more else "right", padx=(0, 4))

    def request_close(self, key):
        task = self.tasks[key]
        allowed = getattr(task.editor, "allow_close", None)
        if allowed and allowed() is False:
            self.select(task.page)
            messagebox.showinfo(translate(self.window, "任务进行中"),
                                translate(self.window, "请等待本次请求返回后再关闭任务。"), parent=self.window)
            return
        if not task.editor.dirty():
            self.remove(key)
            return
        self.select(task.page)
        if self.pending is task:
            return
        self.dismiss_confirmation()
        self.pending = task
        panel = tk.Frame(task.page, name="task_close_confirmation", bg=TINT,
                         padx=10, pady=6, highlightthickness=1, highlightbackground=LINE)
        task.confirmation = panel
        panel.pack(fill="x", before=task.editor.frame, padx=10, pady=(3, 6))

        def save():
            try:
                if task.editor.save() is False:
                    return
            except (OSError, ValueError, RuntimeError, tk.TclError) as error:
                messagebox.showerror(translate(self.window, "保存失败"), str(error), parent=self.window)
                return
            self.remove(key)

        self.dismiss_button = ttk.Button(panel, name="keep_editing", command=self.dismiss_confirmation)
        self.discard_button = ttk.Button(panel, name="discard_changes", command=lambda: self.remove(key))
        self.save_button = ttk.Button(panel, name="save_and_close", command=save, style="Primary.Workbench.TButton")
        self.confirmation_label = tk.Label(panel, bg=TINT, fg=MUTED, anchor="w")
        self.confirmation_label.pack(side="left")
        for button in (self.save_button, self.discard_button, self.dismiss_button):
            button.pack(side="right", padx=(5, 0))
        self.refresh_confirmation()
        self.dismiss_button.focus_set()

    def refresh_confirmation(self):
        if self.pending is None:
            return
        tr = lambda caption: translate(self.window, caption)
        self.confirmation_label.configure(text=tr("当前任务有未保存更改。"))
        self.dismiss_button.configure(text=tr("继续编辑"))
        self.discard_button.configure(text=tr("放弃更改并关闭"))
        self.save_button.configure(text=tr("保存并关闭"))

    def dismiss_confirmation(self):
        if self.pending is not None:
            task, self.pending = self.pending, None
            task.confirmation.destroy()
            task.confirmation = None

    def remove(self, key):
        task = self.tasks.pop(key)
        page_id = str(task.page)
        was_selected = self.notebook.select() == page_id
        if self.pending is task:
            self.dismiss_confirmation()
        self.recent = [page for page in self.recent if page != page_id]
        if was_selected:
            self.select(self.recent[-1] if self.recent else self.pages[0])
        self.notebook.forget(task.page)
        task.page.destroy()
        task.chip.destroy()
        self.fit()

    def allow_close(self):
        for key, task in tuple(self.tasks.items()):
            allowed = getattr(task.editor, "allow_close", None)
            if (allowed and allowed() is False) or task.editor.dirty():
                self.request_close(key)
                return False
        return True
