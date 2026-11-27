"""Local storyboard review window."""

from io import BytesIO
import os
from queue import Empty, Queue
import re
import sys
import tkinter as tk
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from .asset_repair_dialog import open_asset_repair
from .preflight_dialog import open_preflight_dialog
from .production_dialog import open_production_dialog
from .shot_review_dialog import open_shot_review
from .storyboard_review import PREVIEW_LIMIT, ReviewIssue, ReviewResult, read_preview, run_review
from .vision import VisionSettings
from .vision_dialog import open_vision_dialog


def open_workbench(initial_zip: str) -> int:
    window = tk.Tk()
    window.title("ComicFlow 故事板交付验收")
    window.geometry("1120x770")
    window.minsize(800, 600)
    options = ttk.Frame(window, padding=(12, 10))
    options.pack(fill="x")
    options.columnconfigure(1, weight=1)
    entries = (
        ("交付 ZIP", tk.StringVar(value=initial_zip), ("ZIP 交付包", "*.zip")),
        ("故事板校验脚本", tk.StringVar(value=os.getenv("COMICFLOW_STORYBOARD_VALIDATOR", "")),
         ("Python 校验脚本", "*.py")),
        ("已批准格数例外（可选）", tk.StringVar(), ("JSON 例外文件", "*.json")),
    )
    review = tk.BooleanVar()
    registry_path = tk.StringVar()
    status = tk.StringVar(value="请选择交付包和校验脚本。")
    result: ReviewResult | None = None
    workspace: TemporaryDirectory | None = None
    busy = False
    exit_code = 0
    selected_issue: ReviewIssue | None = None
    results: Queue = Queue()
    image_preview = None
    vision_session: dict[str, VisionSettings] = {}

    tabs = ttk.Notebook(window)
    issues_tab = ttk.Frame(tabs, padding=8)
    report_tab = ttk.Frame(tabs, padding=8)
    tabs.add(issues_tab, text="验收结果")
    tabs.add(report_tab, text="完整报告")
    report_text = scrolledtext.ScrolledText(report_tab, wrap="word", state="disabled")
    report_text.pack(expand=True, fill="both")

    split = ttk.Panedwindow(issues_tab, orient="vertical")
    split.pack(expand=True, fill="both")
    table_frame = ttk.Frame(split)
    preview_frame = ttk.Frame(split, padding=(0, 8, 0, 0))
    split.add(table_frame, weight=1)
    split.add(preview_frame, weight=2)
    columns = ("status", "group", "shot", "filename", "message")
    table = ttk.Treeview(table_frame, columns=columns, show="headings", height=8, selectmode="browse")
    for column, title, width in zip(columns, ("结果", "组", "镜号", "文件", "详情"), (95, 90, 80, 210, 460)):
        table.heading(column, text=title)
        table.column(column, width=width, stretch=column == "message")
    scroll = ttk.Scrollbar(table_frame, command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    table.pack(expand=True, fill="both")

    location = ttk.Label(preview_frame, wraplength=760)
    location.pack(anchor="w", fill="x")
    file_row = ttk.Frame(preview_frame)
    file_row.pack(fill="x", pady=6)
    file_selector = ttk.Combobox(file_row, state="readonly")
    file_selector.pack(side="left", fill="x", expand=True)
    preview_text = scrolledtext.ScrolledText(preview_frame, height=9, wrap="word", state="disabled")
    preview_text.tag_configure("shot", background="#fce3a0", foreground="#1b1b1b")
    preview_text.pack(fill="both", expand=True)
    preview_image = ttk.Label(preview_frame, anchor="center")

    def analyze_selected_image() -> None:
        path = file_selector.get()
        if result is None or path not in result.members or path.lower().endswith(".txt"):
            return
        try:
            image = read_preview(result, path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("图片无法分析", str(exc), parent=window)
            return
        open_vision_dialog(window, path, image, vision_session)

    analyze = ttk.Button(file_row, text="AI 辅助看图", command=analyze_selected_image, state="disabled")
    analyze.pack(side="right", padx=(8, 0))

    def inspect_shots() -> None:
        if result is not None:
            group = selected_issue.group if selected_issue else file_selector.get().partition("/")[0]
            shot = selected_issue.shot if selected_issue else ""
            open_shot_review(window, result, group, shot)

    inspect = ttk.Button(file_row, text="逐格复核", command=inspect_shots, state="disabled")
    inspect.pack(side="right", padx=(8, 0))

    def set_text(widget: scrolledtext.ScrolledText, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def show_preview() -> None:
        nonlocal image_preview
        analyze.configure(state="disabled")
        preview_image.pack_forget()
        preview_image.configure(image="")
        image_preview = None
        preview_text.pack(fill="both", expand=True)
        path = file_selector.get()
        if result is None or path not in result.members:
            set_text(preview_text, "此文件不在 ZIP 内。" if path else "选择一个包内文件查看内容。")
            return
        try:
            data = read_preview(result, path)
            if path.lower().endswith(".txt"):
                content = data.decode("utf-8-sig")
                set_text(preview_text, content)
                if selected_issue and selected_issue.shot:
                    full = selected_issue.shot
                    short = full.partition("-")[2] or full
                    marker = re.search(
                        rf"^分镜(?:编号)?[：:\t ]+({re.escape(full)}|0*{re.escape(short.lstrip('0'))})\b",
                        content, re.MULTILINE | re.IGNORECASE,
                    )
                    if marker:
                        line = content.count("\n", 0, marker.start()) + 1
                        preview_text.tag_add("shot", f"{line}.0", f"{line}.end")
                        preview_text.see(f"{line}.0")
                return

            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 32_000_000:
                    raise ValueError("图片分辨率超过内置预览限制。")
                image.thumbnail((max(300, preview_frame.winfo_width() - 25),
                                 max(140, preview_frame.winfo_height() - 95)), Image.Resampling.LANCZOS)
                image_preview = ImageTk.PhotoImage(image)
            preview_text.pack_forget()
            preview_image.configure(image=image_preview)
            preview_image.pack(expand=True, fill="both")
            analyze.configure(state="normal")
        except Exception as exc:
            set_text(preview_text, f"无法预览 {path}\n{exc}")

    def select_issue(_event=None) -> None:
        nonlocal selected_issue
        selection = table.selection()
        if result is None or not selection:
            return
        selected_issue = result.issues[int(selection[0])]
        group = selected_issue.group
        filename = selected_issue.filename
        location.configure(text=selected_issue.message)
        candidates = [path for path in result.members if (not group or path.startswith(group + "/"))
                      and Path(path).suffix.lower() in PREVIEW_LIMIT]
        target = f"{group}/{filename}" if group and filename else filename
        if not target and selected_issue.shot:
            target = next((path for path in candidates if path.endswith("_shot_details.txt")), "")
        file_selector.configure(values=sorted(candidates))
        file_selector.set(target)
        show_preview()

    table.bind("<<TreeviewSelect>>", select_issue)
    file_selector.bind("<<ComboboxSelected>>", lambda _event: show_preview())

    def receive() -> None:
        nonlocal busy, result, exit_code
        try:
            completed = results.get_nowait()
        except Empty:
            window.after(100, receive)
            return
        busy = False
        start_button.configure(state="normal")
        if isinstance(completed, Exception):
            exit_code = 1
            status.set("验收未完成")
            set_text(report_text, str(completed))
            tabs.select(report_tab)
            return
        result = completed
        inspect.configure(state="normal" if result.members else "disabled")
        exit_code = result.exit_code
        verdicts = {0: "自动检查通过", 1: "验收失败", 2: "配置错误", 3: "复用未验证"}
        verdict = verdicts.get(result.exit_code, "验收未完成")
        status.set(f"{verdict} · {len(result.issues)} 条结果")
        set_text(report_text, result.report)
        for number, issue in enumerate(result.issues):
            table.insert("", "end", iid=str(number), values=(
                issue.status, issue.group, issue.shot, issue.filename, issue.message,
            ))
        if result.issues:
            table.selection_set("0")
            tabs.select(issues_tab)
        elif result.exit_code:
            tabs.select(report_tab)
        else:
            file_selector.configure(values=sorted(path for path in result.members
                                                  if Path(path).suffix.lower() in PREVIEW_LIMIT))
            tabs.select(issues_tab)

    def browse(value: tk.StringVar, kind: tuple[str, str]) -> None:
        selected = filedialog.askopenfilename(parent=window, filetypes=(kind, ("所有文件", "*")))
        if selected:
            value.set(selected)

    def start() -> None:
        nonlocal busy, result, workspace, selected_issue
        archive, validator, exception = (Path(value.get().strip()).expanduser() for _, value, _ in entries)
        for path, suffix, label in ((archive, ".zip", "交付 ZIP"), (validator, ".py", "校验脚本")):
            if path.suffix.lower() != suffix or not path.is_file():
                messagebox.showerror("文件未找到", f"请选择有效的{label}。", parent=window)
                return
        if exception != Path() and (exception.suffix.lower() != ".json" or not exception.is_file()):
            messagebox.showerror("文件未找到", "请选择有效的格数例外 JSON。", parent=window)
            return

        arguments = [str(archive.resolve()), "--storyboard-validator", str(validator.resolve())]
        if exception != Path():
            arguments.extend(("--panel-exception", str(exception.resolve())))
        if review.get():
            arguments.append("--review-missing-sources")
        if registry_path.get().strip():
            arguments.extend(("--asset-registry", str(Path(registry_path.get().strip()).expanduser().resolve())))
        if workspace:
            workspace.cleanup()
        workspace = TemporaryDirectory(prefix="comicflow-review-")
        directory = Path(workspace.name)
        busy = True
        result = selected_issue = None
        inspect.configure(state="disabled")
        table.delete(*table.get_children())
        file_selector.configure(values=())
        file_selector.set("")
        location.configure(text="")
        show_preview()
        set_text(report_text, "")
        start_button.configure(state="disabled")
        status.set(f"正在验收 {archive.name}…")

        def worker() -> None:
            try:
                results.put(run_review(arguments, directory))
            except Exception as exc:
                results.put(exc)

        Thread(target=worker, daemon=True).start()
        window.after(100, receive)

    def close() -> None:
        if busy:
            messagebox.showinfo("验收进行中", "当前正在读取交付包，请等待验收完成。", parent=window)
            return
        window.destroy()

    for row, (label, value, kind) in enumerate(entries):
        ttk.Label(options, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=5)
        ttk.Entry(options, textvariable=value, width=58).grid(row=row, column=1, sticky="ew")
        ttk.Button(options, text="浏览", command=lambda v=value, k=kind: browse(v, k)).grid(
            row=row, column=2, padx=12,
        )
    ttk.Checkbutton(options, text="将不可访问的复用原图标为未验证", variable=review).grid(
        row=3, column=1, sticky="w", pady=8,
    )
    start_button = ttk.Button(options, text="开始验收", command=start)
    start_button.grid(row=3, column=2, pady=6)
    ttk.Label(options, textvariable=status).grid(row=4, column=0, columnspan=2, sticky="w", padx=12)
    actions = ttk.Frame(options)
    actions.grid(row=4, column=2, sticky="e", pady=(0, 2))
    ttk.Button(actions, text="单组制片", command=lambda: open_production_dialog(
        window, entries[1][1].get().strip(), registry_path,
    )).pack(side="left", padx=(0, 5))
    ttk.Button(actions, text="生图前预检", command=lambda: open_preflight_dialog(window, entries[1][1].get().strip())).pack(side="left")
    ttk.Button(actions, text="资产与返修", command=lambda: open_asset_repair(
        window, registry_path, entries[1][1].get().strip(), result,
    )).pack(side="left", padx=(5, 0))
    tabs.pack(expand=True, fill="both", padx=12, pady=(0, 12))
    window.protocol("WM_DELETE_WINDOW", close)
    try:
        window.mainloop()
    finally:
        if workspace and not busy:
            workspace.cleanup()
    return exit_code


def main() -> int:
    return open_workbench(sys.argv[1] if len(sys.argv) > 1 else "")


if __name__ == "__main__":
    raise SystemExit(main())
