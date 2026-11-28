"""Illustrated, offline introductions to the workbench's normal entry points."""

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from .workbench_home import ACCENT, BACKGROUND, INK, MUTED


TUTORIAL_IMAGES = Path("assets/workbench_tutorial")
TUTORIAL_LOCALES = ("zh", "en")
SECTIONS = (
    ("start", ("快速开始", "Quick start"), (
        ("先选顶部的「英文影片制作」或「中文影片制作」。界面语言可在右上角单独切换。",
         "Choose English or Chinese film production at the top. The interface language switches separately."),
        ("点「新建项目」制作单组；有整集或多集剧本时，在「故事板制作」打开「批量制作中心」。",
         "Use New project for a single group. For one or more episode scripts, open the batch center under Storyboard production."),
        ("已经有剧本时，在项目里点「导入批准剧本」，选 TXT 或 Markdown。也可先打开内置样例练习。",
         "To start from a script, use Import approved script in the project and select TXT or Markdown. You can also open a sample."),
    ), ("新建项目", "New project")),
    ("production", ("从剧本到交付", "Script to delivery"), (
        ("在「剧本创作」写或导入稿件，点「用左侧稿件拆分镜」。核对镜头后，点「下一步：分析资产」。",
         "Write or import a script, then choose Plan shots with left draft. Review the shots and choose Next: Analyze assets."),
        ("在「人物动作编排 → 动作参考库」记下片段时间和镜头笔记，用笔记新建动作卡或追加到选中的卡。预演后可生成资产图和故事板图，也可导入批准图。",
         "Log clip times and notes in Action sequencing → Action reference library. Create a card from your notes or add them to a selected card. After previewing, generate asset and storyboard images or import approved ones."),
        ("在英文项目的「复核与交付」或中文项目的「文本与排版」逐格核对，确认当前版后导出 ZIP。",
         "In Review & delivery (English projects) or Text, layout & delivery (Chinese projects), review each panel and export the ZIP."),
    ), ("打开剧本创作", "Open script writing")),
    ("review", ("检查交付 ZIP", "Check a delivery ZIP"), (
        ("点「验收已有 ZIP」，选择原始压缩包。先选与交付包一致的中英文制作规则。",
         "Choose Validate an existing ZIP and select the original archive. Select the production rules used by that delivery."),
        ("点「开始验收」。英文版内置严格校验，中文版可选择对应的校验脚本。",
         "Click Validate ZIP. English strict validation is built in. For Chinese deliveries, choose the matching validator script."),
        ("点「逐格复核」查看故事板、净板和文字。可到「景别机位与格间衔接」看同组与跨组的前后镜。",
         "Choose Review panels to see the storyboard, clean plates and text. Use Framing & cut continuity for adjacent shots within or across groups."),
    ), ("选择要验收的 ZIP", "Choose a ZIP to validate")),
    ("api", ("配置 API", "Connect an API"), (
        ("按用途进入「文本创作」「AI 审图」或「图像生成」，选择支持该用途的服务商和模型。",
         "Open Text drafting, AI image review or Image generation, then choose a provider and a model for the task."),
        ("填写模型 ID 和服务商密钥，点「保存本次设置」。按所选服务商界面填写需要的凭证。",
         "Enter the model ID and the provider's credentials, then choose Save for this session."),
        ("调用前预览软件锁定规则和本次资料。确认提交后才会使用服务商额度，本地排版和验收可离线操作。",
         "Preview the fixed instructions and input first. A confirmed request uses provider quota. Local layout and validation work offline."),
    ), ("打开 API 接入", "Open API connections")),
)


def build_tutorial(page, actions, sample_action=None):
    def language():
        return getattr(page._root(), "ui_language", "zh")

    def local(pair):
        return pair[language() == "en"]

    content = tk.Frame(page, bg=BACKGROUND, padx=14, pady=14)
    content.pack(fill="both", expand=True)
    content.columnconfigure(1, weight=1)
    content.rowconfigure(0, weight=1)

    topics = tk.Frame(content, bg=BACKGROUND)
    topics.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
    topic_buttons = []
    for index in range(len(SECTIONS)):
        button = ttk.Button(topics, width=21, command=lambda index=index: show(index), style="Workbench.TButton")
        button.pack(fill="x", pady=(0, 6))
        topic_buttons.append(button)

    article = tk.Frame(content, bg="white", padx=17, pady=13, highlightbackground="#cfdae3", highlightthickness=1)
    article.grid(row=0, column=1, sticky="nsew")
    title = tk.Label(article, bg="white", fg=INK, font=("TkDefaultFont", 15, "bold"), anchor="w")
    title.pack(fill="x")
    buttons = tk.Frame(article, bg="white")
    buttons.pack(side="bottom", fill="x", pady=(7, 0))
    primary = ttk.Button(buttons, style="Primary.Workbench.TButton",
                         command=lambda: actions[SECTIONS[selected][0]]())
    primary.pack(side="left")
    sample = ttk.Button(buttons, style="Workbench.TButton", command=sample_action)
    diagram = tk.Label(article, bg="#f0f4f8", bd=0, fg=MUTED, anchor="center")
    diagram.pack(fill="x", pady=(9, 10))
    steps = tk.Frame(article, bg="white")
    steps.pack(fill="x")
    steps.columnconfigure(1, weight=1)
    instructions = []
    for index in range(3):
        tk.Label(steps, text=f"{index + 1}.", bg="white", fg=ACCENT).grid(
            row=index, column=0, sticky="nw", padx=(0, 7), pady=(0, 5))
        statement = tk.Label(steps, bg="white", fg=INK, anchor="w", justify="left", wraplength=555)
        statement.grid(row=index, column=1, sticky="ew", pady=(0, 5))
        instructions.append(statement)

    selected = 0
    cache = {}
    rendered = None

    def update_image():
        nonlocal rendered
        key = (SECTIONS[selected][0], language())
        if key not in cache:
            images = Path(__file__).resolve().parents[1] / TUTORIAL_IMAGES
            image_path = images / f"{key[0]}_{key[1]}.png"
            if key[1] == "zh" and not image_path.is_file():
                image_path = images / f"{key[0]}_en.png"
            try:
                with Image.open(image_path) as original:
                    cache[key] = original.copy()
            except OSError:
                cache[key] = None
        source = cache[key]
        if source is None:
            diagram.configure(image="", text=local(("截图暂未载入，请按下方步骤操作。",
                                                     "The screenshot is unavailable. Follow the steps below.")))
            diagram.image = None
            rendered = None
            return
        bounds = (max(170, article.winfo_width() - 36), max(110, min(305, article.winfo_height() - 220)))
        scale = min(1, bounds[0] / source.width, bounds[1] / source.height)
        size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
        if rendered != (key, size):
            diagram.image = ImageTk.PhotoImage(source.resize(size, Image.Resampling.LANCZOS), master=page)
            diagram.configure(image=diagram.image, text="")
            rendered = (key, size)

    def resize(event):
        for statement in instructions:
            statement.configure(wraplength=max(140, event.width - 65))
        update_image()

    def show(index):
        nonlocal selected
        selected = index
        for n, (button, (_, name, _, _)) in enumerate(zip(topic_buttons, SECTIONS)):
            button.configure(text=local(name),
                             style="Primary.Workbench.TButton" if n == selected else "Workbench.TButton")
        _, header, descriptions, caption = SECTIONS[selected]
        title.configure(text=local(header))
        for statement, description in zip(instructions, descriptions):
            statement.configure(text=local(description))
        primary.configure(text=local(caption))
        if selected == 0 and sample_action:
            sample.configure(text=local(("打开示例项目", "Open sample project")))
            sample.pack(side="left", padx=(7, 0))
        else:
            sample.pack_forget()
        update_image()

    article.bind("<Configure>", resize)
    show(0)
    return lambda: show(selected), (primary, sample)
