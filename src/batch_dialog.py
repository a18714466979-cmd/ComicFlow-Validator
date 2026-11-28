"""Desktop batch center for script planning, resumable production and reviewed delivery."""

import json
import re
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .batch_planning import coverage_issues, trace_rows
from .batch_workspace import BatchWorkspace
from .batch_runner import BatchQueue
from .batch_delivery import publish_episode, publish_series
from .production_handoff import reviewed_boundary
from .production_project import ProductionProject
from .production_rules import CHINESE, rule_revision
from .workbench_style import AMBER, GREEN, INK, LINE, SURFACE, configure_workbench


SCRIPT_FILES = (("UTF-8 text / Markdown", "*.txt *.md"),)
TASK_KINDS = {"shot": ("分镜", "Shot"), "prompt": ("提示词", "Prompt"),
              "board": ("故事板", "Board"), "plate": ("净板", "Clean plate")}
TASK_STATES = {"queued": ("待运行", "Queued"), "running": ("运行中", "Running"),
               "blocked": ("待前置步骤", "Blocked"), "uncertain": ("需核实扣费", "Check submission"),
               "failed": ("失败", "Failed"), "review": ("待审候选", "Review candidate"),
               "approved": ("已采纳", "Approved"), "polling": ("等待服务商", "Awaiting provider")}


STAGES = (
    ("import", "导入剧本", "Import scripts"),
    ("plan", "整集规划", "Episode plan"),
    ("assets", "公共资产", "Shared assets"),
    ("queue", "执行队列", "Production queue"),
    ("delivery", "验收交付", "Review & delivery"),
)
STEP_LABELS = {
    "import": "Import scripts", "plan": "Plan", "assets": "Shared assets",
    "queue": "Job queue", "delivery": "Review & delivery",
}
GROUP_STATES = {
    "ready": ("已复核", "Reviewed"),
    "visual": ("待逐格复核", "Review panels"),
    "handoff": ("待核对交接", "Review handoff"),
    "missing": ("无法读取项目", "Project unreadable"),
}


class BatchDialog:
    def __init__(self, parent, rules, text_session, image_session, validators, open_group):
        self.rules = rules
        self.text_session = text_session
        self.image_session = image_session
        self.validators = validators
        self.open_group = open_group
        self.window = tk.Toplevel(parent)
        self.english = getattr(self.window._root(), "ui_language", "zh") == "en"
        configure_workbench(self.window)
        self.window.title(self.t("批量制作中心", "Batch production center"))
        max_height = max(480, self.window.winfo_screenheight() - 72)
        scaling = float(self.window.tk.call("tk", "scaling")) / (96 / 72)
        min_height = min(max_height, max(600, round(595 * scaling)))
        self.window.geometry(f"1080x{min(max_height, max(760, min_height))}")
        self.window.minsize(770, min_height)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.grab_set()
        self.workspace = None
        self.view = {}
        self.busy = False
        self.stop = None
        self.episode_id = ""
        self.episode_ids = []
        self.controls = []
        self.on_workbench_update = None
        self.stage = "plan"
        self.review_rows = {}
        self.step_columns = None
        self.status = tk.StringVar(self.window, self.t("先新建批次，再导入一集或多集剧本。", "Create a batch, then import one or more scripts."))
        self.heading = tk.StringVar(self.window, self.t("尚未打开批次", "No batch open"))
        self.summary = tk.StringVar(self.window)
        self.search = tk.StringVar(self.window)
        self.budget = tk.StringVar(self.window, "10")
        self.queue_status = tk.StringVar(self.window)
        self.asset_status = tk.StringVar(self.window)
        self.build()
        self.set_controls()

    def t(self, zh, en):
        return en if self.english else zh

    def guarded(self, callback):
        if not self.busy:
            try:
                callback()
            except Exception as error:
                self.error(error)

    def error(self, error):
        messagebox.showerror(self.window.title(), str(error), parent=self.window)

    def button(self, bar, zh, en, action, needs="episode", *, primary=False, side="left"):
        style = "Primary.Workbench.TButton" if primary else "Workbench.TButton"
        button = ttk.Button(bar, text=self.t(zh, en), width=0, style=style, command=lambda: self.guarded(action))
        button.pack(side=side, padx=(0, 6) if side == "left" else (6, 0), pady=3)
        self.controls.append((button, needs))
        return button

    def toolbar(self, page):
        bar = ttk.Frame(page, style="A.TFrame")
        bar.pack(fill="x", pady=(0, 3))
        return bar

    def wrap_toolbar(self, bar):
        controls = []
        for widget in bar.pack_slaves():
            options = widget.pack_info()
            options.pop("in")
            horizontal = options["padx"]
            padding = 2 * horizontal if isinstance(horizontal, int) else sum(map(int, horizontal))
            controls.append((widget, options, widget.winfo_reqwidth() + padding))
        previous = None
        rows = []

        def arrange(event):
            nonlocal previous
            lines = [[]]
            remaining = event.width
            for index, (_, _, width) in enumerate(controls):
                if lines[-1] and width > remaining:
                    lines.append([])
                    remaining = event.width
                lines[-1].append(index)
                remaining -= width
            if lines == previous:
                return
            previous = lines
            for widget, _, _ in controls:
                widget.pack_forget()
            for row in rows:
                row.destroy()
            rows.clear()
            for line in lines:
                row = ttk.Frame(bar, style="A.TFrame")
                row.pack(fill="x")
                rows.append(row)
                for index in line:
                    widget, options, _ = controls[index]
                    widget.pack(in_=row, **options)

        bar.bind("<Configure>", arrange, add="+")

    def note(self, parent, zh, en):
        label = ttk.Label(parent, text=self.t(zh, en), style="A.Muted.TLabel", wraplength=740, justify="left")
        label.pack(fill="x", anchor="w", pady=(2, 5))
        parent.bind("<Configure>", lambda event: label.configure(wraplength=max(100, event.width - 24)), add="+")
        return label

    def table(self, page, name, columns, height):
        area = ttk.Frame(page, style="A.TFrame")
        area.pack(fill="both", expand=True)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        table = ttk.Treeview(area, name=name, style="A.Treeview", columns=[x[0] for x in columns],
                             show="headings", selectmode="browse", height=height)
        for key, zh, en, size in columns:
            table.heading(key, text=self.t(zh, en))
            table.column(key, width=size, minwidth=43, stretch=key in {"text", "message", "identity", "state_name", "scene"})
        vertical = ttk.Scrollbar(area, orient="vertical", command=table.yview)
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=table.xview)
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        return table

    def build(self):
        body = ttk.Frame(self.window, padding=(18, 12), style="A.TFrame")
        body.pack(fill="both", expand=True)
        header = self.toolbar(body)
        self.button(header, "关闭", "Close", self.close, "always", side="right")
        ttk.Label(header, text=self.window.title(), style="A.TLabel",
                  font=("TkDefaultFont", 17, "bold")).pack(anchor="w")
        heading = ttk.Label(body, textvariable=self.heading, style="A.Muted.TLabel", wraplength=850)
        heading.pack(fill="x", pady=(1, 6))
        body.bind("<Configure>", lambda event: heading.configure(wraplength=max(200, event.width - 40)), add="+")

        self.step_row = ttk.Frame(body, style="A.TFrame")
        self.step_row.pack(fill="x", pady=(0, 8))
        self.steps = {}
        for key, zh, en in STAGES:
            self.steps[key] = ttk.Button(self.step_row, name=f"step_{key}", text=self.t(zh, en), width=0,
                                         style="A.Step.TButton", command=lambda stage=key: self.select_stage(stage))
        self.step_row.bind("<Configure>", self.arrange_steps)
        self.update_steps()

        bar = self.toolbar(body)
        self.new_button = self.button(bar, "新建批次", "New batch", self.create, "always")
        self.button(bar, "打开批次", "Open batch", self.choose_open, "always")
        self.import_button = self.button(bar, "导入剧本", "Import scripts", self.import_scripts, "batch")
        self.button(bar, "更新本集原稿", "Revise script", self.revise)
        self.button(bar, "刷新", "Refresh", self.reload, "batch")
        self.wrap_toolbar(bar)

        line = self.toolbar(body)
        ttk.Label(line, text=self.t("当前集", "Episode"), style="A.TLabel").pack(side="left", padx=(0, 5))
        self.episode_box = ttk.Combobox(line, name="episode", state="readonly", width=25)
        self.episode_box.pack(side="left", padx=(0, 10))
        self.episode_box.bind("<<ComboboxSelected>>", self.switch_episode)
        ttk.Label(line, text=self.t("目标组", "Group"), style="A.TLabel").pack(side="left", padx=(0, 4))
        self.group_box = ttk.Combobox(line, state="readonly", width=7)
        self.group_box.pack(side="left", padx=(0, 10))
        self.group_box.bind("<<ComboboxSelected>>", self.select_group)
        ttk.Label(line, textvariable=self.summary, style="A.Muted.TLabel").pack(side="left")

        content = ttk.Frame(body, style="A.TFrame")
        content.pack(fill="both", expand=True, pady=(5, 6))
        self.import_page = ttk.Frame(content, padding=16, style="A.Card.TFrame")
        ttk.Label(self.import_page, text=self.t("导入一集或多集定稿", "Add one or more final scripts"),
                  style="A.TLabel", font=("TkDefaultFont", 14, "bold"), background=SURFACE).pack(anchor="w")
        details = tk.StringVar(self.window)
        self.import_hint = details
        self.import_hint.set(self.t("先新建批次或打开已有的 .cfbatch。", "Create a batch or open an existing .cfbatch first."))
        tooltip = ttk.Label(self.import_page, textvariable=details, style="A.Muted.TLabel",
                            background=SURFACE, wraplength=680, justify="left")
        tooltip.pack(anchor="w", fill="x", pady=(8, 16))
        self.import_page.bind("<Configure>", lambda event: tooltip.configure(wraplength=max(150, event.width - 32)))
        self.button(self.import_page, "继续到整集规划", "Continue to episode plan", lambda: self.select_stage("plan"),
                    primary=True)

        self.tabs = ttk.Notebook(content, style="A.Hidden.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        plan, assets, queue, delivery = [ttk.Frame(self.tabs, padding=9, style="A.TFrame") for _ in range(4)]
        self.pages = dict(zip((entry[0] for entry in STAGES[1:]), (plan, assets, queue, delivery)))
        for page, entry in zip(self.pages.values(), STAGES[1:]):
            self.tabs.add(page, text=self.t(entry[1], entry[2]))
        self.tabs.bind("<<NotebookTabChanged>>", self.tab_changed)
        self.build_plan(plan)
        self.build_assets(assets)
        self.build_queue(queue)
        self.build_delivery(delivery)
        footer = self.toolbar(body)
        footer.pack_configure(before=content, side="bottom")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=70)
        self.progress.pack(side="right")
        status = ttk.Label(footer, textvariable=self.status, style="A.Muted.TLabel", wraplength=680, justify="left")
        status.pack(side="left", fill="x", expand=True, padx=(0, 8))
        footer.bind("<Configure>", lambda event: status.configure(wraplength=max(180, event.width - 85)))
        self.step_row.after_idle(self.arrange_steps)

    def arrange_steps(self, _event=None):
        width = self.step_row.winfo_width()
        widths = [step.winfo_reqwidth() + 8 for step in self.steps.values()]
        columns = 5 if width < 20 or width >= sum(widths) else 3 if width >= 3 * max(widths) else 2
        if columns == self.step_columns:
            return
        self.step_columns = columns
        for column in range(5):
            self.step_row.columnconfigure(column, weight=1 if column < columns else 0,
                                          uniform="steps" if column < columns and columns != 5 else "")
        for index, step in enumerate(self.steps.values()):
            step.grid(row=index // columns, column=index % columns, sticky="nsew", padx=(0, 4), pady=(0, 3))

    def update_steps(self):
        view = self.view
        delivery = view.get("delivery_groups", ())
        jobs = [job for job in view.get("jobs", ()) if job["episode"] == self.episode_id]
        complete = {"import": bool(self.episode_id), "plan": view.get("approved", False),
                    "assets": bool(view.get("assets")) and not view.get("gaps"),
                    "queue": bool(jobs) and all(job["status"] == "approved" for job in jobs),
                    "delivery": bool(delivery) and all(group["ready"] for group in delivery)}
        for i, (key, zh, en) in enumerate(STAGES, start=1):
            mark = "✓" if complete[key] else f"{i:02}"
            style = "A.Current.Step.TButton" if self.stage == key else (
                "A.Done.Step.TButton" if complete[key] else "A.Step.TButton")
            self.steps[key].configure(text=f"{mark}  {self.t(zh, STEP_LABELS.get(key, en))}", style=style)
        if hasattr(self, "new_button"):
            self.new_button.configure(style="Workbench.TButton" if self.workspace else "Primary.Workbench.TButton")
            self.import_button.configure(style="Primary.Workbench.TButton" if self.workspace and self.stage == "import" and not self.episode_id
                                         else "Workbench.TButton")

    def select_stage(self, stage):
        if stage not in ("import", *self.pages):
            raise ValueError(f"Unknown batch stage: {stage}")
        if stage == "import":
            self.tabs.pack_forget()
            self.import_page.pack(fill="both", expand=True)
        else:
            self.import_page.pack_forget()
            self.tabs.pack(fill="both", expand=True)
            self.tabs.select(self.pages[stage])
        self.stage = stage
        self.update_steps()
        if stage == "delivery":
            self.show_delivery_selection()
        self.notify_workbench()

    def tab_changed(self, _event):
        if self.stage == "import" or not self.tabs.winfo_manager():
            return
        match = next((key for key, page in self.pages.items() if str(page) == self.tabs.select()), None)
        if match and self.stage != match:
            self.select_stage(match)

    def notify_workbench(self):
        if self.on_workbench_update is not None:
            self.on_workbench_update(self)

    def recommended_stage(self):
        if not self.episode_id:
            return "import"
        if not self.view.get("approved") or self.view.get("issues"):
            return "plan"
        if self.view.get("required_gaps"):
            return "assets"
        jobs = [job for job in self.view.get("jobs", ()) if job["episode"] == self.episode_id]
        if any(job["status"] != "approved" for job in jobs):
            return "queue"
        return "delivery"

    def build_plan(self, page):
        bar = self.toolbar(page)
        ttk.Label(bar, text=self.t("查找原文或镜号", "Find passage or shot")).pack(side="left", padx=(0, 5))
        ttk.Entry(bar, name="search", textvariable=self.search, width=17).pack(side="left", padx=(0, 8))
        self.button(bar, "查看整集原文", "Read script", self.show_script)
        self.button(bar, "确认本集规划", "Approve episode plan", self.approve_plan, primary=True)
        self.wrap_toolbar(bar)
        self.trace = self.table(page, "trace", (("group", "组／镜", "Group / shot", 90), ("line", "原稿行", "Line", 65),
            ("speaker", "说话人", "Speaker", 105), ("text", "原文／对白", "Source text / dialogue", 360)), 3)
        self.trace.bind("<<TreeviewSelect>>", lambda _e: self.trace_detail())
        self.trace.bind("<Double-1>", lambda _e: self.guarded(self.edit_group))
        self.search.trace_add("write", lambda *_: self.fill_trace())
        self.detail = scrolledtext.ScrolledText(page, height=2, wrap="word", state="disabled")
        self.detail.pack(fill="x", pady=4)
        bars = self.toolbar(page)
        self.button(bars, "细拆动作段", "Split action passage", self.split_action)
        self.button(bars, "从此镜另起一组", "Start group here", lambda: self.adjust_groups(True))
        self.button(bars, "与前一组合并", "Merge with previous", lambda: self.adjust_groups(False))
        self.button(bars, "打开单组制片", "Open group editor", self.edit_group)
        bars.pack_configure(before=self.trace.master, side="bottom")
        self.detail.pack_configure(before=self.trace.master, side="bottom")
        self.wrap_toolbar(bars)

    def build_assets(self, page):
        library_bar = self.toolbar(page)
        self.button(library_bar, "打开素材库", "Open media library", self.open_media_library, "batch", primary=True)
        ttk.Label(page, textvariable=self.asset_status, wraplength=790).pack(anchor="w", pady=(0, 5))
        self.assets = self.table(page, "assets", (("identity", "身份／资产", "Identity / asset", 180),
            ("state_name", "状态／造型", "State / look", 180), ("version", "版本", "Version", 90),
            ("file", "批准文件", "Approved file", 200)), 2)
        self.assets.bind("<Double-1>", self.open_clicked_asset)
        self.assets.bind("<Return>", lambda _event: self.guarded(lambda: self.open_media_library(open_selected=True)))
        bar = self.toolbar(page)
        self.button(bar, "批准本地资产", "Approve local asset", self.approve_asset, "batch")
        self.button(bar, "复用到所选组", "Reuse in selected group", self.reuse_asset)
        self.button(bar, "安排资产生图", "Queue asset image", self.queue_asset)
        self.wrap_toolbar(bar)
        self.requirements = self.table(page, "requirements", (("identity", "本组依赖", "Required asset", 200), ("state_name", "指定状态", "Required state", 200),
            ("version", "版本", "Version", 90), ("delivery", "用途", "Use", 150)), 1)
        actions = self.toolbar(page)
        self.button(actions, "指定依赖", "Require asset", self.require_asset)
        self.button(actions, "移除依赖", "Remove requirement", self.remove_requirement)
        self.button(actions, "绑定已批准依赖", "Bind approved matches", self.resolve_requirements)
        actions.pack_configure(before=self.assets.master, side="bottom")
        self.assets.master.pack_configure(expand=True)
        self.wrap_toolbar(actions)

    def build_queue(self, page):
        model_bar = self.toolbar(page)
        self.model_boxes = []
        for session, zh, en in ((self.text_session, "文本模型", "Text model"), (self.image_session, "生图模型", "Image model")):
            ttk.Label(model_bar, text=self.t(zh, en)).pack(side="left", padx=(0, 4))
            labels = [self.t("未配置", "Not configured")] if not session else [f"{s.provider} · {s.model}" for s in session.values()]
            box = ttk.Combobox(model_bar, values=labels, state="readonly", width=24)
            box.current(len(labels) - 1)
            box.pack(side="left", padx=(0, 10))
            self.model_boxes.append((box, list(session.values())))
        self.wrap_toolbar(model_bar)
        bar = self.toolbar(page)
        self.kinds = {}
        for key, (zh, en) in TASK_KINDS.items():
            var = tk.BooleanVar(self.window, True)
            self.kinds[key] = var
            ttk.Checkbutton(bar, text=self.t(zh, en), variable=var).pack(side="left", padx=(0, 6))
        self.button(bar, "本集加入队列", "Queue episode", lambda: self.enqueue(False))
        self.button(bar, "多集加入队列", "Queue all episodes", lambda: self.enqueue(True))
        self.wrap_toolbar(bar)
        bar = self.toolbar(page)
        ttk.Label(bar, text=self.t("本批 API 请求上限", "Batch request limit")).pack(side="left")
        self.limit_box = ttk.Entry(bar, width=5, textvariable=self.budget)
        self.limit_box.pack(side="left", padx=(5, 8))
        self.button(bar, "运行／继续", "Run / resume", self.run_queue, primary=True)
        self.pause = ttk.Button(bar, text=self.t("本次请求后暂停", "Pause after request"), width=0, command=self.pause_queue)
        self.pause.pack(side="left", padx=(0, 5))
        self.wrap_toolbar(bar)
        ttk.Label(page, textvariable=self.queue_status, wraplength=740).pack(anchor="w", pady=(0, 4))
        self.jobs = self.table(page, "jobs", (("episode", "集", "Episode", 60), ("group", "组／镜", "Group / shot", 115),
            ("kind", "任务", "Task", 80), ("status", "状态", "Status", 100), ("message", "详情", "Details", 330)), 2)
        bar = self.toolbar(page)
        self.button(bar, "查看／采纳候选", "Review candidate", self.review_job)
        self.button(bar, "整组审核文字", "Review group text", self.review_group_text)
        self.button(bar, "重试选中任务", "Retry selected", self.retry_job)
        bar.pack_configure(before=self.jobs.master, side="bottom")
        self.wrap_toolbar(bar)

    def build_delivery(self, page):
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)
        split = ttk.Panedwindow(page, orient="horizontal")
        split.grid(row=0, column=0, sticky="nsew")

        listing = ttk.Frame(split, padding=(0, 0, 8, 0), style="A.TFrame")
        split.add(listing, weight=5)
        self.delivery_caption = tk.StringVar(self.window, self.t("本集故事板组", "Episode storyboard groups"))
        ttk.Label(listing, textvariable=self.delivery_caption, style="A.TLabel",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.delivery_groups = self.table(listing, "delivery_groups", (
            ("group", "组号", "Group", 62), ("scene", "场景", "Scene", 108),
            ("review", "复核状态", "Review status", 145)), 3)
        self.delivery_groups.tag_configure("ready", foreground=GREEN)
        self.delivery_groups.tag_configure("handoff", foreground=AMBER)
        self.delivery_groups.tag_configure("visual", foreground=AMBER)
        self.delivery_groups.bind("<<TreeviewSelect>>", lambda _event: self.show_delivery_selection())
        self.delivery_groups.bind("<Double-1>", lambda _event: self.guarded(self.open_delivery_group))

        information = ttk.Frame(split, padding=10, style="A.Card.TFrame")
        split.add(information, weight=4)
        self.review_title = tk.StringVar(self.window, self.t("组间衔接", "Group handoff"))
        title = ttk.Label(information, textvariable=self.review_title, style="A.TLabel", background=SURFACE,
                          font=("TkDefaultFont", 12, "bold"), wraplength=380, justify="left")
        title.pack(fill="x", anchor="w", pady=(0, 7))
        information.bind("<Configure>", lambda event: title.configure(wraplength=max(100, event.width - 21)))
        self.delivery_detail = scrolledtext.ScrolledText(information, name="delivery_detail", width=28, height=2,
                                                         wrap="word", state="disabled", bd=0,
                                                         padx=9, pady=5, bg=SURFACE, fg=INK,
                                                         highlightthickness=1, highlightbackground=LINE,
                                                         font="TkDefaultFont")
        self.delivery_detail.pack(fill="both", expand=True, pady=(0, 8))
        self.review_actions = ttk.Frame(information, style="A.Card.TFrame")
        self.review_actions.pack(before=self.delivery_detail.frame, side="bottom", fill="x")
        self.review_group_button = self.button(self.review_actions, "打开本组复核", "Open group for review",
                                               self.open_delivery_group, "review_group", primary=True)
        self.review_boundary_button = self.button(self.review_actions, "打开组间衔接", "Open group handoff",
                                                  lambda: self.open_delivery_group(previous=True), "review_previous")
        self.review_group_button.pack_configure(side="top", anchor="w", padx=0)
        self.review_boundary_button.pack_configure(side="top", anchor="w", padx=0)

        self.delivery_status = tk.StringVar(self.window)
        label = ttk.Label(page, textvariable=self.delivery_status, style="A.Muted.TLabel",
                          wraplength=730, justify="left")
        label.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        page.bind("<Configure>", lambda event: label.configure(wraplength=max(200, event.width - 24)), add="+")

        footer = ttk.Frame(page, style="A.TFrame")
        footer.grid(row=2, column=0, sticky="ew", pady=(3, 0))
        coverage = ttk.Frame(footer, style="A.TFrame")
        release = ttk.Frame(footer, style="A.TFrame")
        coverage.pack(anchor="w")
        release.pack(anchor="w")
        self.button(coverage, "复查本集覆盖", "Recheck coverage", self.reload)
        self.button(coverage, "查看原稿覆盖", "Script coverage", self.show_coverage)
        self.button(release, "导出整集 ZIP", "Export episode ZIP", lambda: self.publish(False), "release_episode",
                    primary=True)
        self.button(release, "导出多集总包", "Export series ZIP", lambda: self.publish(True))

    def show_coverage(self):
        self.show_text(self.t("本集原稿覆盖", "Episode script coverage"), self.coverage_text())

    def coverage_text(self):
        plan = self.view.get("plan", {})
        issues = list(dict.fromkeys([*plan.get("issues", []), *self.view.get("issues", [])]))
        if issues:
            return "\n".join(issues)
        if plan:
            return self.t("当前未发现原文覆盖缺口。仍需逐格核对画面和跨组衔接。",
                          "No script coverage gaps found. Review actual panels and handoffs separately.")
        return self.t("请先导入定稿。", "Import the final script first.")

    def delivery_record(self):
        selection = self.delivery_groups.selection()
        return self.review_rows.get(selection[0], {}) if selection else {}

    def open_delivery_group(self, previous=False):
        record = self.delivery_record()
        group = record.get("previous" if previous else "group")
        if group and group in self.view.get("paths", {}):
            if previous:
                adjacent = self.view["paths"].get(record["group"])
                if adjacent and not record["handoff"]:
                    self.edit_group(group, destination="handoff", adjacent_path=adjacent)
            else:
                self.edit_group(group, destination="review")

    def fill_delivery(self, same_episode):
        past_selection = self.delivery_groups.selection() if same_episode else ()
        self.delivery_groups.delete(*self.delivery_groups.get_children())
        records = self.view.get("delivery_groups", ())
        self.review_rows = {record["group"]: record for record in records}
        ready = sum(row["ready"] for row in records)
        if records:
            self.delivery_caption.set(self.t(f"本集故事板组 · {ready}/{len(records)} 组已复核",
                                              f"Episode storyboard groups · {ready}/{len(records)} reviewed"))
        else:
            self.delivery_caption.set(self.t("本集故事板组", "Episode storyboard groups"))
        for record in records:
            group = record["group"]
            self.delivery_groups.insert("", "end", iid=group, values=(group, record["scene"] or "—",
                                                                      self.t(*GROUP_STATES[record["state"]])),
                                        tags=(record["state"],))
        target = (past_selection[0] if past_selection and past_selection[0] in self.review_rows
                  else next((row["group"] for row in records if not row["ready"]), next(iter(self.review_rows), "")))
        if target:
            self.delivery_groups.selection_set(target)
            self.delivery_groups.focus(target)
            self.delivery_groups.see(target)
        if not records:
            self.delivery_status.set(self.t("请先导入剧本并完成整集规划。", "Import the script and complete the episode plan first."))
        elif not self.view.get("approved"):
            self.delivery_status.set(self.t("请先确认本集规划。", "Approve the episode plan first."))
        elif self.view.get("issues") or self.view.get("plan", {}).get("issues"):
            self.delivery_status.set(self.t("原稿覆盖有待处理项，点「查看原稿覆盖」定位。", "Script coverage needs attention. Open the coverage report."))
        elif self.view.get("required_gaps"):
            self.delivery_status.set(self.t("请先到「公共资产」处理未绑定的指定资产。", "Bind the required assets in Shared assets first."))
        elif ready < len(records):
            pending = len(records) - ready
            self.delivery_status.set(self.t(f"还有 {pending} 组待复核，完成后才能导出本集。",
                                            f"{pending} groups need review before episode export."))
        elif self.view.get("pending"):
            self.delivery_status.set(self.t("最后一组还有待制作镜头，请回到单组制片处理。",
                                            "The final group still has deferred shots. Review it in the group editor."))
        else:
            self.delivery_status.set(self.t("已记录分组复核。导出时会再次核对项目和全部素材。",
                                            "Group reviews are recorded. Export rechecks the projects and all assets."))
        self.show_delivery_selection()

    def show_delivery_selection(self):
        record = self.delivery_record()
        if not record:
            self.review_title.set(self.t("组间衔接", "Group handoff"))
            self.write_text(self.delivery_detail, self.t("选择一个故事板组查看复核记录。", "Select a group to see its review status."))
        else:
            previous = record["previous"]
            group = record["group"]
            self.review_title.set(f"{previous} → {group}" if previous else self.t(f"{group} · 本组复核", f"{group} · Group review"))
            label = self.t(*GROUP_STATES[record["state"]])
            details = [self.t("本组画面与适用的组间交接已记录。", "Current panel and applicable handoff reviews are recorded.")
                       if record["ready"] else label]
            if previous:
                details.extend((self.t(f"{previous} · 尾镜", f"{previous} · Last shot"),
                                record["last_shot"] or self.t("尚无可读镜头。", "No readable shot."),
                                self.t(f"{group} · 首镜", f"{group} · First shot"),
                                record["first_shot"] or self.t("尚无可读镜头。", "No readable shot.")))
                if record["handoff"]:
                    details.extend((self.t("交接记录", "Handoff record"), record["handoff"]))
                elif record["state"] != "missing":
                    details.append(self.t("在前组「排版与交接」里打开前末后首对照，核对当前版本后再确认。",
                                          "Open the previous group's Layout & handoff and review the actual end/start panels."))
            elif record["first_shot"]:
                details.append(record["first_shot"])
            if record["state"] == "visual":
                details.append(self.t("打开本组，逐格确认实际画面。", "Open this group and review the actual panels."))
            self.write_text(self.delivery_detail, "\n\n".join(details))
        if self.can_open_handoff(record):
            self.review_boundary_button.pack(side="top", anchor="w", pady=3)
        else:
            self.review_boundary_button.pack_forget()
        self.set_controls()

    def can_open_handoff(self, record):
        paths = self.view.get("paths", {})
        return record.get("previous") in paths and record.get("group") in paths and not record["handoff"]

    def set_controls(self):
        record = self.delivery_record()
        policy = {
            "always": True, "batch": bool(self.workspace), "episode": bool(self.episode_id),
            "review_group": record.get("group") in self.view.get("paths", {}),
            "review_previous": self.can_open_handoff(record),
            "release_episode": self.episode_can_publish(),
        }
        for button, needs in self.controls:
            button.state(["!disabled"] if policy[needs] and not self.busy else ["disabled"])
        self.episode_box.configure(state="readonly" if self.episode_ids and not self.busy else "disabled")
        self.group_box.configure(state="readonly" if self.episode_id and not self.busy else "disabled")
        self.limit_box.state(["disabled"] if self.busy else ["!disabled"])
        for box, _settings in self.model_boxes:
            box.configure(state="disabled" if self.busy else "readonly")
        self.pause.state(["!disabled"] if self.busy and self.stop is not None else ["disabled"])

    def episode_can_publish(self):
        view = self.view
        records = view.get("delivery_groups", ())
        return (bool(records) and all(group["ready"] for group in records) and view.get("approved")
                and not (view.get("issues") or view.get("plan", {}).get("issues")
                         or view.get("required_gaps") or view.get("pending")))

    def task(self, worker, done, label):
        if self.busy:
            return
        self.busy = True
        self.set_controls()
        self.progress.start(14)
        self.status.set(label)
        results = Queue()

        def run():
            try:
                results.put((True, worker()))
            except Exception as exc:
                results.put((False, exc))

        def poll():
            try:
                success, result = results.get_nowait()
            except Empty:
                self.window.after(90, poll)
                return
            self.busy = False
            self.stop = None
            self.set_controls()
            self.progress.stop()
            if success:
                self.guarded(lambda: done(result))
            else:
                self.status.set(self.t("操作未完成。", "Action did not finish."))
                self.error(result)

        Thread(target=run, daemon=True).start()
        self.window.after(60, poll)

    @staticmethod
    def shot_note(project, final):
        if not project or not project.shots:
            return ""
        number = len(project.shots) if final else 1
        shot = project.shots[number - 1]
        state = project.notes.get("本组退出状态" if final else "本组进入状态", "").strip()
        return "\n".join(part for part in (f"{project.group}-{number:02} · {shot.scene or shot.anchor}",
                                               shot.fields.get("动作起止", "").strip(), state) if part)

    @classmethod
    def review_snapshot(cls, plan, projects):
        lookup = {project.group: project for project in projects}
        results = []
        previous = ""
        for row in plan["groups"]:
            group = row["group"]
            current = lookup.get(group)
            older = lookup.get(previous)
            confirmed = not previous or bool(older and current and reviewed_boundary(older, current))
            state = ("missing" if current is None else "visual" if current.impacts()
                     else "handoff" if not confirmed else "ready")
            results.append({"group": group, "previous": previous, "state": state, "ready": state == "ready",
                            "scene": " / ".join(dict.fromkeys(shot.scene for shot in current.shots if shot.scene))
                            if current else "",
                            "last_shot": cls.shot_note(older, True),
                            "first_shot": cls.shot_note(current, False),
                            "handoff": older.handoffs[group]["review"] if previous and confirmed else ""})
            previous = group
        return results

    @staticmethod
    def snapshot(workspace, episode_id):
        episodes = list(workspace.episodes)
        ids = [ep.id for ep in episodes]
        episode_id = episode_id if episode_id in ids else next(iter(ids), "")
        queue = BatchQueue(workspace)
        view = {"workspace": workspace, "episodes": episodes, "episode": episode_id, "plan": {}, "trace": [],
                "approved": False, "assets": workspace.asset_inventory(), "gaps": [], "required_gaps": [], "issues": [],
                "delivery_groups": [], "pending": False, "jobs": queue.jobs(), "spent": queue.spent(), "limit": queue.request_limit(), "paths": {}}
        if episode_id:
            plan = workspace.plan_for(episode_id)
            paths = workspace.group_paths(episode_id)
            projects, unreadable = [], []
            for path in paths:
                try:
                    project = ProductionProject.open(path)
                    if (project.name, project.episode, project.rules, project.group) != (
                            plan["name"], episode_id, workspace.rules, path.stem):
                        raise ValueError("项目身份、制作规则或组号不匹配 / Project identity, rules or group do not match.")
                    projects.append(project)
                    view["paths"][path.stem] = path
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    unreadable.append(f"{path.name} · {exc}")
            view.update(plan=plan, trace=trace_rows(plan, projects), approved=workspace.plan_approved(episode_id),
                        gaps=workspace.asset_gaps(episode_id) if not unreadable else [],
                        issues=unreadable + coverage_issues(plan, projects))
            view["requirements"] = {g['group']: workspace.required_assets(episode_id, g['group']) for g in plan['groups']}
            required_gaps = []
            for group, requirements in view["requirements"].items():
                if requirements and group in view["paths"]:
                    try:
                        required_gaps.extend(f"{group} · {gap}" for gap in workspace.required_asset_gaps(episode_id, group))
                    except (OSError, ValueError, TypeError, KeyError) as error:
                        required_gaps.append(f"{group} · {error}")
            view["required_gaps"] = required_gaps
            view["delivery_groups"] = BatchDialog.review_snapshot(plan, projects)
            view["pending"] = bool(projects and projects[-1].pending_shots)
        return view

    def update(self, action=None, *, episode=None, label=None, result_message=None):
        workspace = self.workspace
        eid = self.episode_id if episode is None else episode

        def run():
            result = action() if action else None
            return self.snapshot(workspace, eid), result

        def complete(pair):
            self.render(pair[0])
            if result_message:
                self.status.set(result_message(pair[1]))

        self.task(run, complete, label or self.t("正在读取任务与分组…", "Loading tasks and groups…"))

    def reload(self):
        self.update()

    def batch_filetypes(self):
        return ((self.t("批量制作项目", "Batch production project"), "*.cfbatch"),)

    def create(self):
        path = filedialog.asksaveasfilename(
            parent=self.window, title=self.t("保存新批次", "Save new batch"),
            filetypes=self.batch_filetypes(), defaultextension=".cfbatch",
        )
        if path:
            path = Path(path)
            self.task(lambda: self.snapshot(BatchWorkspace.create(path, path.stem, self.rules), ""), self.render,
                      self.t("正在新建批次…", "Creating batch…"))

    def choose_open(self):
        path = filedialog.askopenfilename(parent=self.window, filetypes=self.batch_filetypes())
        if path:
            self.open_path(path)

    def open_path(self, path, *, episode_id=None):
        self.task(lambda: self.snapshot(BatchWorkspace.open(Path(path)), episode_id or ""), self.render,
                  self.t("正在打开批次…", "Opening batch…"))

    def import_scripts(self):
        paths = filedialog.askopenfilenames(parent=self.window, title=self.t("按集导入定稿，每个文件一集", "Import one script file per episode"), filetypes=SCRIPT_FILES)
        if paths:
            workspace = self.workspace
            self.update(lambda: workspace.add_scripts([Path(p) for p in paths]), label=self.t("正在拆解剧本并建立单组项目…", "Planning scripts and creating group projects…"))

    def switch_episode(self, _event):
        index = self.episode_box.current()
        if not self.busy and index >= 0:
            self.update(episode=self.episode_ids[index])

    def render(self, view):
        same_batch = self.workspace is not None and self.workspace.path == view["workspace"].path
        same_episode = same_batch and self.episode_id == view["episode"]
        if not same_batch:
            self.budget.set(str(view["limit"]))
        self.view = view
        self.workspace = view["workspace"]
        self.episode_id = view["episode"]
        self.episode_ids = [ep.id for ep in view["episodes"]]
        self.episode_box.configure(values=[f"{ep.id} · {ep.title}" for ep in view["episodes"]])
        if self.episode_id:
            self.episode_box.current(self.episode_ids.index(self.episode_id))
        else:
            self.episode_box.set("")
        rule = self.t("中文影片制作", "Chinese film production") if self.workspace.rules == CHINESE else self.t("英文影片制作", "English film production")
        self.heading.set(f"{self.workspace.title}  ·  {rule}  v{rule_revision(self.workspace.rules)}")
        plan = view["plan"]
        self.group_box.configure(values=[g['group'] for g in plan.get("groups", [])])
        approved = self.t("已确认", "Approved") if view["approved"] else self.t("草案", "Draft")
        self.summary.set(self.t(f"{len(plan.get('groups', []))} 组 · {approved}", f"{len(plan.get('groups', []))} groups · {approved}") if plan else "")
        self.fill_trace()
        self.assets.delete(*self.assets.get_children())
        for n, asset in enumerate(view["assets"]):
            self.assets.insert("", "end", iid=str(n), values=(asset.identity, asset.state, asset.version, asset.filename))
        gaps = view["required_gaps"] or view["gaps"]
        self.asset_status.set(self.t("待绑定的资产", "Assets to bind") + (" · " + ", ".join(gaps[:12]) if gaps else " · —"))
        self.fill_jobs(view["jobs"], view["spent"])
        self.import_hint.set(self.t("用上方「导入剧本」选择 TXT 或 Markdown。每个文件对应一集。",
                                    "Choose Import scripts above. Select one TXT or Markdown file per episode."))
        self.fill_delivery(same_episode)
        self.status.set(str(self.workspace.path))
        self.update_steps()
        self.set_controls()
        self.notify_workbench()

    @staticmethod
    def write_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def fill_trace(self):
        query = self.search.get().strip().casefold()
        old = self.trace.selection()
        self.trace.delete(*self.trace.get_children())
        self.display_rows = {}
        for n, row in enumerate(self.view.get("trace", [])):
            slot = f"{row['group']}-{row['slot']:02}" if isinstance(row['slot'], int) else f"{row['group']}-{row['slot']}"
            if query and query not in " ".join(str(row.get(k, "")) for k in ("text", "line_no", "speaker", "shot_id", "passage_id")).casefold() and query not in slot.casefold():
                continue
            key = str(n)
            self.display_rows[key] = row
            self.trace.insert("", "end", iid=key, values=(slot, row['line_no'], row.get('speaker', ''), row['text']))
        if self.display_rows:
            self.trace.selection_set(old[0] if old and old[0] in self.display_rows else next(iter(self.display_rows)))
        self.trace_detail()

    def selected_row(self):
        selected = self.trace.selection()
        if not selected:
            raise ValueError(self.t("请在整集规划里选择一格。", "Select a shot in Episode plan."))
        return self.display_rows[selected[0]]

    def trace_detail(self):
        if not self.trace.selection():
            self.write_text(self.detail, "")
            self.group_box.set("")
            self.show_requirements()
            return
        row = self.selected_row()
        self.group_box.set(row['group'])
        original = row.get('source_line', row['text'])
        self.show_requirements()
        group = next((item for item in self.view['plan']['groups'] if item['group'] == row['group']), {})
        annotation = group.get('planning_note', '')
        self.write_text(self.detail, f"{row['passage_id']} · {row['shot_id']}\n{original}" + (f"\n{annotation}" if annotation else ""))

    def select_group(self, _event):
        group = self.group_box.get()
        self.search.set("")
        key = next((index for index, row in self.display_rows.items() if row['group'] == group), None)
        if key is not None:
            self.trace.selection_set(key)
            self.trace.see(key)
            self.trace_detail()

    def revise(self):
        from .batch_revision import revise_episode
        path = filedialog.askopenfilename(parent=self.window, title=self.t("选择本集修订稿", "Select the revised episode script"), filetypes=SCRIPT_FILES)
        if not path:
            return
        if not messagebox.askyesno(self.window.title(), self.t("更新本集原稿并重新规划？受影响的旧组将保留在批次数据中，更新后的规划需确认。",
                "Revise this episode? Affected prior groups are kept in the batch data. Review the updated plan before continuing."), parent=self.window):
            return
        self.update(lambda: revise_episode(self.workspace, self.episode_id, Path(path)),
                    result_message=lambda result: self.t("已更新原稿。复用组", "Revised script. Reused groups") + " · " + ", ".join(result["reused"]) +
                    "   " + self.t("变更组", "Changed groups") + " · " + ", ".join(result["changed"]))

    def show_text(self, title, value, accept=None):
        panel = tk.Toplevel(self.window)
        panel.title(title)
        panel.transient(self.window)
        panel.geometry("700x485")
        box = scrolledtext.ScrolledText(panel, wrap="word", padx=8, pady=8)
        box.pack(fill="both", expand=True)
        self.write_text(box, value)
        bar = self.toolbar(panel)
        if accept:
            def use():
                panel.destroy()
                self.guarded(accept)
            ttk.Button(bar, text=self.t("采纳候选", "Adopt candidate"), command=use).pack(side="left", padx=8)
        ttk.Button(bar, text=self.t("关闭", "Close"), command=panel.destroy).pack(side="right", padx=8)
        panel.grab_set()
        self.window.wait_window(panel)
        self.window.grab_set()

    def show_script(self):
        plan = self.view['plan']
        self.show_text(self.t("批准剧本原文", "Approved source script"), plan['source_text'])

    def split_action(self):
        row = self.selected_row()
        plan = self.view['plan']
        passage = next(p for p in plan['passages'] if p['id'] == row['passage_id'])
        if passage['kind'] != "action":
            raise ValueError(self.t("请选择动作段。对白按当前制作规则的句界处理。", "Select an action passage. Dialogue follows its production rule's sentence boundaries."))
        original = passage['text']
        marks = [0, *[n - passage['start'] for n in plan.get('shot_splits', {}).get(passage['id'], [])], len(original)]
        panel = tk.Toplevel(self.window)
        panel.title(self.t("细拆动作段", "Split action passage"))
        panel.transient(self.window)
        self.note(panel, "在动作发生可见变化的位置按回车，每行对应一镜。保留全部原文。合回一行可撤销段内拆镜。", "Insert a line break at each new visible beat. Keep the original wording. Join the lines to remove cuts.")
        editor = scrolledtext.ScrolledText(panel, width=60, height=9, wrap="word", undo=True)
        editor.pack(fill="both", expand=True, padx=8)
        editor.insert("1.0", "\n".join(original[a:b] for a, b in zip(marks, marks[1:])))
        result = []

        def accept():
            parts = editor.get("1.0", "end-1c").split("\n")
            if "".join(parts) != original or any(not part.strip() for part in parts):
                messagebox.showerror(panel.title(), self.t("只增删换行，保留所有原文字词，不能有空镜。", "Only change line breaks. Preserve every character and avoid empty shots."), parent=panel)
                return
            pos = passage['start']
            offsets = []
            for part in parts[:-1]:
                pos += len(part)
                offsets.append(pos)
            result.append(offsets)
            panel.destroy()

        bar = self.toolbar(panel)
        ttk.Button(bar, text=self.t("保存拆镜", "Save cuts"), command=accept).pack(side="right", padx=6)
        ttk.Button(bar, text=self.t("取消", "Cancel"), command=panel.destroy).pack(side="right")
        editor.focus_set()
        panel.grab_set()
        self.window.wait_window(panel)
        self.window.grab_set()
        if result:
            self.update(lambda: self.workspace.split_passage(self.episode_id, passage['id'], result[0]))

    def approve_plan(self):
        self.update(lambda: self.workspace.approve_plan(self.episode_id))

    def adjust_groups(self, split):
        row = self.selected_row()
        groups = [list(group['shot_ids']) for group in self.view['plan']['groups']]
        index = next(i for i, group in enumerate(groups) if row['shot_id'] in group)
        if split:
            offset = groups[index].index(row['shot_id'])
            if not offset:
                raise ValueError(self.t("此镜已是组首。", "This shot already starts its group."))
            groups[index:index + 1] = [groups[index][:offset], groups[index][offset:]]
        else:
            if index == 0:
                raise ValueError(self.t("第一组没有前一组。", "There is no previous group."))
            groups[index-1:index+1] = [groups[index-1]+groups[index]]
        self.update(lambda: self.workspace.regroup(self.episode_id, groups))

    def edit_group(self, group_id=None, episode_id=None, image_job_id=None, *, destination=None, adjacent_path=None):
        episode_id = episode_id or self.episode_id
        group_id = group_id or self.selected_row()['group']
        path = self.view['paths'].get(group_id) if episode_id == self.episode_id else self.workspace.group_path(episode_id, group_id)
        if path is None:
            raise ValueError(self.t("此源段尚未绑定有效镜头。", "This passage has no linked group."))
        options = {"destination": destination} if destination else {}
        if adjacent_path is not None:
            options["adjacent_path"] = adjacent_path
        dialog = self.open_group(path, self.workspace.rules, self.window, **options)
        if dialog is not None:
            if image_job_id:
                self.open_image_candidate(dialog, image_job_id)
            self.window.wait_window(dialog.window)
            self.window.grab_set()
            self.reload()

    def open_image_candidate(self, dialog, image_job_id):
        from .image_production_dialog import ImageProductionDialog

        def open_when_loaded():
            if not dialog.window.winfo_exists():
                return
            if dialog.project is None:
                if str(dialog.window.cget("cursor")) == "watch":
                    dialog.window.after(80, open_when_loaded)
                return
            job = next((j for j in dialog.project.image_jobs if j['id'] == image_job_id), None)
            if job is None:
                dialog.status.set(self.t("此候选已从单组项目移除。", "This candidate is no longer in the group project."))
                return
            preview = ImageProductionDialog(dialog, self.image_session)
            preview.refresh_jobs(job)
            preview.tabs.select(1)
            dialog.wait(preview.window)

        dialog.window.after(120, lambda: dialog.guarded(open_when_loaded))

    def asset_form(self, title, fields, preview=None):
        panel = tk.Toplevel(self.window)
        panel.title(title)
        panel.transient(self.window)
        form = ttk.Frame(panel, padding=12)
        form.pack(fill="both", expand=True)
        thumbnail = None
        if preview is not None:
            from PIL import ImageTk
            thumbnail = ImageTk.PhotoImage(preview, master=panel)
            ttk.Label(form, image=thumbnail).pack(pady=(0, 8))
        entries = {}
        for key, zh, en, initial in fields:
            row = self.toolbar(form)
            ttk.Label(row, width=18, text=self.t(zh, en)).pack(side="left")
            if isinstance(initial, tuple):
                field = ttk.Combobox(row, width=32, state="readonly", values=initial)
                field.current(0)
            elif isinstance(initial, list):
                field = ttk.Combobox(row, width=32, values=initial)
                if initial:
                    field.current(0)
            else:
                field = ttk.Entry(row, width=35)
                field.insert(0, initial)
            field.pack(side="left", fill="x", expand=True)
            entries[key] = field
        result = {}

        def submit():
            values = {key: field.get().strip() for key, field in entries.items()}
            if not all(values.values()):
                messagebox.showerror(title, self.t("请补齐各项资料。", "Complete all fields."), parent=panel)
                return
            result.update(values)
            panel.destroy()

        bar = self.toolbar(form)
        ttk.Button(bar, text=self.t("确认", "Confirm"), command=submit).pack(side="right")
        ttk.Button(bar, text=self.t("取消", "Cancel"), command=panel.destroy).pack(side="right", padx=5)
        panel.grab_set()
        self.window.wait_window(panel)
        self.window.grab_set()
        return result

    def approve_asset(self):
        selected = filedialog.askopenfilename(parent=self.window, title=self.t("选择已核对的 PNG 原图", "Select a reviewed PNG original"), filetypes=(("PNG", "*.png"),))
        if not selected:
            return
        path = Path(selected)

        def preview():
            from PIL import Image
            with Image.open(path) as img:
                img.thumbnail((580, 300))
                return img.convert("RGB")

        def inspect(image):
            data = self.asset_form(self.t("批准公共资产", "Approve shared asset"), (
                ("identity", "身份／资产名", "Identity / asset", list(dict.fromkeys([*self.view["gaps"], path.stem]))),
                ("state", "状态／造型", "State / look", ""), ("version", "批准版本", "Version", "R1"),
                ("inspection", "画面核对记录", "Review notes", "")), image)
            if data:
                self.update(lambda: self.workspace.approve_asset(image_path=path, **data))

        self.task(preview, inspect, self.t("正在读取原图…", "Loading the original image…"))

    def open_clicked_asset(self, event):
        row = self.assets.identify_row(event.y)
        if row and self.assets.identify_region(event.x, event.y) == "cell":
            self.assets.selection_set(row)
            self.guarded(lambda: self.open_media_library(open_selected=True))

    def open_media_library(self, *, open_selected=False):
        from .media_catalog import MediaCatalog, MediaItem, category_for_filename
        from .media_gallery import open_media_gallery

        if self.workspace is None:
            return
        root = self.workspace.root
        approved = self.t("批准公共资产", "Approved shared asset")
        assets = self.view["assets"]
        items = []
        for asset in assets:
            stored = asset.digest + ".png" if re.fullmatch(r"[0-9a-f]{64}", asset.digest) else "unavailable"
            caption = f"{approved} · {asset.identity} · {asset.state} · {asset.version}"
            items.append(MediaItem(asset.id, root / "images" / stored, category_for_filename(asset.filename),
                                   caption, name=asset.filename, expected_digest=asset.digest))
        picks = self.assets.selection()
        selected = (assets[int(picks[0])].id,) if picks else ()
        return open_media_gallery(self.window, items, catalog=MediaCatalog(root / "media-catalog.json"),
                                  selected=selected, allow_import=True,
                                  title=self.t("批次素材库", "Batch media library"),
                                  open_selected=open_selected)

    def reuse_asset(self):
        picks = self.assets.selection()
        if not picks:
            raise ValueError(self.t("请先选一项批准资产。", "Select an approved asset first."))
        asset = self.view['assets'][int(picks[0])]
        group = self.selected_row()['group']
        self.update(lambda: self.workspace.reuse_asset(self.episode_id, group, asset.identity, asset.state, asset.version),
                    result_message=lambda _r: self.t(f"已将批准图绑定到 {group}。", f"Approved image linked to {group}."))

    def show_requirements(self):
        if not hasattr(self, "requirements"):
            return
        self.requirements.delete(*self.requirements.get_children())
        for index, req in enumerate(self.view.get("requirements", {}).get(self.group_box.get(), [])):
            use = self.t("交付", "Delivery") if req.deliver else self.t("参考", "Reference")
            self.requirements.insert("", "end", iid=str(index), values=(req.identity, req.state, req.version, use))

    def require_asset(self):
        group = self.selected_row()['group']
        picks = self.assets.selection()
        asset = self.view['assets'][int(picks[0])] if picks else None
        reference, delivery = self.t("参考图", "Reference only"), self.t("交付图", "Delivery image")
        data = self.asset_form(self.t("指定本组所需资产", "Specify a required asset"), (
            ("identity", "身份／资产名", "Identity / asset", asset.identity if asset else self.view["gaps"]),
            ("state", "状态／造型", "State / look", asset.state if asset else ""),
            ("version", "准确版本", "Exact version", asset.version if asset else "R1"),
            ("use", "用途", "Use", (reference, delivery))))
        if data:
            deliver = data.pop('use') == delivery
            self.update(lambda: self.workspace.require_asset(self.episode_id, group, **data, deliver=deliver))

    def remove_requirement(self):
        group = self.selected_row()['group']
        picks = self.requirements.selection()
        if not picks:
            raise ValueError(self.t("请选择要移除的依赖。", "Select a requirement to remove."))
        req = self.view['requirements'][group][int(picks[0])]
        self.update(lambda: self.workspace.remove_requirement(self.episode_id, group, req.identity, req.state, req.version))

    def resolve_requirements(self):
        group = self.selected_row()['group']
        self.update(lambda: self.workspace.resolve_required_assets(self.episode_id, group),
                    result_message=lambda gaps: self.t("已绑定匹配图。剩余缺项", "Bound matches. Remaining requirements") + f" · {len(gaps)}")

    def queue_asset(self):
        group = self.selected_row()['group']
        data = self.asset_form(self.t(f"为 {group} 安排资产生图", f"Queue asset image for {group}"), (
            ("kind", "类型", "Type", ("角色", "道具 / HUD", "场景") if not self.english else ("Character", "Prop / HUD", "Location")), ("title", "身份／资产名", "Identity / asset", self.view["gaps"]),
            ("state", "状态／造型", "State / look", ""), ("brief", "图像要求", "Image brief", "")))
        if data:
            data["kind"] = {"Character": "角色", "Prop / HUD": "道具 / HUD", "Location": "场景"}.get(data["kind"], data["kind"])
            self.update(lambda: BatchQueue(self.workspace).enqueue_asset(self.episode_id, group, **data))

    def enqueue(self, all_episodes):
        kinds = tuple(key for key, var in self.kinds.items() if var.get())
        if not kinds:
            raise ValueError(self.t("请选择至少一种任务。", "Select at least one task type."))
        episodes = list(self.episode_ids) if all_episodes else [self.episode_id]
        workspace = self.workspace

        def add():
            pending = [ep for ep in episodes if not workspace.plan_approved(ep)]
            if pending:
                raise ValueError(self.t("请先在整集规划中确认：", "Approve the episode plans first: ") + ", ".join(pending))
            queue = BatchQueue(workspace)
            for ep in episodes:
                queue.enqueue(ep, kinds)

        self.update(add)

    def fill_jobs(self, jobs, spent):
        selected = self.jobs.selection()
        self.jobs.delete(*self.jobs.get_children())
        self.job_records = {}
        shots = {row['shot_id']: row['slot'] for row in self.view.get('trace', []) if row.get('slot')}
        for job in jobs:
            kind, state = job['kind'], job['status']
            identity = str(job['id'])
            group = job['group_id']
            if job['shot_id']:
                slot = shots.get(job['shot_id']) if job['episode'] == self.episode_id else None
                group += f"-{slot:02d}" if slot else f" · {job['shot_id'][:7]}"
            self.jobs.insert("", "end", iid=identity, values=(job['episode'], group,
                self.t(*TASK_KINDS.get(kind, (kind, kind))), self.t(*TASK_STATES.get(state, (state, state))), job.get('message', '')))
            self.job_records[identity] = job
        if selected and selected[0] in self.job_records:
            self.jobs.selection_set(selected[0])
        waiting = [job for job in jobs if job['status'] in ('queued', 'blocked')]
        texts = sum(job['kind'] in ('shot', 'prompt') for job in waiting)
        pictures = len(waiting) - texts
        self.queue_status.set(self.t(f"{len(jobs)} 项 · 已提交 {spent} 次 · 待提交估算：文本 {texts} 次，生图 {pictures} 次",
                                     f"{len(jobs)} tasks · {spent} requests submitted · Pending estimate: {texts} text, {pictures} image requests"))

    def selected_job(self):
        selected = self.jobs.selection()
        if not selected:
            raise ValueError(self.t("请选择一项队列任务。", "Select a queued task."))
        return self.job_records[selected[0]]

    def run_queue(self):
        max_requests = int(self.budget.get())
        if max_requests < 0:
            raise ValueError(self.t("请求上限必须为非负整数。", "Enter a non-negative request limit."))
        if not self.job_records:
            raise ValueError(self.t("请先选择任务并将本集加入队列。", "Select task types and queue the episode first."))
        text, image = [settings[box.current()] if settings else None for box, settings in self.model_boxes]
        if max_requests > 0 and text is None and image is None:
            raise ValueError(self.t("请先到主界面「API 接入」保存本次文本或生图设置，然后回来运行。", "Save text or image settings in API connections, then reopen the batch to run it."))
        stop = Event()
        workspace = self.workspace
        eid = self.episode_id
        self.stop = stop

        def run():
            queue = BatchQueue(workspace)
            queue.run(text, image, max_requests=max_requests, stop=stop, poll_rounds=12)
            return self.snapshot(workspace, eid)

        def finish(view):
            self.render(view)
            self.budget.set(str(view["limit"]))
            self.status.set(self.t("队列已停在当前进度。请查看各任务状态和候选。", "Queue stopped at the recorded progress. Check the task states and candidates."))

        self.task(run, finish, self.t("队列运行中，可在当前请求结束后暂停。", "Running. You can pause after the active request."))
        messages = Queue()

        def read_status():
            try:
                q = BatchQueue(workspace)
                messages.put((q.jobs(), q.spent()))
            except Exception:
                messages.put(None)

        def poll():
            if self.stop is not stop:
                return
            try:
                record = messages.get_nowait()
            except Empty:
                self.window.after(250, poll)
                return
            if record:
                self.fill_jobs(*record)
            self.window.after(1500, start_read)

        def start_read():
            if self.stop is stop:
                Thread(target=read_status, daemon=True).start()
                self.window.after(250, poll)

        self.window.after(500, start_read)

    def pause_queue(self):
        if self.stop:
            self.stop.set()
            self.status.set(self.t("已请求暂停，正在等待当前请求结束。", "Pausing after the active request."))
            self.pause.state(["disabled"])

    def review_job(self):
        job = self.selected_job()
        if job['status'] != 'review':
            self.show_text(self.t("任务详情", "Task details"), job.get('message') or self.t("尚无待审候选。", "No candidate waiting for review."))
            return
        if job['kind'] in ('shot', 'prompt'):
            identity = job['id']
            queue = BatchQueue(self.workspace)
            self.task(lambda: queue.candidate_text(identity), lambda text: self.show_text(
                self.t("核对文字候选", "Review text candidate"), text,
                lambda: self.update(lambda: queue.apply_text(identity))), self.t("读取候选…", "Reading candidate…"))
        else:
            image_job_id = json.loads(job['candidate']).get('image', {}).get('id')
            self.edit_group(job['group_id'], job['episode'], image_job_id)

    def review_group_text(self):
        job = self.selected_job()
        if job['kind'] not in ('shot', 'prompt'):
            raise ValueError(self.t("请选择同组的一项分镜或提示词任务。", "Select a shot or prompt task from the group."))
        args = job['episode'], job['group_id'], job['kind']
        workspace = self.workspace

        def review(text):
            if not text:
                raise ValueError(self.t("本组没有可审的同类候选。", "This group has no candidates of this type ready to review."))
            self.show_text(self.t("整组审核文字", "Review group text") + f" · {args[0]} / {args[1]}", text,
                           lambda: self.update(lambda: BatchQueue(workspace).apply_group_text(*args, expected=text)))

        self.task(lambda: BatchQueue(workspace).group_preview(*args), review, self.t("读取整组候选…", "Loading group candidates…"))

    def retry_job(self):
        job = self.selected_job()
        confirmed = False
        if job['status'] in ('uncertain', 'review'):
            confirmed = messagebox.askyesno(self.window.title(), self.t("请先到服务商核对这次提交。已核实并允许重新提交（可能再次计费）？",
                "Check the previous submission with your provider. Have you verified it and authorized another potentially billable request?"), parent=self.window)
            if not confirmed:
                return
        self.update(lambda: BatchQueue(self.workspace).retry(job['id'], confirmed=confirmed))

    def publish(self, series):
        workspace = self.workspace
        episode = self.episode_id
        configured = self.validators.get(workspace.rules)
        validator = Path(configured) if configured else None
        if not validator or not validator.is_file():
            selected = filedialog.askopenfilename(parent=self.window, title=self.t("选择当前制作规则的校验脚本", "Choose the validator for these production rules"), filetypes=(("Python", "*.py"),))
            if not selected:
                return
            validator = Path(selected)
        output = filedialog.asksaveasfilename(parent=self.window, title=self.t("另存交付版本", "Save a delivery revision"),
            filetypes=(("ZIP", "*.zip"),), defaultextension=".zip", confirmoverwrite=False, initialfile=f"{workspace.title if series else episode}.zip")
        if output:
            destination = Path(output)
            replace = destination.is_file()
            if replace and not messagebox.askyesno(self.window.title(), self.t(
                "此交付包已存在。新版本验收通过后替换它？", "This delivery already exists. Replace it after the new version passes validation?"), parent=self.window):
                return
            def build():
                if series:
                    return publish_series(workspace, {workspace.rules: validator}, destination, replace=replace)
                return publish_episode(workspace, episode, validator, destination, replace=replace)
            self.update(build, label=self.t("正在复核并打包…", "Validating and packaging…"),
                        result_message=lambda p: self.t(f"已导出 {p}", f"Exported {p}"))

    def close(self):
        if self.busy:
            if self.stop:
                self.pause_queue()
            self.status.set(self.t("正在完成当前操作。完成后可关闭，进度保存在批次中。", "Finishing the current action. You can close after progress is saved."))
            return
        self.window.destroy()
