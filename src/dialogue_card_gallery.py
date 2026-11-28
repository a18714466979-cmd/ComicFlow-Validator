"""Page for illustrated dialogue blocking and explicit shot application."""

from functools import lru_cache
import tkinter as tk
from tkinter import font, ttk

from PIL import Image, ImageTk

from .dialogue_blocking import DIALOGUE_CARDS, dialogue_fields, dialogue_preview_path
from .guide_links import guide_button
from .workbench_style import ACCENT


CARD_CAPTIONS = (
    ("双人中景同框", "Medium two-shot"),
    ("过肩正反打", "Over-shoulder reverse"),
    ("三人三角站位", "Three-person triangle"),
)


@lru_cache(maxsize=12)
def _load_art(identity, index):
    path = dialogue_preview_path(identity, index)
    try:
        with Image.open(path) as image:
            return image.convert("RGB")
    except (OSError, ValueError, TypeError):
        return None


class DialogueCardGallery(ttk.Frame):
    def __init__(self, parent, *, english, on_back, on_complete, get_context, apply):
        super().__init__(parent, name="dialogue_cards", padding=(14, 10))
        self.english = int(english)
        self.on_back = on_back
        self.on_complete = on_complete
        self.get_context = get_context
        self.apply = apply
        self.index = 0
        self.card = DIALOGUE_CARDS[0]
        self.immersive = False
        self.resampled = None
        self.captions = []
        self.confirmation = None
        self.context_error = ""
        self.shot_choices = ()
        self.project_english = bool(english)
        self.roles = {role: tk.StringVar(self) for role in ("A", "B", "C")}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.build()
        self.select(self.card)
        self.refresh_context()

    def t(self, zh, en):
        return (zh, en)[self.english]

    def label(self, widget, zh, en):
        self.captions.append((widget, (zh, en)))
        widget.configure(text=self.t(zh, en))
        return widget

    def build(self):
        heading = ttk.Frame(self)
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        title_font = font.nametofont("TkDefaultFont", root=self).copy()
        title_font.configure(weight="bold")
        self.title_font = title_font
        self.label(ttk.Label(heading, font=title_font), "日常与表演  /  对话与站位",
                   "Everyday & performance  /  Dialogue blocking").pack(side="left")
        self.label(ttk.Button(heading, name="dialogue_back", command=self.on_back),
                   "返回动作卡图库", "Back to action cards").pack(side="right")

        self.card_row = ttk.Frame(self)
        self.card_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.card_buttons = {}
        for column, card in enumerate(DIALOGUE_CARDS):
            self.card_row.columnconfigure(column, weight=1, uniform="dialogue_card")
            button = self.label(
                ttk.Button(self.card_row, name=f"card_{card.id}", command=lambda item=card: self.select(item)),
                *CARD_CAPTIONS[column],
            )
            button.grid(row=0, column=column, sticky="ew", padx=(0, 5))
            self.card_buttons[card.id] = button

        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.preview = ttk.Frame(body)
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview.columnconfigure(0, weight=1)
        self.preview.rowconfigure(1, weight=1)
        bar = ttk.Frame(self.preview)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.tabs = []
        for index, key in enumerate(("map", "1", "2")):
            button = ttk.Button(bar, name=f"dialogue_show_{key}", command=lambda value=index: self.show(value))
            button.pack(side="left", padx=(0, 5))
            self.tabs.append(button)
        self.enlarge = ttk.Button(bar, name="dialogue_enlarge", command=lambda: self.set_immersive(True))
        self.restore = ttk.Button(bar, name="dialogue_restore", command=lambda: self.set_immersive(False))
        self.label(self.enlarge, "放大", "Enlarge")
        self.label(self.restore, "返回", "Restore")
        help_button = guide_button(bar, "dialogue")
        if help_button is not None:
            help_button.pack(side="right", padx=(6, 0))
            help_button.bind("<Escape>", self.escape, add=True)
        self.enlarge.pack(side="right")

        self.stage = ttk.Frame(self.preview, style="A.Card.TFrame")
        self.stage.grid(row=1, column=0, sticky="nsew")
        self.art = ttk.Label(self.stage, name="dialogue_image", style="A.Card.TLabel")
        self.art.place(relx=.5, rely=.5, anchor="center")
        self.stage.bind("<Configure>", self.render)

        # Reuse the gallery's scrollable widget so fields remain accessible at Windows DPI scaling.
        from .action_preset_gallery import _ScrollingPane
        self.form = _ScrollingPane(body, "dialogue_form")
        self.form.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self.form.canvas.configure(width=295)
        content = self.form.content
        content.columnconfigure(1, weight=1)
        self.label(ttk.Label(content, font=self.title_font), "对应本组人物", "Map the cast").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(2, 3))
        self.role_widgets = {}
        for row, (role, variable) in enumerate(self.roles.items(), 1):
            tag = ttk.Label(content, text=role)
            tag.grid(row=row, column=0, sticky="w", padx=(0, 8))
            entry = ttk.Combobox(content, name=f"dialogue_role_{role.lower()}", textvariable=variable, width=16)
            entry.grid(row=row, column=1, sticky="ew", pady=2)
            self.role_widgets[role] = (tag, entry)
            variable.trace_add("write", self.mapping_changed)
            self.form.attach_scroll(tag)

        target_label = self.label(ttk.Label(content, font=self.title_font), "应用到", "Apply to")
        target_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 3))
        self.target = ttk.Combobox(content, name="dialogue_target", state="readonly", exportselection=False, width=21)
        self.target.grid(row=5, column=0, columnspan=2, sticky="ew")
        self.target.bind("<<ComboboxSelected>>", self.mapping_changed)
        self.summary = ttk.Label(content, name="dialogue_summary", justify="left", foreground=ACCENT)
        self.summary.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 3))
        self.caption = ttk.Label(content, anchor="w", justify="left")
        self.caption.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(3, 4))
        self.form.attach_scroll(target_label, self.summary, self.caption)
        self.form.canvas.bind("<Configure>", self.wrap_form, add=True)

        self.review = ttk.Frame(content, name="dialogue_review")
        self.review.grid(row=8, column=0, columnspan=2, sticky="ew")
        self.review.columnconfigure(0, weight=1)
        self.review.grid_remove()
        self.changes = ttk.Label(self.review, name="dialogue_changes", justify="left")
        self.changes.grid(row=0, column=0, sticky="ew", pady=(4, 0))
        self.form.attach_scroll(self.changes)

        self.footer = footer = ttk.Frame(self)
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        footer.columnconfigure(0, weight=1)
        self.error = ttk.Label(footer, name="dialogue_error", foreground=ACCENT, justify="left")
        self.error.grid(row=0, column=0, sticky="w")
        footer.bind("<Configure>", lambda event: self.error.configure(wraplength=max(120, event.width - 335)))
        self.review_button = self.label(ttk.Button(footer, name="dialogue_apply", command=self.review_changes,
                                                  style="Primary.Workbench.TButton"),
                                        "预览应用内容", "Preview changes")
        self.review_button.grid(row=0, column=2, sticky="e")
        self.confirm_button = self.label(ttk.Button(footer, name="dialogue_confirm", command=self.confirm,
                                                   style="Primary.Workbench.TButton"),
                                         "确认应用", "Apply")
        self.cancel_button = self.label(ttk.Button(footer, name="dialogue_cancel", command=self.reset_review),
                                        "返回选择", "Back to choices")
        for widget in (self.enlarge, self.restore, *self.tabs, *self.card_buttons.values()):
            widget.bind("<Escape>", self.escape, add=True)

    def wrap_form(self, event):
        width = max(120, event.width - 8)
        self.caption.configure(wraplength=width)
        self.summary.configure(wraplength=width)
        self.changes.configure(wraplength=width)

    def refresh_context(self):
        try:
            names, shots, *production = self.get_context()
        except (OSError, ValueError, RuntimeError) as error:
            self.context_error = str(error)
            self.reset_review()
            self.refresh_text()
            return
        self.context_error = ""
        self.error.configure(text="")
        if production:
            self.project_english = production[0]
        current = self.target.current()
        identity = self.shot_choices[current - 1][0] if 0 < current <= len(self.shot_choices) else ""
        self.shot_choices = tuple(shots)
        self.target.configure(values=(self.t("动作编排草稿", "Action sequence draft"), *(label for _, label in self.shot_choices)))
        target = next((index for index, (shot, _) in enumerate(self.shot_choices, 1) if shot == identity), 0)
        self.target.current(target)
        if identity and not target:
            self.reset_review()
        for _, widget in self.role_widgets.values():
            widget.configure(values=names)

    def set_language(self, english):
        self.english = int(english)
        for widget, captions in self.captions:
            widget.configure(text=captions[self.english])
        self.refresh_context()
        self.refresh_text()

    def select(self, card):
        self.card = card
        for role, widgets in self.role_widgets.items():
            for widget in widgets:
                widget.grid() if role in card.roles else widget.grid_remove()
        for identity, button in self.card_buttons.items():
            button.configure(style="A.Current.Step.TButton" if identity == card.id else "TButton")
        self.show(0)

    def show(self, index):
        self.index = index
        self.reset_review()
        self.refresh_text()
        self.render()

    def mapped_name(self, role):
        return self.roles[role].get().strip() or role

    def refresh_text(self):
        labels = (self.t("俯视站位", "Overhead map"), self.t("镜头 1", "Shot 1"), self.t("镜头 2", "Shot 2"))
        for index, tab in enumerate(self.tabs):
            tab.configure(text=labels[index], style="A.Current.Step.TButton" if index == self.index else "TButton")
        can_apply = self.index and not self.context_error and _load_art(self.card.id, self.index) is not None
        self.review_button.state(["!disabled"] if can_apply else ["disabled"])
        if not self.index:
            self.caption.configure(text=f"{self.card.title[self.english]} · {self.card.summary[self.english]}")
            self.summary.configure(text=self.t(
                "彩色箭头是视线，虚线标对话轴，紫色编号标机位。选镜头 1 或镜头 2 应用该机位。",
                "Colored arrows show eye lines. Dashed lines mark the dialogue axis. Purple numbers are cameras. Choose a shot to apply it.",
            ))
        else:
            view = self.card.views[self.index - 1]
            roles = {role: self.mapped_name(role) for role in self.card.roles}
            self.caption.configure(text=f"{view.title[self.english]} · {view.position[self.english].format_map(roles)}")
            speakers = self.mapped_name(view.speaker)
            listeners = "、".join(self.mapped_name(role) for role in view.listeners)
            self.summary.configure(text=self.t(f"说话者 {speakers} · 听者 {listeners}",
                                               f"Speaker {speakers} · Listeners {listeners}"))
        if self.confirmation is not None:
            self.show_changes()

    def render(self, _event=None):
        image = _load_art(self.card.id, self.index)
        if image is None:
            self.art.photo = None
            self.art.configure(image="", text=self.t("示意图不可用", "Illustration unavailable"))
            self.resampled = None
            return
        width = min(image.width, self.stage.winfo_width() - 10,
                    (self.stage.winfo_height() - 10) * image.width // image.height)
        if width < 2:
            return
        key = self.card.id, self.index, width
        if key != self.resampled:
            resized = image.resize((width, max(1, width * image.height // image.width)), Image.Resampling.LANCZOS)
            self.art.photo = ImageTk.PhotoImage(resized, master=self.art)
            self.art.configure(image=self.art.photo, text="")
            self.resampled = key

    def set_immersive(self, immersive):
        self.immersive = immersive
        if immersive:
            self.card_row.grid_remove()
            self.form.grid_remove()
            self.footer.grid_remove()
            self.enlarge.pack_forget()
            self.restore.pack(side="right")
            self.restore.focus_set()
        else:
            self.card_row.grid()
            self.form.grid()
            self.footer.grid()
            self.restore.pack_forget()
            self.enlarge.pack(side="right")
            self.enlarge.focus_set()

    def escape(self, _event):
        if self.immersive:
            self.set_immersive(False)
        else:
            self.on_back()
        return "break"

    def mapping_changed(self, *_args):
        self.reset_review()
        self.refresh_text()

    def reset_review(self):
        self.confirmation = None
        self.review.grid_remove()
        self.confirm_button.grid_remove()
        self.cancel_button.grid_remove()
        self.review_button.grid()
        self.error.configure(text=self.context_error)

    def review_changes(self):
        try:
            mapping = {role: self.roles[role].get().strip() for role in self.card.roles}
            target = self.target.current()
            identity = self.shot_choices[target - 1][0] if target > 0 else ""
            dialogue_fields(self.card.id, self.index, mapping, english=bool(self.english))
            self.confirmation = mapping, identity
            self.show_changes()
        except (IndexError, ValueError) as error:
            self.confirmation = None
            self.error.configure(text=str(error))
            return
        if self.immersive:
            self.set_immersive(False)
        self.review_button.grid_remove()
        self.cancel_button.grid(row=0, column=1, padx=(0, 6))
        self.confirm_button.grid(row=0, column=2, sticky="e")
        self.review.grid()
        self.confirm_button.focus_set()
        self.after_idle(self.reveal_changes)

    def reveal_changes(self):
        if self.confirmation is not None:
            self.form.update_scroll()
            self.form.canvas.yview_moveto(1)

    def show_changes(self):
        mapping, identity = self.confirmation
        fields = dialogue_fields(self.card.id, self.index, mapping, english=self.project_english)
        captions = ("景别", "机位/角度", "机位空间", "人物站位")
        labels = captions if not self.english else ("Shot scale", "Camera angle", "Camera position", "Blocking")
        rows = [f"{label}  {fields[key]}" for label, key in zip(labels, captions)]
        if identity:
            target = next(label for shot_id, label in self.shot_choices if shot_id == identity)
            rows.insert(0, self.t(f"写入 {target}", f"Update {target}"))
            rows.append(self.t("对白、原图与镜头顺序保留。", "Dialogue, assets and shot order stay intact."))
        else:
            rows.insert(0, self.t("创建 1 张动作卡草稿", "Create one draft action card"))
        self.changes.configure(text="\n".join(rows))

    def confirm(self):
        if self.confirmation is None:
            return
        mapping, identity = self.confirmation
        try:
            self.apply(self.card.id, self.index, mapping, identity)
        except (OSError, ValueError, RuntimeError, tk.TclError) as error:
            self.error.configure(text=str(error))
            return
        self.on_complete()
