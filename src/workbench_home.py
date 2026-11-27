"""Build the storyboard workbench's home screen and project shortcuts."""

import tkinter as tk
from tkinter import ttk

from .production_rules import RULE_LABELS


BACKGROUND = "#edf2f7"
NAVY = "#182b3c"
INK = "#1c2c3b"
MUTED = "#435c70"
ACCENT = "#23617f"


def build_home(window, label_text, change_language, selected_rules, switch_rules, callbacks):
    def label(parent, caption, **options):
        return label_text(tk.Label(parent, **options), caption)

    def button(parent, caption, command, *, primary=False):
        style = "Primary.Workbench.TButton" if primary else "Workbench.TButton"
        return label_text(ttk.Button(parent, command=command, style=style), caption)

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
    label(header, "从剧本到 SD2 交付", bg=NAVY, fg="#c6d9e5").grid(row=1, column=0, sticky="w", pady=(3, 0))
    language = tk.Frame(header, bg=NAVY)
    language.grid(row=0, column=1, rowspan=2, sticky="e")
    label(language, "界面语言", bg=NAVY, fg="#c6d9e5").pack(side="left", padx=(0, 6))
    ttk.Button(language, text="中文 / English", command=change_language, style="Workbench.TButton").pack(side="left")

    flow = tk.Frame(window, bg=BACKGROUND, padx=16, pady=9)
    flow.pack(fill="x")
    flow.columnconfigure(tuple(range(3)), weight=1, uniform="step")
    shortcuts = tk.Frame(flow, bg=BACKGROUND)
    shortcuts.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
    new_project = button(shortcuts, "新建项目", callbacks["new"], primary=True)
    open_project = button(shortcuts, "打开项目", callbacks["open"])
    new_project.pack(side="left")
    open_project.pack(side="left", padx=6)
    rule_bar = tk.Frame(shortcuts, bg=BACKGROUND)
    rule_bar.pack(side="right")
    label(rule_bar, "制作规则", bg=BACKGROUND, fg=MUTED).pack(side="left", padx=(0, 5))
    rules_buttons = []
    for rules, caption in RULE_LABELS.items():
        control = label_text(ttk.Radiobutton(rule_bar, variable=selected_rules, value=rules,
                                            command=lambda value=rules: switch_rules(value)), caption)
        control.pack(side="left", padx=(0, 3))
        rules_buttons.append(control)

    steps = (
        ("剧本与分镜", "导入批准剧本、安排镜头与对白。", "开始拆分镜", "shots"),
        ("角色、场景与道具", "导入批准素材，或用图像接口生成候选。", "制作资产图", "assets"),
        ("故事板与净板", "绑定板格和机位净板，检查 16:9 排版。", "排故事板", "layout"),
        ("SD2 提示词", "编辑分镜动作和声音，查看文本模型建议。", "写提示词", "prompts"),
        ("从项目交付", "逐格确认画面，验收并导出 ZIP。", "复核与打包", "deliver"),
        ("已有素材返修", "登记原图、定位受影响的镜头并重新打包。", "资产与返修", "repair"),
    )
    controls = [new_project, open_project]
    for index, (title, description, action, target) in enumerate(steps):
        card = tk.Frame(flow, bg="white", highlightbackground="#cfdae3", highlightthickness=1, padx=10, pady=6)
        card.grid(row=index // 3 + 1, column=index % 3, padx=3, pady=3, sticky="nsew")
        card.columnconfigure(0, weight=1)
        label(card, title, anchor="w", bg="white", fg=INK, font=("TkDefaultFont", 11, "bold")).grid(
            row=0, column=0, sticky="ew")
        detail = label(card, description, anchor="w", justify="left", bg="white", fg=MUTED, wraplength=245)
        detail.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        card.bind("<Configure>", lambda event, text=detail: text.configure(wraplength=max(100, event.width - 22)))
        control = button(card, action, callbacks[target])
        control.grid(row=2, column=0, sticky="w")
        controls.append(control)

    tools = tk.Frame(flow, bg=BACKGROUND)
    tools.grid(row=3, column=0, columnspan=3, sticky="w", pady=(3, 0))
    controls.append(button(tools, "单组制片", callbacks["group"]))
    controls.append(button(tools, "对白与九图预算", callbacks["preflight"]))
    for control in controls[-2:]:
        control.pack(side="left", padx=(3, 5))
    return rules_buttons, controls
