"""Local storyboard review window."""

from io import BytesIO
import json
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

from .api_settings_dialog import build_api_settings
from .asset_repair_dialog import open_asset_repair
from .preflight_dialog import open_preflight_dialog
from .production_dialog import open_production_dialog
from .bundled_validators import bundled_validator
from .production_project import atomic_text
from .production_rules import CHINESE, ENGLISH, RULE_LABELS, rule_revision
from .image_api import ImageSettings
from .shot_review_dialog import open_shot_review
from .storyboard_review import PREVIEW_LIMIT, ReviewIssue, ReviewResult, read_preview, run_review
from .vision import VisionSettings
from .ui_language import load_language, save_language, translate
from .vision_dialog import open_vision_dialog
from .workbench_home import PAGE_CAPTIONS, build_navigation, build_production_page


VALIDATOR_ENV = {ENGLISH: "COMICFLOW_STORYBOARD_VALIDATOR",
                 CHINESE: "COMICFLOW_CHINESE_STORYBOARD_VALIDATOR"}


def validator_preference(rules: str = ENGLISH) -> Path | None:
    home = os.environ.get("LOCALAPPDATA")
    filename = "settings.json" if rules == ENGLISH else "settings-zh.json"
    return Path(home) / "ComicFlow" / filename if home else None


def saved_validator(rules: str = ENGLISH) -> str:
    if supplied := os.environ.get(VALIDATOR_ENV[rules], "").strip():
        return supplied
    path = validator_preference(rules)
    if path:
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("validator", "")
            if isinstance(value, str) and Path(value).is_file():
                return value
        except (OSError, ValueError, AttributeError):
            pass
    bundled = bundled_validator(rules)
    return str(bundled) if bundled else ""


def remember_validator(value: str, rules: str = ENGLISH) -> None:
    target = validator_preference(rules)
    if target is not None and not os.environ.get(VALIDATOR_ENV[rules], "").strip():
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_text(target, json.dumps({"validator": value}, ensure_ascii=False) + "\n")


def open_workbench(initial_zip: str, initial_project: Path | None = None) -> int:
    window = tk.Tk()
    window.ui_language = load_language()
    window.geometry("1160x870")
    window.minsize(900, 700)

    def tr(text):
        return translate(window, text)

    labels = []

    def label_text(widget, caption):
        labels.append((widget, caption))
        widget.configure(text=tr(caption))
        return widget

    selected_rules = tk.StringVar(window, ENGLISH)
    navigation, (production_page, review_page, api_page), rule_buttons = build_navigation(
        window, label_text, change_language=lambda: change_language(), selected_rules=selected_rules,
        switch_rules=lambda rules: switch_rules(rules),
    )
    if initial_zip and initial_project is None:
        navigation.select(review_page)

    options = ttk.LabelFrame(review_page, padding=(8, 5))
    label_text(options, "验收已有 ZIP")
    options.columnconfigure(1, weight=1)
    active_rules = ENGLISH
    validators = {rules: saved_validator(rules) for rules in RULE_LABELS}
    validator_label = tk.StringVar(window)
    entries = (
        ("交付 ZIP", tk.StringVar(value=initial_zip), ("ZIP 交付包", "*.zip")),
        ("校验脚本", tk.StringVar(value=validators[ENGLISH]),
         ("Python 校验脚本", "*.py")),
        ("已批准格数例外（可选）", tk.StringVar(), ("JSON 例外文件", "*.json")),
    )
    review = tk.BooleanVar()
    registry_path = tk.StringVar()
    status = tk.StringVar(window)
    status_data = ("选择 ZIP 检查文件完整性。严格验收需选择故事板校验脚本。", {})

    def set_status(caption, **values):
        nonlocal status_data
        status_data = (caption, values)
        status.set(tr(caption).format(**{key: tr(value) if isinstance(value, str) else value
                                          for key, value in values.items()}))

    def rule_fields():
        caption = "中文校验脚本（严格验收）" if active_rules == CHINESE else "英文校验脚本（严格验收）"
        validator_label.set(tr(caption))
    result: ReviewResult | None = None
    workspace: TemporaryDirectory | None = None
    busy = False
    exit_code = 0
    selected_issue: ReviewIssue | None = None
    strict_review = False
    results: Queue = Queue()
    image_preview = None
    vision_session: dict[str, VisionSettings] = {}
    text_session: dict[str, VisionSettings] = {}
    image_session: dict[str, ImageSettings] = {}

    tabs = ttk.Notebook(review_page)
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
    headings = ("结果", "组", "镜号", "文件", "详情")
    for column, title, width in zip(columns, headings, (95, 90, 80, 210, 460)):
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
            messagebox.showerror(tr("图片无法分析"), tr(str(exc)), parent=window)
            return
        open_vision_dialog(window, path, image, vision_session, rules=active_rules)

    analyze = label_text(ttk.Button(file_row, command=analyze_selected_image, state="disabled"), "AI 辅助看图")
    analyze.pack(side="right", padx=(8, 0))

    def inspect_shots() -> None:
        if result is not None:
            group = selected_issue.group if selected_issue else file_selector.get().partition("/")[0]
            shot = selected_issue.shot if selected_issue else ""
            open_shot_review(window, result, group, shot)

    inspect = label_text(ttk.Button(file_row, command=inspect_shots, state="disabled"), "逐格复核")
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
            set_text(preview_text, tr("此文件不在 ZIP 内。" if path else "选择一个包内文件查看内容。"))
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
                    raise ValueError(tr("图片分辨率超过内置预览限制。"))
                image.thumbnail((max(300, preview_frame.winfo_width() - 25),
                                 max(140, preview_frame.winfo_height() - 95)), Image.Resampling.LANCZOS)
                image_preview = ImageTk.PhotoImage(image)
            preview_text.pack_forget()
            preview_image.configure(image=image_preview)
            preview_image.pack(expand=True, fill="both")
            analyze.configure(state="normal")
        except Exception as exc:
            set_text(preview_text, tr("无法预览 {path}").format(path=path) + f"\n{exc}")

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
        set_running(False)
        if isinstance(completed, Exception):
            exit_code = 1
            set_status("验收未完成")
            set_text(report_text, str(completed))
            tabs.select(report_tab)
            return
        result = completed
        inspect.configure(state="normal" if result.members else "disabled")
        exit_code = result.exit_code
        verdicts = {0: "自动检查通过", 1: "验收失败", 2: "配置错误", 3: "复用未验证"}
        verdict = verdicts.get(result.exit_code, "验收未完成")
        if not strict_review and result.exit_code == 0:
            verdict = "文件完整性检查通过 · 工作流未验"
        set_status("{rules} · {verdict} · {count} 条结果",
                   rules=RULE_LABELS[active_rules], verdict=verdict, count=len(result.issues))
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
        selected = filedialog.askopenfilename(parent=window, filetypes=((tr(kind[0]), kind[1]), (tr("所有文件"), "*")))
        if selected:
            value.set(selected)
            if value is entries[1][1]:
                save_validator_choice()

    def save_validator_choice() -> None:
        value = entries[1][1].get().strip()
        path = Path(value).expanduser()
        validators[active_rules] = value
        if path.suffix.lower() == ".py" and path.is_file():
            validators[active_rules] = str(path.resolve())
            try:
                if path.resolve() != bundled_validator(active_rules):
                    remember_validator(validators[active_rules], active_rules)
            except OSError:
                messagebox.showinfo(tr("校验脚本"), tr("本次可使用所选脚本，下次启动时需重新选择。"), parent=window)

    def produce(path=None, *, action=None, destination="group", owner=None, loaded_project=None, source_id=""):
        save_validator_choice()
        return open_production_dialog(owner or window, validators, registry_path, text_session, image_session,
                                      active_rules, switch_rules, initial_project=path, initial_action=action,
                                      destination=destination, loaded_project=loaded_project, source_id=source_id)

    def clear_review() -> None:
        nonlocal result, selected_issue
        result = selected_issue = None
        inspect.configure(state="disabled")
        table.delete(*table.get_children())
        file_selector.configure(values=())
        file_selector.set("")
        location.configure(text="")
        show_preview()
        set_text(report_text, "")

    def switch_rules(rules: str) -> None:
        nonlocal active_rules, exit_code
        if rules == active_rules:
            return
        save_validator_choice()
        active_rules = rules
        selected_rules.set(rules)
        entries[1][1].set(validators[rules])
        rule_fields()
        for widget in exception_widgets:
            widget.state(["!disabled"] if rules == ENGLISH else ["disabled"])
        clear_review()
        exit_code = 0
        set_status("{rules} · SB 规则 v{version}", rules=RULE_LABELS[rules], version=rule_revision(rules))

    def set_running(running: bool) -> None:
        for widget in (start_button, *workflow_buttons, *rule_buttons, *checks.winfo_children()):
            widget.state(["disabled"] if running else ["!disabled"])

    def start() -> None:
        nonlocal busy, workspace, strict_review
        archive, validator, exception = (Path(value.get().strip()).expanduser() for _, value, _ in entries)
        if active_rules == CHINESE:
            exception = Path()
        required = ((archive, ".zip", "交付 ZIP"),)
        if validator != Path():
            required += ((validator, ".py", "校验脚本"),)
        for path, suffix, label in required:
            if path.suffix.lower() != suffix or not path.is_file():
                messagebox.showerror(tr("文件未找到"), tr("请选择有效的{label}。").format(label=tr(label)), parent=window)
                return
        if exception != Path() and (exception.suffix.lower() != ".json" or not exception.is_file()):
            messagebox.showerror(tr("文件未找到"), tr("请选择有效的格数例外 JSON。"), parent=window)
            return

        strict_review = validator != Path()
        if exception != Path() and not strict_review:
            messagebox.showerror(tr("校验脚本"), tr("使用批准格数例外前，请选择现行故事板校验脚本。"), parent=window)
            return
        arguments = [str(archive.resolve())]
        if strict_review:
            save_validator_choice()
            arguments.extend(("--storyboard-validator", str(validator.resolve())))
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
        clear_review()
        set_running(True)
        set_status("正在验收 {archive}…", archive=archive.name)

        def worker() -> None:
            try:
                results.put(run_review(arguments, directory))
            except Exception as exc:
                results.put(exc)

        Thread(target=worker, daemon=True).start()
        window.after(100, receive)

    def close() -> None:
        if busy:
            messagebox.showinfo(tr("验收进行中"), tr("当前正在读取交付包，请等待验收完成。"), parent=window)
            return
        window.destroy()

    def change_language():
        window.ui_language = "en" if window.ui_language == "zh" else "zh"
        refresh_language()
        try:
            save_language(window.ui_language)
        except OSError:
            messagebox.showinfo(tr("界面语言"), tr("本次可切换界面语言。下次启动时需重新选择。"), parent=window)

    def refresh_language():
        window.title(tr("ComicFlow 漫剧制片工作台"))
        for widget, caption in labels:
            widget.configure(text=tr(caption))
        for page, caption in zip((production_page, review_page, api_page), PAGE_CAPTIONS):
            navigation.tab(page, text=tr(caption))
        refresh_api_language()
        for column, caption in zip(columns, headings):
            table.heading(column, text=tr(caption))
        tabs.tab(issues_tab, text=tr("验收结果"))
        tabs.tab(report_tab, text=tr("完整报告"))
        rule_fields()
        set_status(status_data[0], **status_data[1])
        if result is None:
            show_preview()

    def plan_script(task):
        from .script_handoff_dialog import choose_project_for_script
        from .storyboard_planning_dialog import open_storyboard_planning

        def use_script(title, body):
            editor = planner.window
            selected = choose_project_for_script(editor, title, body, active_rules)
            if selected is None:
                return False
            path, project, source = selected
            production = produce(path, destination="shots", owner=editor, loaded_project=project, source_id=source.id)
            editor.wait_window(production.window)
            editor.grab_set()
            return True

        planner = open_storyboard_planning(window, text_session, task=task, rules=active_rules,
                                           on_use_script=use_script if task == "script" else None)

    def inspect_image():
        from .review_tools_dialog import open_image_inspection

        open_image_inspection(window)

    def inspect_cuts():
        from .review_tools_dialog import open_cut_review

        open_cut_review(window, result, active_rules)

    def choose_delivery_zip():
        navigation.select(review_page)
        browse(entries[0][1], entries[0][2])

    callbacks = {
        "new": lambda: produce(action="new"),
        "open": lambda: produce(action="open"),
        "review_zip": choose_delivery_zip,
        "group": produce,
        "script": lambda: plan_script("script"),
        "inventory": lambda: plan_script("assets"),
        "preflight": lambda: open_preflight_dialog(window, entries[1][1].get().strip(), active_rules),
    }
    for destination in ("shots", "assets", "generate_assets", "generate_board", "layout", "prompts",
                        "costume", "pose", "deliver"):
        callbacks[destination] = lambda view=destination: produce(action="open", destination=view)
    workflow_buttons = build_production_page(production_page, label_text, callbacks)
    refresh_api_language, sync_api = build_api_settings(api_page, text_session, vision_session, image_session, label_text)

    def sync_selected_page(event):
        if event.widget is navigation and navigation.select() == str(api_page):
            sync_api()

    navigation.bind("<<NotebookTabChanged>>", sync_selected_page)
    checks = ttk.Frame(review_page, padding=(12, 7, 12, 2))
    checks.pack(fill="x")
    for caption, action in (
        ("图片大小与比例", inspect_image),
        ("景别机位与格间衔接", inspect_cuts),
        ("资产与返修", lambda: open_asset_repair(window, registry_path, entries[1][1].get().strip(), result)),
    ):
        label_text(ttk.Button(checks, command=action, style="Workbench.TButton"), caption).pack(
            side="left", padx=(0, 7))
    options.pack(fill="x", padx=16, pady=(1, 4))
    for row, (label, value, kind) in enumerate(entries):
        caption = ttk.Label(options, textvariable=validator_label) if row == 1 else label_text(ttk.Label(options), label)
        caption.grid(row=row, column=0, sticky="w", padx=(2, 8), pady=2)
        field = ttk.Entry(options, textvariable=value, width=58)
        field.grid(row=row, column=1, sticky="ew")
        picker = label_text(ttk.Button(options, command=lambda v=value, k=kind: browse(v, k)), "浏览")
        picker.grid(row=row, column=2, padx=(8, 2), pady=2, sticky="ew")
        if row == 2:
            exception_widgets = (field, picker)
    label_text(ttk.Checkbutton(options, variable=review), "将不可访问的复用原图标为未验证").grid(
        row=3, column=1, sticky="w", pady=2,
    )
    start_button = label_text(ttk.Button(options, command=start, style="Primary.Workbench.TButton"), "开始验收")
    start_button.grid(row=3, column=2, padx=(8, 2), pady=3, sticky="ew")
    ttk.Label(options, textvariable=status).grid(row=4, column=0, columnspan=3, sticky="w", padx=2)
    tabs.pack(expand=True, fill="both", padx=16, pady=(0, 10))
    refresh_language()
    window.protocol("WM_DELETE_WINDOW", close)
    if initial_project is not None:
        window.after_idle(lambda: produce(initial_project))
    try:
        window.mainloop()
    finally:
        if workspace and not busy:
            workspace.cleanup()
    return exit_code


def main() -> int:
    initial = sys.argv[1] if len(sys.argv) > 1 else ""
    if Path(initial).suffix.casefold() == ".cfproject":
        return open_workbench("", Path(initial).expanduser().resolve())
    return open_workbench(initial)


if __name__ == "__main__":
    raise SystemExit(main())
