"""Build the desktop workbench navigation and the guided production home."""

import tkinter as tk
from tkinter import ttk

from .brand import APP_NAME_ZH, VERSION
from .guide_links import guide_button
from .production_rules import DELIVERY_TARGET, OTHER_VIDEO_MODELS, RULE_LABELS
from .workbench_style import ACCENT, BACKGROUND, GREEN, INK, LINE, MUTED, SURFACE, TINT, configure_workbench
from .workbench_tasks import WorkbenchTasks


PAGE_CAPTIONS = ("故事板制作", "电商信息流视频复刻", "检查验收", "API 接入", "使用教程")
WORKFLOW_STEPS = (
    ("导入剧本", "Import scripts", "import"),
    ("整集规划", "Episode plan", "plan"),
    ("公共资产", "Shared assets", "assets"),
    ("执行队列", "Production queue", "queue"),
    ("验收交付", "Review & delivery", "delivery"),
)
PROJECT_SHORTCUTS = (
    ("新建项目", "new"),
    ("继续已有项目", "open"),
    ("批量制作中心", "batch"),
    ("验收已有 ZIP", "review_zip"),
)
PRODUCTION_TOOLS = (
    ("剧本创作", "script"),
    ("分镜拆分", "shots"),
    ("资产分析", "inventory"),
    ("资产图生成", "generate_assets"),
    ("故事板图生成", "generate_board"),
    ("提示词生成", "prompts"),
    ("角色服装设计", "costume"),
    ("人物动作编排", "action_sequence"),
    ("角色动作设计", "pose"),
    ("故事板组打包交付", "deliver"),
    ("单组制片", "group"),
    ("批准图像", "assets"),
    ("排版与交接", "layout"),
    ("对白与九图预算", "preflight"),
)
GUIDANCE = (
    "先选保存位置，软件会创建 .cfproject。已有剧本可导入 TXT 或 Markdown。",
    "打开已保存的 .cfproject，或试用 Examples/SB01.cfproject。",
    "选择已有的交付压缩包，无需解压。选完点「开始验收」。",
)
_KEEP = object()


def _wrap_to_parent(parent, labels, *, inset=0, minimum=80):
    def fit(event):
        width = max(minimum, event.width - inset)
        for label in labels:
            if int(label.cget("wraplength")) != width:
                label.configure(wraplength=width)

    parent.bind("<Configure>", fit, add="+")


def build_navigation(window, label_text, change_language, selected_rules, switch_rules, show_release_notes):
    styles = configure_workbench(window)
    header = tk.Frame(window, bg=SURFACE, padx=22, pady=8, highlightthickness=1, highlightbackground=LINE)
    header.pack(fill="x", pady=(0, 1))
    header.columnconfigure(1, weight=1)
    tk.Frame(header, bg=ACCENT, width=6, height=22).grid(row=0, column=0, sticky="w", padx=(0, 10))
    label_text(tk.Label(header, bg=SURFACE, fg=INK, font=("TkDefaultFont", 13, "bold")),
               APP_NAME_ZH).grid(row=0, column=1, sticky="w")
    ttk.Button(header, name="release_version", text=f"v{VERSION}", command=show_release_notes,
               style="Workbench.TButton").grid(row=0, column=2, padx=(10, 6))
    styles.configure("Workbench.TMenubutton", padding=(9, 7), background=SURFACE, foreground=INK,
                     bordercolor=LINE, lightcolor=SURFACE, darkcolor=SURFACE)
    styles.map("Workbench.TMenubutton", background=[("active", TINT)], bordercolor=[("focus", ACCENT)])
    help_button = label_text(ttk.Menubutton(header, name="workbench_help", takefocus=True,
                                          style="Workbench.TMenubutton"), "帮助")
    help_menu = tk.Menu(help_button, tearoff=False)
    help_menu.add_command(command=show_release_notes)
    help_button.configure(menu=help_menu)
    help_button.grid(row=0, column=3, padx=(0, 6))
    ttk.Button(header, text="中文 / English", command=change_language, style="Workbench.TButton").grid(
        row=0, column=4, sticky="e")

    rule_bar = tk.Frame(window, bg=BACKGROUND, padx=22)
    rule_bar.pack(fill="x", pady=(4, 0))
    label_text(tk.Label(rule_bar, bg=BACKGROUND, fg=MUTED), "制作规则").pack(side="left", padx=(0, 8))
    rules_buttons = []
    for rules, caption in RULE_LABELS.items():
        control = label_text(ttk.Radiobutton(rule_bar, variable=selected_rules, value=rules,
                                             command=lambda value=rules: switch_rules(value)), caption)
        control.pack(side="left", padx=(0, 12))
        rules_buttons.append(control)

    notice = tk.Frame(window, bg=BACKGROUND, padx=22)
    notice.pack(fill="x", pady=(2, 4))
    model_note = label_text(tk.Label(notice, bg=BACKGROUND, fg=MUTED, justify="left", anchor="w"),
                            DELIVERY_TARGET)
    detail_note = label_text(tk.Label(notice, bg=BACKGROUND, fg=MUTED, justify="left", anchor="w"),
                             OTHER_VIDEO_MODELS)
    model_note.pack(side="top", anchor="w")
    detail_note.pack(side="top", anchor="w")
    _wrap_to_parent(notice, (model_note, detail_note), inset=44)

    return WorkbenchTasks(window, PAGE_CAPTIONS), rules_buttons, help_menu


def _adaptive_grid(parent, widgets, maximum, *, spacing=7):
    previous = None

    def fit(_event=None):
        nonlocal previous
        width = parent.winfo_width()
        if width <= 1:
            return
        requested = [widget.winfo_reqwidth() for widget in widgets]
        columns = maximum
        while columns > 1:
            total_width = sum(max(requested[column::columns]) for column in range(columns))
            if total_width + spacing * (columns - 1) <= width:
                break
            columns -= 1
        if columns == previous:
            return
        for column in range(maximum):
            parent.columnconfigure(column, weight=int(column < columns))
        for index, widget in enumerate(widgets):
            row, column = divmod(index, columns)
            widget.grid(row=row, column=column, sticky="nsew",
                        padx=(0, spacing if column < columns - 1 else 0), pady=(0, spacing))
        previous = columns

    # Mapping the first row gives Tk a size before the first resize event.
    for index, widget in enumerate(widgets):
        widget.grid(row=index // maximum, column=index % maximum, sticky="nsew")
    parent.bind("<Configure>", fit, add="+")
    return fit


def build_production_page(page, label_text, callbacks, *, action_picker=None, production_picker=None):
    window = page._root()
    controls = []
    ttk.Style(window).configure("A.Home.Tool.TButton", padding=(8, 5))
    status = {"project_title": "", "project_meta": "", "progress": None, "next_step": None}

    def button(parent, caption, action, *, name=None, style="Workbench.TButton"):
        options = {"name": name} if name else {}
        control = ttk.Button(parent, command=action, style=style, **options)
        if caption:
            label_text(control, caption)
        controls.append(control)
        return control

    if action_picker is not None:
        action_picker.mount(page, label_text)
    if production_picker is not None:
        production_picker.mount(page, label_text)

    viewport = tk.Frame(page, bg=BACKGROUND)
    viewport.pack(fill="both", expand=True)
    canvas = tk.Canvas(viewport, bg=BACKGROUND, highlightthickness=0, borderwidth=0, yscrollincrement=18)
    scroll = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    content = tk.Frame(canvas, bg=BACKGROUND, padx=14, pady=10)
    content_window = canvas.create_window(0, 0, window=content, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(content_window, width=event.width))
    content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))

    title = label_text(tk.Label(content, bg=BACKGROUND, fg=INK, font=("TkDefaultFont", 19, "bold"), anchor="w"),
                       "故事板制作")
    title.pack(fill="x")
    intro = label_text(tk.Label(content, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left"),
                       "按步骤完成一集故事板。")
    intro.pack(fill="x", pady=(1, 8))
    _wrap_to_parent(content, (intro,), inset=28)

    rail = tk.Frame(content, bg=BACKGROUND)
    rail.pack(fill="x")
    steps = []
    for index, (caption, _english, identifier) in enumerate(WORKFLOW_STEPS):
        steps.append(button(rail, caption,
                            lambda value=index: callbacks["batch_step"](value)
                            if "batch_step" in callbacks else callbacks["batch"](),
                            name=f"a_home_{identifier}", style="A.Step.TButton"))
    fit_steps = _adaptive_grid(rail, steps, len(steps))

    hero = tk.Frame(content, bg=TINT, highlightbackground=LINE, highlightthickness=1, padx=15, pady=12)
    hero.pack(fill="x", pady=(2, 8))
    hero.columnconfigure((0, 1), weight=1, uniform="project")
    project = tk.Frame(hero, bg=TINT)
    project.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
    label_text(tk.Label(project, bg=TINT, fg=ACCENT, anchor="w"), "当前项目").pack(fill="x")
    project_name = tk.Label(project, bg=TINT, fg=INK, font=("TkDefaultFont", 15, "bold"), anchor="w", justify="left")
    project_name.pack(fill="x", pady=(1, 0))
    meta_label = tk.Label(project, bg=TINT, fg=MUTED, anchor="w", justify="left")
    meta_label.pack(fill="x", pady=(0, 6))
    _wrap_to_parent(project, (project_name, meta_label))
    primary = button(project, "", callbacks.get("resume", callbacks["batch"]), name="a_home_resume",
                     style="Primary.Workbench.TButton")
    primary.pack(anchor="w")
    progress_card = tk.Frame(hero, bg=SURFACE, highlightbackground=LINE, highlightthickness=1, padx=11, pady=9)
    progress_card.grid(row=0, column=1, sticky="nsew")
    label_text(tk.Label(progress_card, bg=SURFACE, fg=INK, anchor="w", font=("TkDefaultFont", 10, "bold")),
               "制作进度").pack(fill="x")
    status_line = tk.Label(progress_card, bg=SURFACE, fg=MUTED, anchor="w", justify="left")
    status_line.pack(fill="x", pady=(1, 3))
    ttk.Style(window).configure("A.Home.Horizontal.TProgressbar", thickness=5, background=GREEN,
                                troughcolor=LINE, bordercolor=LINE, lightcolor=GREEN, darkcolor=GREEN)
    meter = ttk.Progressbar(progress_card, mode="determinate", style="A.Home.Horizontal.TProgressbar")
    next_line = tk.Label(progress_card, bg=SURFACE, fg=MUTED, anchor="w", justify="left")
    next_line.pack(fill="x")
    _wrap_to_parent(progress_card, (status_line, next_line), inset=24)

    route_header = tk.Frame(content, bg=BACKGROUND)
    route_header.pack(fill="x")
    label_text(tk.Label(route_header, bg=BACKGROUND, fg=INK, anchor="w", font=("TkDefaultFont", 10, "bold")),
               "项目入口").pack(side="left")
    help_button = guide_button(route_header, "home")
    if help_button is not None:
        help_button.pack(side="right", padx=(7, 0))
    if "jobs" in callbacks:
        button(route_header, "任务中心", callbacks["jobs"], name="workbench_jobs", style="A.Home.Tool.TButton").pack(
            side="right")
    routes = tk.Frame(content, bg=BACKGROUND)
    routes.pack(fill="x", pady=(3, 0))
    shortcuts = [button(routes, caption, callbacks[action], style="A.Home.Tool.TButton")
                 for caption, action in PROJECT_SHORTCUTS]
    fit_shortcuts = _adaptive_grid(routes, shortcuts, len(shortcuts))

    guidance = tk.Frame(content, bg=BACKGROUND)
    hints = []
    for caption in GUIDANCE:
        hint = label_text(tk.Label(guidance, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left",
                                   font=("TkDefaultFont", 8)), caption)
        hint.pack(fill="x")
        hints.append(hint)
    _wrap_to_parent(guidance, hints)

    def toggle_help():
        if guidance.winfo_manager():
            guidance.pack_forget()
        else:
            guidance.pack(fill="x", after=routes, pady=(0, 7))

    help_button = button(route_header, "项目文件说明", toggle_help, name="a_home_project_help",
                         style="A.Home.Tool.TButton")
    help_button.pack(side="right")
    label_text(tk.Label(content, bg=BACKGROUND, fg=INK, anchor="w", font=("TkDefaultFont", 10, "bold")),
               "单项工具").pack(fill="x", pady=(3, 0))
    tools = tk.Frame(content, bg=BACKGROUND)
    tools.pack(fill="x", pady=(3, 0))
    tools_buttons = [button(tools, caption, callbacks[action], style="A.Home.Tool.TButton")
                     for caption, action in PRODUCTION_TOOLS]
    fit_tools = _adaptive_grid(tools, tools_buttons, 5)

    def wheel(event):
        direction = -1 if event.delta > 0 or event.num == 4 else 1
        canvas.yview_scroll(direction * 3, "units")
        return "break"

    def bind_scroll(widget):
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(sequence, wheel, add="+")
        for child in widget.winfo_children():
            bind_scroll(child)

    bind_scroll(canvas)

    def reveal_focused(event):
        if not canvas.winfo_viewable():
            return
        item = event.widget
        y = item.winfo_rooty() - canvas.winfo_rooty()
        overflow = y + item.winfo_height() + 4 - canvas.winfo_height()
        if y < 4 or overflow > 0:
            region = canvas.bbox("all")
            if region and region[3] > region[1]:
                adjustment = y - 4 if y < 4 else overflow
                canvas.yview_moveto((canvas.canvasy(0) + adjustment - region[1]) / (region[3] - region[1]))

    for control in controls:
        control.bind("<FocusIn>", reveal_focused, add="+")

    def refresh(*, project_title=_KEEP, project_meta=_KEEP, progress=_KEEP, next_step=_KEEP):
        for name, value in (("project_title", project_title), ("project_meta", project_meta),
                            ("progress", progress), ("next_step", next_step)):
            if value is not _KEEP:
                status[name] = value
        english = getattr(window, "ui_language", "zh") == "en"

        def localized(zh, en):
            return en if english else zh

        name = status["project_title"]
        active = status["next_step"]
        project_name.configure(text=name or localized("尚未打开项目", "No project open"))
        meta_label.configure(text=status["project_meta"] or localized("整集或多集剧本", "Single- or multi-episode scripts"))
        primary.configure(text=localized("继续制作", "Continue production") if name else
                          localized("开始批量制作", "Start batch production"))
        progress_value = status["progress"]
        if progress_value is not None and progress_value[1]:
            done, total = progress_value
            meter.configure(maximum=total, value=done)
            if not meter.winfo_manager():
                meter.pack(fill="x", before=next_line, pady=(1, 5))
            status_line.configure(text=localized(f"{done} / {total} 组已复核", f"{done} / {total} groups reviewed"))
        else:
            meter.pack_forget()
            status_line.configure(text=localized("进度随项目显示", "Progress appears with your project"))
        if active is not None:
            zh, en, _identifier = WORKFLOW_STEPS[active]
            next_line.configure(text=localized(f"下一步  {zh}", f"Next step  {en}"))
        else:
            next_line.configure(text=localized("导入定稿后开始整集规划。", "Import a script to start episode planning."))
        for index, step in enumerate(steps):
            style = "A.Step.TButton"
            if index == (0 if active is None else active):
                style = "A.Current.Step.TButton"
            step.configure(style=style)
        content.after_idle(fit_steps)
        content.after_idle(fit_shortcuts)
        content.after_idle(fit_tools)

    refresh()
    return controls, refresh
