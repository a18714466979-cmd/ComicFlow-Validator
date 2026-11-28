"""Offline, context-sensitive guides for the workbench."""

from functools import lru_cache
from pathlib import Path
import tkinter as tk
from tkinter import font, ttk

from PIL import Image, ImageTk

from .storyboard_guide_topics import STORYBOARD_TOPICS
from .workbench_guide_topics import WORKBENCH_TOPICS
from .workbench_style import BACKGROUND, INK, LINE, MUTED, SURFACE


STORYBOARD_GUIDE_IMAGES = Path("assets/storyboard_guide")
WORKBENCH_GUIDE_IMAGES = Path("assets/workbench_guide")
GUIDE_TOPICS = {**STORYBOARD_TOPICS, **WORKBENCH_TOPICS}
TOPIC_GROUPS = (
    (("工作台入门", "Workbench basics"), ("general", "guide_navigation")),
    (("开始制作", "Getting started"), ("home", "project")),
    (("制作流程", "Production steps"), (
        "script", "shots", "drafts", "inventory", "generate_assets", "generate_board", "prompts",
    )),
    (("素材、表演与排版", "Media, performance & layout"), (
        "assets", "media", "media_preview", "costume", "action_sequence", "action_gallery",
        "action_preview", "dialogue", "pose", "director", "layout",
    )),
    (("交付", "Delivery"), ("deliver",)),
    (("电商信息流复刻", "E-commerce recreation"), (
        "ecommerce_import", "ecommerce_shots", "ecommerce_assets", "ecommerce_delivery",
    )),
    (("批量制片", "Batch production"), (
        "batch_import", "batch_plan", "batch_assets", "batch_queue", "batch_delivery",
    )),
    (("检查与返修", "Validation & repair"), ("review_zip", "review_images", "review_cuts", "review_repair")),
    (("任务与 API", "Jobs & API"), ("jobs", "api")),
)
WORKBENCH_PRACTICE_LABELS = {
    "ecommerce": ("打开电商练习", "Open e-commerce practice"),
    "batch": ("打开多集练习", "Open multiple-episode practice"),
    "review": ("打开验收练习", "Open delivery review practice"),
}


@lru_cache(maxsize=6)
def screenshot(topic, locale):
    images = WORKBENCH_GUIDE_IMAGES if topic in WORKBENCH_TOPICS else STORYBOARD_GUIDE_IMAGES
    path = Path(__file__).resolve().parents[1] / images / f"{topic}_{locale}.webp"
    try:
        with Image.open(path) as image:
            return image.convert("RGB")
    except (OSError, ValueError):
        return None


class StoryboardGuide:
    def __init__(self, parent, *, on_return, on_overview, on_practice=None):
        self.frame = ttk.Frame(parent, name="storyboard_guide", padding=(12, 8))
        self.current_topic = "home"
        self.on_practice = on_practice
        self.can_practice = bool(on_practice)
        self.workbench_practices = frozenset()
        self.allow_overview = True
        self.contextual = False
        self.zoomed = False
        self.image = None
        self.image_key = None
        self.paint_id = None
        self.body_font = font.nametofont("TkDefaultFont", root=parent).copy()
        self.body_font.configure(size=max(10, abs(self.body_font.cget("size"))))
        self.section_font = self.body_font.copy()
        self.section_font.configure(weight="bold")
        self.heading_font = self.section_font.copy()
        self.heading_font.configure(size=self.body_font.cget("size") + 5)
        self.build(on_return, on_overview)
        self.refresh()

    @property
    def english(self):
        return getattr(self.frame._root(), "ui_language", "zh") == "en"

    def local(self, pair):
        return pair[int(self.english)]

    def text(self, chinese, english):
        return english if self.english else chinese

    def build(self, on_return, on_overview):
        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill="x", pady=(0, 8))
        self.header = ttk.Label(toolbar, font=self.section_font)
        self.header.pack(side="left", fill="x", expand=True)
        self.return_button = ttk.Button(toolbar, name="guide_return", command=on_return, style="Primary.Workbench.TButton")
        self.return_button.pack(side="right")
        self.overview_button = ttk.Button(toolbar, name="guide_overview", command=on_overview)
        self.overview_button.pack(side="right", padx=(0, 6))

        body = ttk.Frame(self.frame)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        outline = ttk.Frame(body)
        outline.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        self.tree = ttk.Treeview(outline, name="guide_topic_list", show="tree", selectmode="browse", height=18)
        self.tree.column("#0", width=226, minwidth=172, stretch=False)
        self.tree.pack(side="left", fill="y")
        list_scroll = ttk.Scrollbar(outline, orient="vertical", command=self.tree.yview)
        list_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=list_scroll.set)
        for index, (_, topics) in enumerate(TOPIC_GROUPS):
            category = f"guide-section-{index}"
            self.tree.insert("", "end", iid=category)
            for key in topics:
                self.tree.insert(category, "end", iid=key)
        self.tree.bind("<<TreeviewSelect>>", self.select)

        reader = tk.Frame(body, bg=SURFACE, highlightthickness=1, highlightbackground=LINE)
        reader.grid(row=0, column=1, sticky="nsew")
        reader.columnconfigure(0, weight=1)
        reader.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(reader, name="guide_reader", bg=SURFACE, highlightthickness=0,
                                yscrollincrement=20, xscrollincrement=20)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(reader, orient="vertical", command=self.canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        self.horizontal = ttk.Scrollbar(reader, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=self.horizontal.set)
        self.article = tk.Frame(self.canvas, bg=SURFACE, padx=16, pady=10)
        self.content_window = self.canvas.create_window(0, 0, anchor="nw", window=self.article)
        self.article.bind("<Configure>", self.update_scroll, add="+")
        self.canvas.bind("<Configure>", self.resize, add="+")
        self.title = tk.Label(self.article, name="guide_title", bg=SURFACE, fg=INK,
                              font=self.heading_font, anchor="w", justify="left")
        self.title.pack(fill="x", pady=(0, 4))
        self.intro = tk.Label(self.article, bg=SURFACE, fg=MUTED, font=self.body_font, anchor="w", justify="left")
        self.intro.pack(fill="x")
        self.picture = tk.Label(self.article, name="guide_screenshot", bg=BACKGROUND, fg=MUTED, bd=0)
        self.picture.pack(fill="x", pady=(8, 4))
        self.zoom = ttk.Button(self.article, name="guide_image_zoom", command=self.toggle_zoom)
        self.zoom.pack(anchor="w", pady=(0, 10))
        self.details = tk.Frame(self.article, bg=SURFACE)
        self.details.pack(fill="x")
        self.practice = ttk.Frame(self.article)
        self.practice_script = ttk.Button(self.practice, name="practice_script", style="Primary.Workbench.TButton",
                                          command=lambda: self.on_practice("script"))
        self.practice_script.pack(side="left", padx=(0, 6))
        self.practice_existing = ttk.Button(self.practice, name="practice_existing",
                                            command=lambda: self.on_practice("existing"))
        self.practice_existing.pack(side="left")
        self.workbench_practice = ttk.Frame(self.article)
        self.practice_buttons = {
            kind: ttk.Button(self.workbench_practice, name=f"practice_{kind}",
                             command=lambda selected=kind: self.on_practice(selected))
            for kind in WORKBENCH_PRACTICE_LABELS
        }
        self.wrap_labels = [self.title, self.intro]
        for widget in (self.canvas, self.article, self.title, self.intro, self.picture, self.details, self.zoom):
            self.bind_wheel(widget)
        self.canvas.bind("<Destroy>", self.destroy, add="+")

    def bind_wheel(self, widget):
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(event, self.wheel, add="+")

    def wheel(self, event):
        direction = -1 if event.delta > 0 or event.num == 4 else 1
        self.canvas.yview_scroll(3 * direction, "units")
        return "break"

    def update_scroll(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def resize(self, _event=None):
        if self.paint_id is None:
            self.paint_id = self.canvas.after_idle(self.layout)

    def destroy(self, event):
        if event.widget is self.canvas and self.paint_id is not None:
            self.canvas.after_cancel(self.paint_id)
            self.paint_id = None

    def layout(self):
        self.paint_id = None
        view_width = max(180, self.canvas.winfo_width())
        for label in self.wrap_labels:
            label.configure(wraplength=max(130, view_width - 34))
        locale = "en" if self.english else "zh"
        original = screenshot(self.current_topic, locale)
        whole = self.zoomed and original is not None
        width = max(view_width, original.width + 32) if whole else view_width
        self.canvas.itemconfigure(self.content_window, width=width)
        if whole:
            self.horizontal.grid(row=1, column=0, sticky="ew")
        else:
            self.horizontal.grid_remove()
            self.canvas.xview_moveto(0)
        if original is None:
            self.image = self.image_key = None
            self.picture.configure(image="", text=self.text("截图暂不可用。操作步骤在下方。", "Screenshot unavailable. Follow the steps below."))
            self.zoom.state(["disabled"])
        else:
            self.zoom.state(["!disabled"])
            image_width = original.width if whole else min(original.width, max(120, view_width - 32))
            key = (self.current_topic, locale, image_width)
            if self.image_key != key:
                image_height = round(original.height * image_width / original.width)
                self.image = ImageTk.PhotoImage(original.resize((image_width, image_height), Image.Resampling.LANCZOS),
                                                master=self.canvas)
                self.image_key = key
                self.picture.configure(image=self.image, text="")
        self.update_scroll()

    def select(self, _event=None):
        selected = self.tree.selection()
        if not selected or selected[0] not in GUIDE_TOPICS or selected[0] == self.current_topic:
            return
        self.show(selected[0])

    def show(self, topic, *, contextual=None, can_practice=None, allow_overview=None, workbench_practices=None):
        self.current_topic = topic if topic in GUIDE_TOPICS else "home"
        if contextual is not None:
            self.contextual = contextual
        if can_practice is not None:
            self.can_practice = can_practice
        if allow_overview is not None:
            self.allow_overview = allow_overview
        if workbench_practices is not None:
            self.workbench_practices = workbench_practices
        self.zoomed = False
        self.refresh(reset=True)

    def toggle_zoom(self):
        self.zoomed = not self.zoomed
        self.zoom.configure(text=self.text("适应宽度", "Fit to width") if self.zoomed
                            else self.text("放大截图", "View screenshot at full size"))
        self.layout()

    def refresh(self, *, reset=False):
        self.header.configure(text=self.text("工作台操作教程", "Workbench operations guide")
                              if self.current_topic in WORKBENCH_TOPICS
                              else self.text("故事板制作教程", "Storyboard production guide"))
        self.overview_button.configure(text=self.text("教程总览", "Tutorial overview"))
        self.return_button.configure(text=self.text("返回发起页", "Return to originating page"))
        self.return_button.state(["!disabled"] if self.contextual else ["disabled"])
        self.overview_button.state(["!disabled"] if self.allow_overview else ["disabled"])
        self.practice_script.configure(text=self.text("从剧本练习", "Practice from a script"))
        self.practice_existing.configure(text=self.text("从已有分镜练习", "Practice from existing shots"))
        self.zoom.configure(text=self.text("适应宽度", "Fit to width") if self.zoomed
                            else self.text("放大截图", "View screenshot at full size"))
        for index, (caption, topics) in enumerate(TOPIC_GROUPS):
            self.tree.item(f"guide-section-{index}", text=self.local(caption))
            for key in topics:
                self.tree.item(key, text=self.local(GUIDE_TOPICS[key].title))
        if self.tree.selection() != (self.current_topic,):
            self.tree.selection_set(self.current_topic)
            self.tree.see(self.current_topic)

        topic = GUIDE_TOPICS[self.current_topic]
        self.title.configure(text=self.local(topic.title))
        self.intro.configure(text=self.local(topic.intro))
        for widget in self.details.winfo_children():
            widget.destroy()
        self.wrap_labels = [self.title, self.intro]
        for heading, prose in topic.sections:
            title = tk.Label(self.details, text=self.local(heading), font=self.section_font,
                             bg=SURFACE, fg=INK, anchor="w", justify="left")
            paragraph = tk.Label(self.details, text=self.local(prose), font=self.body_font,
                                 bg=SURFACE, fg=INK, anchor="w", justify="left")
            title.pack(fill="x", pady=(7, 0))
            paragraph.pack(fill="x", pady=(1, 5))
            for widget in (title, paragraph):
                self.bind_wheel(widget)
                self.wrap_labels.append(widget)
        if self.current_topic == "home" and self.can_practice and self.on_practice is not None:
            self.practice.pack(fill="x", before=self.picture, pady=(9, 3))
        else:
            self.practice.pack_forget()
        if self.current_topic == "general" and self.workbench_practices and self.on_practice is not None:
            self.workbench_practice.pack(fill="x", before=self.picture, pady=(7, 0))
            for kind, button in self.practice_buttons.items():
                if kind in self.workbench_practices:
                    button.configure(text=self.local(WORKBENCH_PRACTICE_LABELS[kind]))
                    button.pack(anchor="w", pady=(0, 3))
                else:
                    button.pack_forget()
        else:
            self.workbench_practice.pack_forget()
        self.layout()
        if reset:
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
