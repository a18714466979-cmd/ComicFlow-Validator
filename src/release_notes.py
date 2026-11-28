"""Display the release notes shipped with this build."""

import re
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import scrolledtext, ttk

from .brand import VERSION
from .ui_language import translate
from .workbench_style import ACCENT, BACKGROUND, INK, MUTED, SURFACE


BUILD_HISTORIES = (
    "https://github.com/a18714466979-cmd/Comic-Sequence-Studio/actions/workflows/windows-smoke.yml"
    "?branch=codex%2Fchinese-production"
)
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def localized_lines(document: str, language: str):
    """Read shared headings and the requested language under each release."""
    section = None
    for line in document.splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            section = None
        if line in ("### 简体中文", "### English"):
            section = "zh" if line.endswith("简体中文") else "en"
            continue
        if section is None or section == language:
            yield line


def open_release_notes(parent):
    window = tk.Toplevel(parent, name="release_notes")
    window.transient(parent)
    window.geometry("720x575")
    window.minsize(460, 330)
    window.bind("<Escape>", lambda _event: window.destroy())
    container = tk.Frame(window, bg=BACKGROUND, padx=16, pady=15)
    container.pack(fill="both", expand=True)

    heading = tk.Label(container, bg=BACKGROUND, fg=INK, font=("TkDefaultFont", 16, "bold"))
    heading.pack(anchor="w")
    build = tk.Label(container, bg=BACKGROUND, fg=MUTED)
    build.pack(anchor="w", pady=(2, 8))

    footer = tk.Frame(container, bg=BACKGROUND)
    footer.pack(side="bottom", fill="x", pady=(8, 0))
    history = ttk.Button(footer, style="Workbench.TButton", command=lambda: webbrowser.open(BUILD_HISTORIES))
    history.pack(side="left")
    close = ttk.Button(footer, style="Workbench.TButton", command=window.destroy)
    close.pack(side="right")

    notes = scrolledtext.ScrolledText(container, name="release_history", wrap="word", relief="flat",
                                      bg=SURFACE, fg=INK, font="TkDefaultFont", padx=14, pady=12)
    notes.pack(fill="both", expand=True)
    notes.tag_configure("heading", foreground=ACCENT, font=("TkDefaultFont", 12, "bold"), spacing3=5)
    notes.tag_configure("list", lmargin1=4, lmargin2=18, spacing3=4)

    try:
        document = (PACKAGE_ROOT / "CHANGELOG.md").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        document = ""
    try:
        revision = (PACKAGE_ROOT / "REVISION.txt").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        revision = ""

    def refresh():
        def tr(text):
            return translate(parent, text)

        title = tr("更新日志")
        window.title(title)
        heading.configure(text=title)
        build.configure(text=f"{tr('构建版本')} v{VERSION}" + (f"  ·  {revision[:12]}" if revision else ""))
        history.configure(text=tr("GitHub 构建记录"))
        close.configure(text=tr("关闭"))
        notes.configure(state="normal")
        notes.delete("1.0", "end")
        if document:
            for line in localized_lines(document, parent.ui_language):
                if line.startswith(("## ", "### ")):
                    notes.insert("end", line.lstrip("# ") + "\n", "heading")
                    continue
                value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line).replace("**", "").replace("`", "")
                if value.startswith("- "):
                    notes.insert("end", "•  " + value[2:] + "\n", "list")
                else:
                    notes.insert("end", value + "\n")
        else:
            notes.insert("end", tr("无法读取更新日志。"))
        notes.configure(state="disabled")

    refresh()
    close.focus_set()
    return window, refresh
