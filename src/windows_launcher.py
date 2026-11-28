"""Local storyboard review window."""

from io import BytesIO
import json
import os
import re
import sys
import tkinter as tk
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from .action_workspace import ActionWorkspace
from .api_settings_dialog import build_api_settings
from .asset_repair_dialog import open_asset_repair
from .brand import APP_FOLDER, app_name
from .preflight_dialog import open_preflight_dialog
from .production_dialog import open_production_dialog
from .bundled_validators import bundled_validator
from .ecommerce_page import EcommercePage
from .guide_links import guide_button, refresh_guide_buttons
from .practice_project import make_practice, practice_example
from .production_project import atomic_text
from .production_rules import CHINESE, ENGLISH, RULE_LABELS, rule_revision
from .production_workspace import ProductionWorkspace, StageEditor
from .desktop_runtime import application_data
from .image_api import ImageSettings
from .release_notes import open_release_notes
from .shot_review_dialog import open_shot_review
from .storyboard_guide import StoryboardGuide
from .storyboard_review import PREVIEW_LIMIT, ReviewIssue, ReviewResult, read_preview, run_review
from .vision import VisionSettings
from .ui_language import load_language, save_language, translate
from .vision_dialog import open_vision_dialog, vision_job_key
from .workbench_jobs import JobOutcome, WorkbenchJobs, build_job_center
from .workbench_home import build_navigation, build_production_page
from .workbench_practice import (
    PRACTICE_SOURCES, REVIEW_GROUPS, REVIEW_REGISTRY, available_practices, make_workbench_practice,
)
from .workbench_tutorial import build_tutorial


BATCH_STAGES = ("import", "plan", "assets", "queue", "delivery")


class WorkbenchPanelTask:
    """A tab for a whole workbench panel or a file review."""

    project = None
    path = None
    confirmation = None

    def __init__(self, page, caption, build):
        self.page, self.title = page, caption
        frame = ttk.Frame(page)
        frame.pack(fill="both", expand=True)
        self.editor = StageEditor(frame)
        self.editor.controller = build(frame)

    def caption(self, *, distinguish=False):
        return translate(self.page, self.title)

    def full_caption(self):
        return self.caption()

    def activate(self):
        activate = getattr(self.editor.controller, "activate", None)
        if activate:
            activate()

    def refresh_language(self):
        refresh = getattr(self.editor.controller, "refresh_language", None)
        if refresh:
            refresh()


VALIDATOR_ENV = {ENGLISH: "COMICFLOW_STORYBOARD_VALIDATOR",
                 CHINESE: "COMICFLOW_CHINESE_STORYBOARD_VALIDATOR"}


def validator_preference(rules: str = ENGLISH) -> Path | None:
    home = application_data()
    filename = "settings.json" if rules == ENGLISH else "settings-zh.json"
    return home / filename if home else None


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


def open_workbench(initial_zip: str, initial_project: Path | None = None, *, initial_batch: Path | None = None, on_ready=None) -> int:
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

    release_window = None
    refresh_release = None

    def show_release_notes():
        nonlocal release_window, refresh_release
        if release_window is None or not release_window.winfo_exists():
            release_window, refresh_release = open_release_notes(window)
        else:
            release_window.deiconify()
            release_window.lift()
            release_window.focus_set()

    selected_rules = tk.StringVar(window, ENGLISH)
    tasks, _, help_menu = build_navigation(
        window, label_text, change_language=lambda: change_language(), selected_rules=selected_rules,
        switch_rules=lambda rules: switch_rules(rules), show_release_notes=show_release_notes,
    )
    navigation = tasks.notebook
    production_page, ecommerce_page, review_page, api_page, tutorial_page = tasks.pages
    jobs = WorkbenchJobs(window)
    api_origin = ""
    api_explicit = False
    help_origin = ""
    suspended_help = None
    known_projects = set()
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
    review_rules = ENGLISH
    review_source = None
    image_preview = None
    vision_session: dict[str, VisionSettings] = {}
    text_session: dict[str, VisionSettings] = {}
    image_session: dict[str, ImageSettings] = {}
    active_batch = None
    current_work = None

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

    def show_vision(raw, origin):
        archive, member, rules = origin
        key = vision_job_key(origin, raw)

        def build(body):
            return open_vision_dialog(
                window, member, raw, vision_session, rules=rules, job_registry=jobs, origin=origin,
                mount=body, on_recover=lambda _key: show_vision(raw, origin), on_open_api=go_to_api,
            )

        return tasks.open(("vision", key), lambda page, _: WorkbenchPanelTask(page, "AI 辅助看图", build))

    def analyze_selected_image() -> None:
        path = file_selector.get()
        if result is None or path not in result.members or path.lower().endswith(".txt"):
            return
        try:
            image = read_preview(result, path)
        except (OSError, ValueError) as exc:
            messagebox.showerror(tr("图片无法分析"), tr(str(exc)), parent=window)
            return
        show_vision(image, (review_source or result.archive, path, review_rules))

    analyze = label_text(ttk.Button(file_row, command=analyze_selected_image, state="disabled"), "AI 辅助看图")
    analyze.pack(side="right", padx=(8, 0))

    def inspect_shots() -> None:
        if result is not None:
            group = selected_issue.group if selected_issue else file_selector.get().partition("/")[0]
            shot = selected_issue.shot if selected_issue else ""
            open_shot_review(window, result, group, shot, help_topic="review_cuts")

    inspect = label_text(ttk.Button(file_row, command=inspect_shots, state="disabled"), "逐格复核")
    inspect.pack(side="right", padx=(8, 0))

    def return_to_production():
        from .review_repair_bridge import open_review_repair

        if result is not None:
            open_review_repair(
                window, result, selected_issue, source_archive=review_source,
                selected_member=file_selector.get(), project_paths=tuple(review_project_paths()),
                open_production=production_workspace.open,
            )

    repair = label_text(ttk.Button(file_row, name="return_to_production", command=return_to_production,
                                  state="disabled"), "回到制作返修")
    repair.pack(side="right", padx=(8, 0))

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

    def receive(completed):
        nonlocal busy, result, exit_code
        busy = False
        set_running(False)
        if isinstance(completed, Exception):
            exit_code = 1
            set_status("验收未完成")
            set_text(report_text, str(completed))
            tabs.select(report_tab)
            return JobOutcome("failed", str(completed))
        result = completed
        inspect.configure(state="normal" if result.members else "disabled")
        repair.configure(state="normal" if result.members else "disabled")
        exit_code = result.exit_code
        verdicts = {0: "自动检查通过", 1: "验收失败", 2: "配置错误", 3: "复用未验证"}
        verdict = verdicts.get(result.exit_code, "验收未完成")
        if not strict_review and result.exit_code == 0:
            verdict = "文件完整性检查通过 · 工作流未验"
        set_status("{rules} · {verdict} · {count} 条结果",
                   rules=RULE_LABELS[review_rules], verdict=verdict, count=len(result.issues))
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
        return JobOutcome("ready", tr(verdict))

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

    def refresh_current_work():
        if current_work is None:
            refresh_production()
            return
        meta = " · ".join(str(value) for value in (
            current_work["episode"], current_work.get("group"), tr(RULE_LABELS[current_work["rules"]]),
        ) if value)
        refresh_production(project_title=current_work["title"], project_meta=meta,
                           progress=current_work.get("progress"), next_step=current_work["step"])

    def remember_project(project, path):
        nonlocal current_work
        path = Path(path).resolve()
        known_projects.add(path)
        current_work = {
            "kind": "group", "path": path, "title": project.name or path.stem,
            "episode": project.episode, "group": project.group, "rules": project.rules,
            "step": 1 if project.sources else 0,
        }
        window.after_idle(refresh_current_work)

    def produce(path=None, *, action=None, destination="group", owner=None, loaded_project=None, source_id=""):
        save_validator_choice()
        dialog = open_production_dialog(owner or window, validators, registry_path, text_session, image_session,
                                       active_rules, switch_rules, initial_project=path, initial_action=action,
                                       destination=destination, loaded_project=loaded_project, source_id=source_id)
        if dialog is None:
            return None

        def open_in_workbench():
            if dialog.allow_leave():
                location = dialog.path
                dialog.window.destroy()
                action_workspace.open(location)

        if owner is None:
            dialog.action_workspace = open_in_workbench

        def remember_group(event):
            if event.widget is not dialog.window or dialog.project is None or dialog.path is None:
                return
            remember_project(dialog.project, dialog.path)

        dialog.window.bind("<Destroy>", remember_group, add="+")
        return dialog

    def review_project_paths():
        yield from known_projects
        if active_batch is not None and active_batch.frame.winfo_exists() and active_batch.workspace is not None:
            for episode in active_batch.workspace.episodes:
                yield from active_batch.workspace.group_paths(episode.id)

    def batch_center(path=None, *, stage=None, episode=None, group=None):
        nonlocal active_batch
        from .batch_dialog import BatchDialog

        key = ("batch_center",)
        save_validator_choice()

        def open_group(group_path, rules, parent, *, destination="shots", adjacent_path=None,
                       image_job_id=None, shot_id=None):
            from .production_project import ProductionProject

            group_project = ProductionProject.open(group_path)
            if group_project.rules != rules:
                raise ValueError(tr("项目制作规则与当前批量任务不一致。"))
            if image_job_id:
                image_job = next((job for job in group_project.image_jobs if job["id"] == image_job_id), None)
                destination = "generate_board" if image_job and image_job["kind"] == "故事板" else "generate_assets"
            else:
                destination = {"review": "deliver", "handoff": "layout"}.get(destination, destination)
            return production_workspace.open(
                destination, group_path, project=group_project, adjacent_path=adjacent_path, job_id=image_job_id,
                shot_id=shot_id, batch_context=(active_batch.workspace.path, group_project.episode, group_project.group),
            )

        def remember_batch(center):
            nonlocal current_work
            if center.workspace is None:
                return
            groups = center.view.get("delivery_groups", ())
            progress = (sum(bool(group["ready"]) for group in groups), len(groups)) if groups else None
            current_work = {
                "kind": "batch", "path": center.workspace.path, "title": center.workspace.title,
                "episode": center.episode_id, "rules": center.workspace.rules,
                "progress": progress, "step": BATCH_STAGES.index(center.recommended_stage()),
            }
            refresh_current_work()

        def build(body):
            center = BatchDialog(window, active_rules, text_session, image_session, validators, open_group,
                                 mount=body, on_close=lambda: tasks.request_close(key), on_api=go_to_api)
            center.on_workbench_update = remember_batch
            return center

        panel = tasks.open(key, lambda page, _: WorkbenchPanelTask(page, "批量制作中心", build))
        active_batch = center = panel.editor.controller
        if path is not None and (center.workspace is None or Path(path).resolve() != center.workspace.path.resolve()):
            center.open_path(Path(path), episode_id=episode, group_id=group, stage=stage)
        else:
            center.locate(episode_id=episode, group_id=group, stage=stage)

    def locate_batch(path, episode, group):
        batch_center(path, episode=episode, group=group)

    def batch_stage(index):
        recent = current_work if current_work and current_work["kind"] == "batch" else None
        batch_center(recent["path"] if recent else None, stage=BATCH_STAGES[index],
                     episode=recent["episode"] if recent else None)

    def resume_work():
        if current_work is None:
            batch_center(stage="import")
        elif current_work["kind"] == "batch":
            batch_stage(current_work["step"])
        else:
            produce(current_work["path"])

    def clear_review() -> None:
        nonlocal result, selected_issue
        result = selected_issue = None
        inspect.configure(state="disabled")
        repair.configure(state="disabled")
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
        if not busy and result is None:
            exit_code = 0
            set_status("{rules} · SB 规则 v{version}", rules=RULE_LABELS[rules], version=rule_revision(rules))

    def set_running(running: bool) -> None:
        start_button.state(["disabled"] if running else ["!disabled"])

    def start() -> None:
        nonlocal busy, workspace, strict_review, review_source, review_rules
        if busy:
            return
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
        review_source, review_rules = archive.resolve(), active_rules
        clear_review()
        set_running(True)
        set_status("正在验收 {archive}…", archive=archive.name)

        jobs.start(("archive_review",), "最近一次交付验收", str(review_source),
                   lambda _key: tasks.select(review_page), lambda: run_review(arguments, directory), receive)

    def close() -> None:
        if suspended_help:
            return_from_help()
            return
        modal = window.grab_current()
        if modal is not None and modal.winfo_toplevel() != window:
            modal.winfo_toplevel().lift()
            return
        if jobs.active:
            messagebox.showinfo(tr("任务进行中"), tr("请求仍在运行，可以从任务中心查看。"), parent=window)
            return
        if busy:
            messagebox.showinfo(tr("验收进行中"), tr("当前正在读取交付包，请等待验收完成。"), parent=window)
            return
        if tasks.allow_close() and ecommerce.allow_close():
            window.destroy()

    def change_language():
        window.ui_language = "en" if window.ui_language == "zh" else "zh"
        refresh_language()
        try:
            save_language(window.ui_language)
        except OSError:
            messagebox.showinfo(tr("界面语言"), tr("本次可切换界面语言。下次启动时需重新选择。"), parent=window)

    def refresh_language():
        window.title(app_name(window.ui_language))
        for widget, caption in labels:
            widget.configure(text=tr(caption))
        help_menu.entryconfigure(0, label=tr("更新日志"))
        if release_window is not None and release_window.winfo_exists():
            refresh_release()
        tasks.refresh_language()
        production_workspace.refresh_language()
        refresh_current_work()
        refresh_api_language()
        refresh_tutorial()
        storyboard_guide.refresh()
        refresh_guide_buttons(window)
        ecommerce.refresh_language()
        for column, caption in zip(columns, headings):
            table.heading(column, text=tr(caption))
        tabs.tab(issues_tab, text=tr("验收结果"))
        tabs.tab(report_tab, text=tr("完整报告"))
        rule_fields()
        set_status(status_data[0], **status_data[1])
        if result is None:
            show_preview()

    def inspect_image():
        from .review_tools_dialog import open_image_inspection

        open_image_inspection(window)

    def inspect_cuts():
        from .review_tools_dialog import open_cut_review

        open_cut_review(window, result, review_rules if result is not None else active_rules)

    def go_to_api():
        nonlocal api_origin, api_explicit
        selected = navigation.select()
        if selected and selected != str(api_page):
            api_origin, api_explicit = selected, True
        tasks.select(api_page)

    def return_from_api():
        if api_origin in navigation.tabs() and api_origin != str(api_page):
            tasks.select(api_origin)
        else:
            tasks.select(production_page)

    def open_jobs():
        def build(body):
            panel = build_job_center(body, jobs)
            panel.pack(fill="both", expand=True)
            return panel

        tasks.open(("jobs",), lambda page, _: WorkbenchPanelTask(
            page, "任务中心", build,
        ))

    def choose_delivery_zip():
        navigation.select(review_page)
        browse(entries[0][1], entries[0][2])

    def restore_help_modal():
        nonlocal suspended_help
        if suspended_help is None:
            return
        holder, status, focus, ancestors = suspended_help
        suspended_help = None
        for dialog, state in reversed(ancestors):
            if dialog.winfo_exists():
                dialog.state(state)
                dialog.lift()
        window.update_idletasks()
        if holder is not None and holder.winfo_exists():
            if status == "global":
                holder.grab_set_global()
            else:
                holder.grab_set()
        if focus is not None and focus.winfo_exists() and focus.winfo_viewable():
            focus.focus_set()

    def show_storyboard_help(topic="home", *, contextual=True, source=None):
        nonlocal help_origin, suspended_help
        selected = navigation.select()
        if selected != str(tutorial_page):
            help_origin = selected if contextual else ""
        elif not contextual:
            help_origin = ""
        if contextual:
            holder = window.grab_current()
            grabbed = holder.winfo_toplevel() if holder is not None else window
            originating = source.winfo_toplevel() if source is not None else window
            focus, status, ancestors = window.focus_get(), None, []
            if grabbed != window:
                status = holder.grab_status()
                holder.grab_release()
            for dialog in (grabbed, originating):
                while dialog != window:
                    state = dialog.state()
                    if state in ("normal", "zoomed"):
                        ancestors.append((dialog, state))
                        dialog.withdraw()
                    dialog = dialog.master.winfo_toplevel()
            if ancestors:
                suspended_help = holder if status else None, status, focus, ancestors
        tutorial_overview.pack_forget()
        storyboard_guide.frame.pack(fill="both", expand=True)
        storyboard_guide.show(
            topic, contextual=bool(help_origin or suspended_help),
            can_practice=not suspended_help and practice_example(examples, active_rules).is_file(),
            allow_overview=suspended_help is None,
            workbench_practices=available_practices(examples) if suspended_help is None else (),
        )
        tasks.select(tutorial_page)

    def return_from_help():
        nonlocal help_origin, api_explicit
        origin = help_origin
        help_origin = ""
        if origin == str(api_page):
            api_explicit = True
        tasks.select(origin if origin in navigation.tabs() and origin != str(tutorial_page) else production_page)
        restore_help_modal()

    def show_tutorial_overview():
        storyboard_guide.frame.pack_forget()
        tutorial_overview.pack(fill="both", expand=True)

    window.open_storyboard_help = show_storyboard_help
    action_workspace = ActionWorkspace(
        window, tasks, lambda: active_rules,
        lambda: current_work["path"] if current_work and current_work["kind"] == "group" else None,
        remember_project,
    )
    production_workspace = ProductionWorkspace(
        window, tasks,
        lambda: current_work["path"] if current_work and current_work["kind"] == "group" else None,
        lambda: active_rules, validators, registry_path, text_session, image_session, remember_project,
        action_workspace.open, jobs=jobs, open_api=go_to_api, on_batch_group=locate_batch,
    )

    def open_stage(stage):
        action_workspace.hide()
        production_workspace.ask_project(stage)

    def open_actions():
        production_workspace.hide()
        action_workspace.show()

    def open_script():
        action_workspace.hide()
        production_workspace.hide()
        production_workspace.open("script")

    callbacks = {
        "new": lambda: produce(action="new"),
        "batch": batch_center,
        "batch_step": batch_stage,
        "resume": resume_work,
        "open": lambda: produce(action="open"),
        "review_zip": choose_delivery_zip,
        "group": produce,
        "script": open_script,
        "inventory": lambda: open_stage("inventory"),
        "action_sequence": open_actions,
        "jobs": open_jobs,
        "preflight": lambda: open_preflight_dialog(window, entries[1][1].get().strip(), active_rules),
    }
    for destination in ("shots", "assets", "generate_assets", "generate_board", "layout", "prompts",
                        "costume", "pose", "deliver"):
        callbacks[destination] = lambda view=destination: open_stage(view)
    _, refresh_production = build_production_page(
        production_page, label_text, callbacks, action_picker=action_workspace,
        production_picker=production_workspace,
    )
    api_tools = ttk.Frame(api_page, padding=(10, 6))
    api_tools.pack(fill="x")
    label_text(ttk.Button(api_tools, name="api_return", command=return_from_api), "返回发起页").pack(anchor="w")
    refresh_api_language, sync_api = build_api_settings(api_page, text_session, vision_session, image_session, label_text)
    ecommerce = EcommercePage(ecommerce_page, vision_session, image_session, go_to_api, inline=True)
    examples = Path(__file__).resolve().parents[1] / "Examples"
    sample_available = (examples / "SB01.cfproject").is_file()

    def open_tutorial_sample():
        path = practice_example(examples, active_rules)
        if path.is_file():
            produce(path, destination="shots")
        else:
            callbacks["open"]()

    def start_practice(kind):
        if kind == "review" and busy:
            messagebox.showinfo(tr("验收进行中"), tr("当前正在读取交付包，请等待验收完成。"), parent=window)
            return
        directory = filedialog.askdirectory(
            parent=window,
            title="Choose a folder for practice files" if window.ui_language == "en" else "选择练习文件的保存位置",
            mustexist=True,
        )
        if not directory:
            return
        try:
            if kind in PRACTICE_SOURCES:
                open_workbench_practice(kind, make_workbench_practice(examples, directory, kind))
                return
            path = make_practice(examples, directory, active_rules, existing=kind == "existing")
            if kind == "existing":
                production_workspace.open("assets", path)
            else:
                production_workspace.open("script", practice_script=path)
        except (OSError, ValueError, RuntimeError, tk.TclError) as error:
            production_workspace.show_error(error)

    def open_workbench_practice(kind, path):
        if kind == "ecommerce":
            if ecommerce.open_path(path):
                tasks.select(ecommerce_page)
        elif kind == "batch":
            batch_center(path, stage="plan")
        else:
            entries[0][1].set(str(path))
            entries[2][1].set("")
            registry_path.set(str(path.with_name(REVIEW_REGISTRY)))
            known_projects.update(path.with_name(filename) for filename in REVIEW_GROUPS)
            clear_review()
            set_status("已准备练习包。请选择英文影片制作，然后开始验收。")
            tasks.select(review_page)

    tutorial_overview = ttk.Frame(tutorial_page, name="tutorial_overview")
    tutorial_overview.pack(fill="both", expand=True)
    refresh_tutorial, _ = build_tutorial(
        tutorial_overview,
        {"start": callbacks["new"], "production": callbacks["script"],
         "review": choose_delivery_zip, "api": go_to_api},
        sample_action=open_tutorial_sample if sample_available else None,
        open_storyboard_guide=lambda: show_storyboard_help(contextual=False),
        open_workbench_guide=lambda: show_storyboard_help("general", contextual=False),
    )
    storyboard_guide = StoryboardGuide(tutorial_page, on_return=return_from_help, on_overview=show_tutorial_overview,
                                      on_practice=start_practice)

    def sync_selected_page(event):
        nonlocal api_origin, api_explicit
        if event.widget is not navigation:
            return
        if navigation.select() != str(tutorial_page):
            restore_help_modal()
        if navigation.select() != str(api_page):
            api_explicit = False
            return
        if not api_explicit:
            api_origin = next((page for page in reversed(tasks.recent) if page != str(api_page)), "")
        sync_api()

    navigation.bind("<<NotebookTabChanged>>", sync_selected_page, add="+")
    checks = ttk.Frame(review_page, padding=(12, 7, 12, 2))
    checks.pack(fill="x")
    for caption, action in (
        ("图片大小与比例", inspect_image),
        ("景别机位与格间衔接", inspect_cuts),
        ("资产与返修", lambda: open_asset_repair(window, registry_path, entries[1][1].get().strip(), result)),
    ):
        label_text(ttk.Button(checks, command=action, style="Workbench.TButton"), caption).pack(
            side="left", padx=(0, 7))
    label_text(ttk.Button(checks, name="workbench_jobs", command=open_jobs, style="Workbench.TButton"),
               "任务中心").pack(side="left", padx=(0, 7))
    guide_button(checks, "review_zip").pack(side="right")
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
    if initial_batch is not None:
        window.after_idle(lambda: batch_center(initial_batch))
    elif initial_project is not None:
        window.after_idle(lambda: produce(initial_project))
    if on_ready is not None:
        window.after_idle(lambda: on_ready(window))
    try:
        window.mainloop()
    finally:
        if workspace and not busy:
            workspace.cleanup()
    return exit_code


def main() -> int:
    initial = sys.argv[1] if len(sys.argv) > 1 else ""
    if Path(initial).suffix.casefold() == ".cfbatch":
        return open_workbench("", initial_batch=Path(initial).expanduser().resolve())
    if Path(initial).suffix.casefold() == ".cfproject":
        return open_workbench("", Path(initial).expanduser().resolve())
    return open_workbench(initial)


if __name__ == "__main__":
    raise SystemExit(main())
