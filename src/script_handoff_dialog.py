"""Choose a project for an explicitly selected manuscript."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .production_dialog import project_filetypes
from .production_flow import attach_script
from .ui_language import translate


def choose_project_for_script(parent, title, text, rules, *, existing=None):
    if existing is not None:
        return select_project(parent, title, text, rules, existing=existing)

    panel = tk.Toplevel(parent)
    panel.title(translate(panel, "将剧本带入分镜"))
    panel.transient(parent)
    body = ttk.Frame(panel, padding=14)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=title, wraplength=480).pack(anchor="w")
    ttk.Label(body, text=translate(panel, "选择新项目或已有项目。这份原文将作为一个剧本版本带入镜头清单。"),
              wraplength=480).pack(anchor="w", pady=(4, 10))
    result = []

    def select(existing):
        try:
            selection = select_project(panel, title, text, rules, existing=existing)
        except (OSError, ValueError) as exc:
            messagebox.showerror(panel.title(), translate(panel, str(exc)), parent=panel)
            return
        if selection:
            result.append(selection)
            panel.destroy()

    actions = ttk.Frame(body)
    actions.pack(fill="x")
    for caption, command in (("新建项目并拆分镜", lambda: select(False)),
                             ("加入已有项目", lambda: select(True)),
                             ("取消", panel.destroy)):
        ttk.Button(actions, text=translate(panel, caption), command=command).pack(side="left", padx=(0, 8))
    panel.grab_set()
    parent.wait_window(panel)
    parent.grab_set()
    return result[0] if result else None


def select_project(parent, title, text, rules, *, existing):
    labels = project_filetypes(parent)
    if existing:
        value = filedialog.askopenfilename(parent=parent, filetypes=labels)
    else:
        value = filedialog.asksaveasfilename(parent=parent, filetypes=labels, defaultextension=".cfproject",
                                            initialfile="SB01.cfproject", confirmoverwrite=False)
    if not value:
        return None
    path = Path(value)
    project, source = attach_script(path, title, text, rules, existing=existing)
    return path, project, source
