"""Build the storyboard workbench's home screen and project shortcuts."""

import tkinter as tk
from tkinter import ttk

from .production_rules import DELIVERY_TARGET, OTHER_VIDEO_MODELS, RULE_LABELS


BACKGROUND = "#edf2f7"
NAVY = "#182b3c"
INK = "#1c2c3b"
MUTED = "#435c70"
ACCENT = "#23617f"


PAGE_CAPTIONS = ("故事板制作", "检查验收", "API 接入")


def build_navigation(window, label_text, change_language, selected_rules, switch_rules):
    def label(parent, caption, **options):
        return label_text(tk.Label(parent, **options), caption)

    styles = ttk.Style(window)
    styles.theme_use("clam")
    styles.configure("Workbench.TButton", padding=(9, 4), foreground=NAVY)
    styles.configure("Primary.Workbench.TButton", padding=(12, 5), foreground="white",
                     background=ACCENT, bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
    styles.map("Primary.Workbench.TButton", background=[("disabled", "#7d8c99"), ("active", "#184b65")])
    window.configure(background=BACKGROUND)
    header = tk.Frame(window, bg=NAVY, padx=16, pady=12)
    header.pack(fill="x")
    header.columnconfigure(0, weight=1)
    label(header, "ComicFlow 漫剧制片工作台", bg=NAVY, fg="white", font=("TkDefaultFont", 17, "bold")).grid(
        row=0, column=0, sticky="w")
    label(header, DELIVERY_TARGET, bg=NAVY, fg="#e3eef5").grid(row=1, column=0, sticky="w", pady=(3, 0))
    label(header, OTHER_VIDEO_MODELS, bg=NAVY, fg="#c6d9e5", anchor="w", justify="left",
          wraplength=820).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(3, 0))
    language = tk.Frame(header, bg=NAVY)
    language.grid(row=0, column=1, rowspan=2, sticky="e")
    label(language, "界面语言", bg=NAVY, fg="#c6d9e5").pack(side="left", padx=(0, 6))
    ttk.Button(language, text="中文 / English", command=change_language, style="Workbench.TButton").pack(side="left")

    rule_bar = tk.Frame(window, bg=BACKGROUND, padx=16)
    rule_bar.pack(fill="x", pady=(5, 5))
    label(rule_bar, "制作规则", bg=BACKGROUND, fg=MUTED).pack(side="left", padx=(0, 7))
    rules_buttons = []
    for rules, caption in RULE_LABELS.items():
        control = label_text(ttk.Radiobutton(rule_bar, variable=selected_rules, value=rules,
                                            command=lambda value=rules: switch_rules(value)), caption)
        control.pack(side="left", padx=(0, 8))
        rules_buttons.append(control)
    styles.configure("Navigation.TNotebook.Tab", padding=(20, 8))
    navigation = ttk.Notebook(window, style="Navigation.TNotebook")
    navigation.pack(fill="both", expand=True, padx=12, pady=(0, 8))
    pages = tuple(ttk.Frame(navigation) for _ in PAGE_CAPTIONS)
    for page in pages:
        navigation.add(page)
    navigation.enable_traversal()
    return navigation, pages, rules_buttons


def build_production_page(page, label_text, callbacks):
    def button(parent, caption, action, *, primary=False):
        style = "Primary.Workbench.TButton" if primary else "Workbench.TButton"
        return label_text(ttk.Button(parent, command=callbacks[action], style=style), caption)

    flow = tk.Frame(page, bg=BACKGROUND, padx=7, pady=8)
    flow.pack(fill="both", expand=True)
    flow.columnconfigure(tuple(range(3)), weight=1, uniform="stage")
    for row in (1, 2, 3):
        flow.rowconfigure(row, weight=1, uniform="stage")
    shortcuts = tk.Frame(flow, bg=BACKGROUND)
    shortcuts.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
    shortcuts.columnconfigure(tuple(range(3)), weight=1, uniform="shortcut")
    routes = (
        ("新建项目", "先选保存位置，软件会创建 .cfproject。已有剧本可导入 TXT 或 Markdown。", "new"),
        ("继续已有项目", "打开 ComicFlow 保存的 .cfproject。想试用可打开 Examples/SB01.cfproject。", "open"),
        ("验收已有 ZIP", "选择已有的交付压缩包，无需解压。选完点「开始验收」。", "review_zip"),
    )
    controls = []
    for column, (caption, description, action) in enumerate(routes):
        route = tk.Frame(shortcuts, bg=BACKGROUND, padx=9, pady=4)
        route.grid(row=0, column=column, sticky="nsew", padx=4)
        control = button(route, caption, action, primary=action == "new")
        control.pack(anchor="w")
        detail = label_text(tk.Label(route, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=220),
                            description)
        detail.pack(fill="x", pady=(4, 0))
        route.bind("<Configure>", lambda event, text=detail: text.configure(wraplength=max(100, event.width - 18)))
        controls.append(control)

    steps = (
        ("剧本创作", "从构思写到剧本草稿，可本地编辑或请文本模型协助。", "script"),
        ("分镜拆分", "导入批准剧本，逐镜安排动作、景别和对白。", "shots"),
        ("资产分析", "从剧本整理角色、服装状态、场景和道具。", "inventory"),
        ("资产图生成", "为角色、场景、道具或净板建立生图任务。", "generate_assets"),
        ("故事板图生成", "按镜头清单生成板页，选择参考图后提交。", "generate_board"),
        ("提示词生成", "按镜头起草 Seedance 2.0 的成片动作和声音。", "prompts"),
        ("角色服装设计", "选取服装参考，进入角色生图并带入参考图。", "costume"),
        ("角色动作设计", "用 3D 导演台摆姿势和机位，导入取景图辅助生图。", "pose"),
        ("故事板组打包交付", "核对板格、净板和文字后，保存正式交付 ZIP。", "deliver"),
    )
    for index, (caption, description, action) in enumerate(steps):
        card = tk.Frame(flow, bg="white", highlightbackground="#cfdae3", highlightthickness=1, padx=11, pady=8)
        card.grid(row=index // 3 + 1, column=index % 3, padx=4, pady=4, sticky="nsew")
        card.columnconfigure(0, weight=1)
        control = button(card, caption, action, primary=action == "deliver")
        control.grid(row=0, column=0, sticky="w")
        detail = label_text(tk.Label(card, anchor="w", justify="left", bg="white", fg=MUTED, wraplength=240),
                            description)
        detail.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        card.bind("<Configure>", lambda event, text=detail: text.configure(wraplength=max(100, event.width - 24)))
        controls.append(control)

    tools = tk.Frame(flow, bg=BACKGROUND)
    tools.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 1))
    for caption, action in (("单组制片", "group"), ("批准图像", "assets"),
                            ("排版与交接", "layout"), ("对白与九图预算", "preflight")):
        control = button(tools, caption, action)
        control.pack(side="left", padx=(4, 2))
        controls.append(control)
    return controls
