"""Select a ZIP and run the existing storyboard checker in the launcher console."""

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .delivery_checker import main as validate


def select_options(initial_zip: str) -> list[str]:
    window = tk.Tk()
    window.title("ComicFlow 故事板交付验收")
    window.columnconfigure(1, weight=1)
    entries = (
        ("交付 ZIP", tk.StringVar(value=initial_zip), ("ZIP 交付包", "*.zip")),
        ("故事板校验脚本", tk.StringVar(value=os.getenv("COMICFLOW_STORYBOARD_VALIDATOR", "")),
         ("Python 校验脚本", "*.py")),
        ("已批准格数例外（可选）", tk.StringVar(), ("JSON 例外文件", "*.json")),
    )
    review = tk.BooleanVar()
    arguments = []

    def browse(value: tk.StringVar, kind: tuple[str, str]) -> None:
        selected = filedialog.askopenfilename(parent=window, filetypes=(kind, ("所有文件", "*")))
        if selected:
            value.set(selected)

    def start() -> None:
        archive, validator, exception = (Path(value.get().strip()) for _, value, _ in entries)
        for path, suffix, label in ((archive, ".zip", "交付 ZIP"), (validator, ".py", "校验脚本")):
            if path.suffix.lower() != suffix or not path.is_file():
                messagebox.showerror("文件未找到", f"请选择有效的{label}。", parent=window)
                return
        if exception != Path() and (exception.suffix.lower() != ".json" or not exception.is_file()):
            messagebox.showerror("文件未找到", "请选择有效的格数例外 JSON。", parent=window)
            return

        arguments.extend((str(archive), "--storyboard-validator", str(validator)))
        if exception != Path():
            arguments.extend(("--panel-exception", str(exception)))
        if review.get():
            arguments.append("--review-missing-sources")
        window.destroy()

    for row, (label, value, kind) in enumerate(entries):
        ttk.Label(window, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=8)
        ttk.Entry(window, textvariable=value, width=58).grid(row=row, column=1, sticky="ew")
        ttk.Button(window, text="浏览", command=lambda v=value, k=kind: browse(v, k)).grid(
            row=row, column=2, padx=12,
        )
    ttk.Checkbutton(window, text="将不可访问的复用原图标为未验证", variable=review).grid(
        row=3, column=1, sticky="w", pady=8,
    )
    ttk.Button(window, text="开始验收", command=start).grid(row=4, column=1, sticky="e", pady=(0, 12))
    window.mainloop()
    return arguments


def main() -> int:
    arguments = select_options(sys.argv[1] if len(sys.argv) > 1 else "")
    return validate(arguments) if arguments else 0


if __name__ == "__main__":
    raise SystemExit(main())
