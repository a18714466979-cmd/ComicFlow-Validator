"""Browse built-in action presets by illustration before adding one to a sequence."""

from collections.abc import Callable
from functools import lru_cache
import tkinter as tk
from tkinter import font, messagebox, ttk

from PIL import Image, ImageTk

from .action_card_catalog import ACTION_PRESETS, action_preview_path, get_preset
from .workbench_style import BACKGROUND, MUTED, SURFACE, configure_workbench


STAGES = (("起始", "Start"), ("关键变化", "Key beat"), ("结束", "End"))
STAGE_KEYS = ("start", "beat", "end")


@lru_cache(maxsize=18)
def _preview_frames(identity):
    path = action_preview_path(identity)
    if path is None:
        return ()
    try:
        with Image.open(path) as strip:
            if strip.width % len(STAGES) or strip.width < len(STAGES) or strip.height < 1:
                return ()
            width = strip.width // len(STAGES)
            return tuple(strip.crop((i * width, 0, (i + 1) * width, strip.height)).convert("RGB")
                         for i in range(len(STAGES)))
    except (OSError, ValueError):
        return ()


class _ScrollingPane(ttk.Frame):
    def __init__(self, parent, name, *, surface=BACKGROUND):
        super().__init__(parent, name=name)
        self.canvas = tk.Canvas(self, name="viewport", bg=surface, borderwidth=0, highlightthickness=0,
                                width=1, height=1, yscrollincrement=24)
        self.content = ttk.Frame(self.canvas, style="A.Card.TFrame" if surface == SURFACE else "TFrame")
        self.contents = self.canvas.create_window(0, 0, anchor="nw", window=self.content)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.bind("<Configure>", self.sized)
        self.content.bind("<Configure>", self.update_scroll)
        self.attach_scroll(self.canvas, self.content)

    def sized(self, event):
        self.canvas.itemconfigure(self.contents, width=event.width)

    def update_scroll(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def attach_scroll(self, *widgets):
        for widget in widgets:
            widget.bind("<MouseWheel>", self.scroll, add=True)
            widget.bind("<Button-4>", self.scroll, add=True)
            widget.bind("<Button-5>", self.scroll, add=True)

    def scroll(self, event):
        if event.num in (4, 5):
            units = -1 if event.num == 4 else 1
        else:
            units = -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(units * 2, "units")
        return "break"

    def reveal(self, widget):
        height = self.content.winfo_height()
        top = self.canvas.canvasy(0)
        bottom = top + self.canvas.winfo_height()
        start = widget.winfo_y()
        end = start + widget.winfo_height()
        if height > 1 and (start < top or end > bottom):
            target = start if start < top else end - self.canvas.winfo_height()
            self.canvas.yview_moveto(max(0, target) / height)


def open_action_presets(parent, *, english: bool, on_add: Callable[[str], None], initial_id: str = "") -> tk.Toplevel:
    """Open the modal preset browser and return its native window."""
    return _ActionPresetGallery(parent, english, on_add, initial_id).window


class _ActionPresetGallery:
    def __init__(self, parent, english, on_add, initial_id):
        self.locale = int(english)
        self.on_add = on_add
        self.previous_grab = parent.grab_current()
        self.selected = None
        self.visible = ()
        self.categories = tuple(dict.fromkeys(preset.category for preset in ACTION_PRESETS))
        self.covers = {}
        self.cover_images = {}
        self.stage_images = ()
        self.columns = 1
        self.tile_width = 0
        self.frame_width = 0
        self.refresh_job = None
        self.cover_job = None
        self.frame_job = None

        self.window = tk.Toplevel(parent, name="action_presets")
        configure_workbench(self.window)
        self.window.title(self.t("动作预设图库", "Action preset gallery"))
        self.window.geometry("1100x700")
        self.window.minsize(760, 520)
        self.window.transient(parent.winfo_toplevel())
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Destroy>", self.release)

        self.caption_font = font.nametofont("TkDefaultFont", root=self.window)
        self.title_font = self.caption_font.copy()
        size = self.title_font.cget("size")
        self.title_font.configure(size=size + (3 if size >= 0 else -3), weight="bold")

        self.build()
        initial = get_preset(initial_id)
        self.category.current(self.categories.index(initial.category) + 1 if initial else 0)
        self.filter(initial_id)
        self.window.grab_set()
        self.category.focus_set()

    def t(self, zh, en):
        return (zh, en)[self.locale]

    def build(self):
        view = ttk.Frame(self.window, padding=(16, 12))
        view.pack(fill="both", expand=True)
        filter_bar = ttk.Frame(view)
        filter_bar.pack(fill="x", pady=(0, 10))
        ttk.Label(filter_bar, text=self.t("类别", "Category")).pack(side="left", padx=(0, 8))
        values = (self.t("全部类别", "All categories"), *(category[self.locale] for category in self.categories))
        self.category = ttk.Combobox(filter_bar, name="preset_category", state="readonly", values=values,
                                     width=31, exportselection=False)
        self.category.pack(side="left")
        self.category.bind("<<ComboboxSelected>>", lambda _event: self.filter())
        self.count = ttk.Label(filter_bar, name="preset_count", foreground=MUTED)
        self.count.pack(side="left", padx=12)

        body = ttk.Frame(view)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=4, uniform="preset_browser")
        body.columnconfigure(1, weight=5, uniform="preset_browser")
        self.library = _ScrollingPane(body, "preset_library")
        self.library.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.library.canvas.bind("<Configure>", self.schedule_covers, add=True)
        self.preview = _ScrollingPane(body, "preset_detail", surface=SURFACE)
        self.preview.grid(row=0, column=1, sticky="nsew")
        self.preview.canvas.bind("<Configure>", self.schedule_frames, add=True)

        content = ttk.Frame(self.preview.content, padding=14, style="A.Card.TFrame")
        content.pack(fill="both", expand=True)
        self.title = ttk.Label(content, name="preset_title", font=self.title_font, style="A.Card.TLabel",
                               anchor="w", justify="left")
        self.title.pack(fill="x")
        self.metadata = ttk.Label(content, name="preset_metadata", style="A.CardMuted.TLabel", anchor="w",
                                  justify="left")
        self.metadata.pack(fill="x", pady=(2, 14))
        stages = ttk.Frame(content, style="A.Card.TFrame")
        stages.pack(fill="x")
        self.stage_widgets = []
        self.preview.attach_scroll(content, self.title, self.metadata, stages)
        for index, (key, caption) in enumerate(zip(STAGE_KEYS, STAGES)):
            stages.columnconfigure(index, weight=1, uniform="preset_stage")
            frame = ttk.Frame(stages, style="A.Card.TFrame")
            frame.grid(row=0, column=index, sticky="nsew", padx=(0, 7 if index < len(STAGES) - 1 else 0))
            heading = ttk.Label(frame, text=caption[self.locale], anchor="w", style="A.CardMuted.TLabel")
            heading.pack(fill="x", pady=(0, 4))
            image = ttk.Button(frame, name=f"frame_{key}", style="ActionPreview.TButton", compound="none",
                               command=lambda position=index: self.enlarge(position))
            image.pack(fill="x")
            image.bind("<Return>", lambda _event, position=index: self.enlarge(position))
            self.stage_widgets.append(image)
            self.preview.attach_scroll(frame, heading, image)
        ttk.Style(self.window).configure("ActionPreview.TButton", padding=2)

        self.description = ttk.Label(content, name="preset_movement", style="A.Card.TLabel", anchor="nw",
                                     justify="left")
        self.description.pack(fill="x", pady=(14, 0))
        self.preview.attach_scroll(self.description)

        footer = ttk.Frame(view)
        footer.pack(side="bottom", before=body, fill="x", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, name="close_preset", text=self.t("关闭", "Close"), command=self.close,
                   style="Workbench.TButton").grid(row=0, column=1, padx=(0, 8))
        self.add_button = ttk.Button(footer, name="add_preset", text=self.t("加入动作编排", "Add to sequence"),
                                     style="Primary.Workbench.TButton", command=self.add)
        self.add_button.grid(row=0, column=2)

    def filter(self, preferred=""):
        if self.cover_job is not None:
            self.window.after_cancel(self.cover_job)
            self.cover_job = None
        category_index = self.category.current()
        category = self.categories[category_index - 1] if category_index > 0 else None
        self.visible = tuple(preset for preset in ACTION_PRESETS if category is None or preset.category == category)
        for button in self.covers.values():
            button.destroy()
        self.covers.clear()
        self.cover_images.clear()
        for index, preset in enumerate(self.visible):
            button = ttk.Button(self.library.content, name=f"cover_{preset.id}", compound="top",
                                style="Workbench.TButton", takefocus=True,
                                command=lambda item=preset: self.select(item))
            button.bind("<Return>", lambda _event, item=preset: self.select(item))
            button.bind("<FocusIn>", lambda _event, item=button: self.library.reveal(item))
            for direction in ("Left", "Right", "Up", "Down"):
                button.bind(f"<{direction}>", lambda _event, step=direction, i=index: self.move(i, step))
            self.library.attach_scroll(button)
            self.covers[preset.id] = button
        count = len(self.visible)
        self.count.configure(text=self.t(f"{count} 张预设", f"{count} preset" if count == 1 else f"{count} presets"))
        selected_id = preferred or (self.selected.id if self.selected else "")
        item = next((card for card in self.visible if card.id == selected_id), self.visible[0] if self.visible else None)
        self.tile_width = 0
        self.library.canvas.yview_moveto(0)
        self.select(item)
        self.schedule_covers()

    def select(self, item):
        if self.selected and self.selected.id in self.covers:
            self.covers[self.selected.id].configure(style="Workbench.TButton")
        self.selected = item
        if item:
            self.covers[item.id].configure(style="A.Current.Step.TButton")
            self.title.configure(text=item.title[self.locale])
            details = " · ".join(value for value in (item.category[self.locale], item.prop[self.locale]) if value)
            self.metadata.configure(text=details)
            self.description.configure(text=item.movement[self.locale])
        self.add_button.state(["!disabled"] if item else ["disabled"])
        self.frame_width = 0
        self.preview.canvas.yview_moveto(0)
        self.schedule_frames()

    def move(self, index, direction):
        step = {"Left": -1, "Right": 1, "Up": -self.columns, "Down": self.columns}[direction]
        target = min(max(index + step, 0), len(self.visible) - 1)
        item = self.visible[target]
        self.select(item)
        self.covers[item.id].focus_set()
        return "break"

    def schedule_covers(self, _event=None):
        if self.refresh_job is None:
            self.refresh_job = self.window.after_idle(self.layout_covers)

    def layout_covers(self):
        self.refresh_job = None
        width = max(self.library.canvas.winfo_width() - 3, 120)
        columns = 3 if width >= 520 else 2 if width >= 280 else 1
        tile_width = min(220, (width + 8) // columns - 8)
        if self.tile_width == tile_width and self.columns == columns:
            return
        self.tile_width, self.columns = tile_width, columns
        if self.cover_job is not None:
            self.window.after_cancel(self.cover_job)
            self.cover_job = None
        for index, preset in enumerate(self.visible):
            row, column = divmod(index, columns)
            button = self.covers[preset.id]
            button.configure(text=self.cover_caption(preset.title[self.locale], tile_width - 24))
            button.grid(row=row, column=column, sticky="nsew", padx=(0, 8 if column < columns - 1 else 0),
                        pady=(0, 8))
        self.load_covers(iter(self.visible))

    def cover_caption(self, title, width):
        lines = []
        for part in title.split() if self.locale else title:
            glue = " " if self.locale else ""
            joined = f"{lines[-1]}{glue}{part}" if lines else part
            if lines and self.caption_font.measure(joined) <= width:
                lines[-1] = joined
            else:
                lines.append(part)
        display = lines[:2]
        for index, line in enumerate(display):
            tail = "…" if index == 1 and len(lines) > 2 else ""
            while line and self.caption_font.measure(line + tail) > width:
                line = line[:-1]
                tail = "…"
            display[index] = line + tail
        return "\n".join(display + [""] * (2 - len(display)))

    def load_covers(self, iterator):
        self.cover_job = None
        # Limit work per Tk callback so navigating the full catalog stays responsive.
        for _index in range(5):
            preset = next(iterator, None)
            if preset is None:
                return
            frames = _preview_frames(preset.id)
            if frames:
                image = self.photo(frames[1], max(72, self.tile_width - 24), self.library.canvas)
                self.cover_images[preset.id] = image
                self.covers[preset.id].configure(image=image)
        self.cover_job = self.window.after(8, self.load_covers, iterator)

    @staticmethod
    def photo(image, width, master):
        size = width, max(1, round(width * image.height / image.width))
        return ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS), master=master)

    def schedule_frames(self, _event=None):
        if self.frame_job is None:
            self.frame_job = self.window.after_idle(self.render_frames)

    def render_frames(self):
        self.frame_job = None
        width = max(100, self.preview.canvas.winfo_width() - 30)
        for label in (self.title, self.metadata, self.description):
            label.configure(wraplength=width)
        frame_width = min(320, max(24, (width - 30) // len(STAGES)))
        if self.frame_width == frame_width:
            return
        self.frame_width = frame_width
        frames = _preview_frames(self.selected.id) if self.selected else ()
        self.stage_images = tuple(self.photo(image, frame_width, self.preview.canvas) for image in frames)
        for index, button in enumerate(self.stage_widgets):
            image = self.stage_images[index] if frames else ""
            caption = STAGES[index][self.locale] if image else self.t("预览缺失", "Unavailable")
            button.configure(image=image, text=caption, state="normal" if image else "disabled")

    def enlarge(self, position):
        frames = _preview_frames(self.selected.id) if self.selected else ()
        if not frames:
            return "break"
        title = f"{self.selected.title[self.locale]} · {STAGES[position][self.locale]}"
        window = tk.Toplevel(self.window, name="enlarged_action_frame", bg=BACKGROUND)
        window.title(title)
        window.transient(self.window)
        width = min(640, max(300, window.winfo_screenwidth() - 64), max(300, (window.winfo_screenheight() - 140) * 4 // 3))
        box = ttk.Frame(window, padding=12)
        box.pack(fill="both", expand=True)
        art = self.photo(frames[position], width, window)
        label = ttk.Label(box, image=art)
        label.image = art
        label.pack()

        def close_preview():
            window.destroy()
            if self.window.winfo_exists():
                self.window.grab_set()
                self.stage_widgets[position].focus_set()

        close = ttk.Button(box, text=self.t("关闭", "Close"), command=close_preview, style="Workbench.TButton")
        close.pack(anchor="e", pady=(10, 0))
        window.protocol("WM_DELETE_WINDOW", close_preview)
        window.bind("<Escape>", lambda _event: close_preview())
        window.grab_set()
        close.focus_set()
        return "break"

    def add(self):
        if self.selected:
            try:
                self.on_add(self.selected.id)
            except (OSError, ValueError, RuntimeError, tk.TclError) as error:
                messagebox.showerror(self.window.title(), str(error), parent=self.window)
                return
            self.close()

    def close(self):
        self.window.destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()

    def release(self, event):
        if event.widget is self.window:
            for job in (self.refresh_job, self.cover_job, self.frame_job):
                if job is not None:
                    self.window.after_cancel(job)
            self.cover_images.clear()
            self.stage_images = ()
