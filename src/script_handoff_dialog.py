"""Choose a project for an explicitly selected manuscript."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .production_dialog import PROJECT_FILES
from .production_flow import attach_script
from .ui_language import translate


def choose_project_for_script(parent, title, text, rules):
    panel = tk.Toplevel(parent)
    panel.title(translate(panel, "将剧本带入分镜"))
    panel.transient(parent)
    body = ttk.Frame(panel, padding=14)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=title, wraplength=480).pack(anchor="w")
    ttk.Label(body, text=translate(panel, "选择新项目或已有项目。这份原文将作为一个剧本版本带入镜头清单。"),
              wraplength=480).pack(anchor="w", pady=(4, 10))
    labels = ((translate(panel, PROJECT_FILES[0][0]), PROJECT_FILES[0][1]),)
    result = []

    def select(existing):
        if existing:
            value = filedialog.askopenfilename(parent=panel, filetypes=labels)
        else:
            value = filedialog.asksaveasfilename(parent=panel, filetypes=labels, defaultextension=".cfproject",
                                                initialfile="SB01.cfproject", confirmoverwrite=False)
        if not value:
            return
        try:
            path = Path(value)
            project, source = attach_script(path, title, text, rules, existing=existing)
        except (OSError, ValueError) as exc:
            messagebox.showerror(panel.title(), translate(panel, str(exc)), parent=panel)
            return
        result.append((path, project, source))
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
