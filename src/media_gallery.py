"""Local media contact sheet, classification and uncropped previews."""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk

from PIL import Image, ImageTk

from .guide_links import guide_button
from .media_catalog import MEDIA_FILTER
from .media_preview import iter_video_frames, load_preview
from .workbench_style import ACCENT, BACKGROUND, INK, LINE, MUTED, SUBTLE, SURFACE, TINT


CATEGORIES = {
    "scene": ("场景", "Scenes"),
    "character": ("人物", "Characters"),
    "prop": ("道具", "Props"),
    "unclassified": ("待分类", "Unclassified"),
    "product": ("产品", "Products"),
    "storyboard": ("故事板", "Storyboards"),
    "clean_plate": ("净板", "Clean plates"),
    "motion_reference": ("动作参考", "Motion reference"),
}
KINDS = {"image": ("图片", "Images"), "video": ("视频", "Videos")}
SIZES = {144: ("小", "Small"), 200: ("中", "Medium"), 256: ("大", "Large")}
GAP = 12
CACHE_LIMIT = 96


def _close_popup(window, previous_grab):
    # The calling workflows commonly hold their own local modal grab.
    window.destroy()
    if previous_grab is not None and previous_grab.winfo_exists():
        previous_grab.grab_set()


def _media_error(error, english):
    if isinstance(error, FileNotFoundError):
        return "File unavailable. Check its location." if english else "找不到源文件，请检查文件位置。"
    value = str(error)
    if " / " in value:
        zh, en = value.split(" / ", 1)
        return en if english else zh
    return value


def _time(milliseconds):
    minutes, remainder = divmod(max(0, milliseconds), 60_000)
    seconds, fraction = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{fraction // 100}"


def open_media_gallery(parent, items, *, catalog=None, on_select=None, selected=(), allow_import=False,
                       title=None, on_change=None, native_only=False, select_types=None, open_selected=False,
                       mount=None, on_close=None):
    """Open a contact sheet in a workflow page or its own modal window."""
    gallery = MediaGallery(parent, items, catalog, on_select, selected, allow_import, title,
                           on_change, native_only, select_types, mount, on_close)
    if open_selected and gallery.active():
        gallery.direct_preview = mount is not None
        gallery.preview_timer = gallery.window.after_idle(gallery.preview)
    return gallery.window


class MediaGallery:
    def __init__(self, parent, items, catalog, on_select, selected, allow_import, title,
                 on_change, native_only, select_types, mount, on_close):
        self.english = getattr(parent._root(), "ui_language", "zh") == "en"
        self.catalog = catalog
        self.native = tuple(items)
        self.native_keys = {item.key for item in self.native}
        self.native_only = native_only
        self.select_types = frozenset(select_types) if select_types is not None else None
        self.on_select = on_select
        self.on_change = on_change
        self.on_close = on_close
        self.embedded = mount is not None
        self.selected = dict.fromkeys(selected)
        self.cursor = None
        self.items = ()
        self.filtered = ()
        self.categories = ()
        self.poster_times = {}
        self.card_size = 200
        self.columns = 1
        self.thumb_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="media-thumb")
        self.work_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="media-library")
        self.pending = {}
        self.cache = OrderedDict()
        self.photos = {}
        self.operation = None
        self.operation_stop = None
        self.import_count = 0
        self.draw_timer = None
        self.poll_timer = None
        self.preview_timer = None
        self.detail = None
        self.direct_preview = False
        self.old_grab = parent.grab_current() if not self.embedded else None
        self.title = title or self.t("素材图库", "Media library")
        if self.embedded:
            self.window = ttk.Frame(mount, name="media_gallery")
            self.window.pack(fill="both", expand=True)
        else:
            self.window = tk.Toplevel(parent, name="media_gallery", bg=BACKGROUND)
            self.window.title(self.title)
            self.window.transient(parent.winfo_toplevel())
            self.window.geometry("950x660")
            self.window.minsize(680, 480)
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Destroy>", self.destroyed)
        self.build(allow_import and catalog is not None and not native_only)
        try:
            self.refresh()
        except (OSError, ValueError):
            self.window.destroy()
            raise
        if not self.embedded:
            self.window.grab_set()
        self.canvas.focus_set()

    def t(self, zh, en):
        return en if self.english else zh

    def build(self, can_import):
        body = ttk.Frame(self.window, padding=(16, 14))
        self.body = body
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(body)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.columnconfigure((0, 1, 2), weight=1, uniform="media_filters")
        self.category_filter = self.filter_control(toolbar, 0, "media_category", self.t("类别", "Category"))
        self.kind_filter = self.filter_control(toolbar, 1, "media_kind", self.t("媒体", "Media type"))
        self.size_filter = self.filter_control(toolbar, 2, "media_size", self.t("卡片大小", "Card size"))
        self.kind_filter.configure(values=(self.t("全部媒体", "All media"), *(self.t(*n) for n in KINDS.values())))
        self.kind_filter.current(0)
        self.size_filter.configure(values=tuple(self.t(*name) for name in SIZES.values()))
        self.size_filter.current(1)
        self.import_button = None
        if can_import:
            self.import_button = ttk.Button(toolbar, name="media_import", text=self.t("导入素材", "Import media"),
                                            command=self.import_media, style="Workbench.TButton")
            self.import_button.grid(row=1, column=3, sticky="e")

        sheet = ttk.Frame(body)
        sheet.grid(row=1, column=0, sticky="nsew")
        sheet.columnconfigure(0, weight=1)
        sheet.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(sheet, name="media_cards", bg=BACKGROUND, relief="flat", borderwidth=0,
                                highlightbackground=LINE, highlightcolor=ACCENT, highlightthickness=1,
                                takefocus=True, yscrollincrement=28)
        self.scroll = ttk.Scrollbar(sheet, orient="vertical", command=self.scroll_by)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.bind("<Configure>", lambda _event: self.schedule_draw())
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Double-Button-1>", self.double_click)
        self.canvas.bind("<MouseWheel>", self.mousewheel)
        self.canvas.bind("<Button-4>", lambda _event: self.scroll_by("scroll", -3, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.scroll_by("scroll", 3, "units"))
        self.canvas.bind("<Return>", lambda _event: self.preview())
        if self.embedded:
            self.canvas.bind("<Escape>", lambda _event: self.close())
        self.canvas.bind("<space>", self.select_focused)
        self.canvas.bind("<FocusIn>", lambda _event: self.schedule_draw())
        self.canvas.bind("<FocusOut>", lambda _event: self.schedule_draw())
        for key, delta in (("Left", -1), ("Right", 1), ("Up", "up"), ("Down", "down")):
            self.canvas.bind(f"<{key}>", lambda _event, move=delta: self.move_focus(move))
        for key, direction in (("Prior", -1), ("Next", 1)):
            self.canvas.bind(f"<{key}>", lambda _event, step=direction: self.scroll_by("scroll", step, "pages"))
        self.caption_font = font.nametofont("TkDefaultFont", root=self.window)

        footer = ttk.Frame(body)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        self.status = tk.StringVar(self.window)
        ttk.Label(footer, name="media_status", textvariable=self.status, foreground=MUTED).grid(
            row=0, column=0, sticky="w", pady=(0, 7))
        self.cancel = ttk.Button(footer, name="media_cancel", text=self.t("取消导入", "Cancel import"),
                                 command=self.cancel_operation, style="Workbench.TButton")
        self.cancel.grid(row=0, column=1, sticky="e", pady=(0, 7))
        self.cancel.grid_remove()

        edit = ttk.Frame(footer)
        edit.grid(row=1, column=0, sticky="w")
        self.category_edit = None
        self.apply = None
        if self.catalog is not None:
            self.category_edit = ttk.Combobox(edit, name="media_assign_category", state="readonly", width=14,
                                               values=tuple(self.t(*n) for n in CATEGORIES.values()))
            self.category_edit.current(3)
            self.category_edit.pack(side="left", padx=(0, 6))
            self.apply = ttk.Button(edit, name="media_apply_category", text=self.t("设置类别", "Set category"),
                                    command=self.apply_category, style="Workbench.TButton")
            self.apply.pack(side="left")
        actions = ttk.Frame(footer)
        actions.grid(row=2, column=0, columnspan=2, sticky="e", pady=(5, 0))
        self.preview_button = ttk.Button(actions, name="media_preview", text=self.t("查看大图／视频", "Open preview"),
                                         command=self.preview, style="Workbench.TButton")
        self.preview_button.pack(side="left", padx=(0, 6))
        self.choose_button = None
        if self.on_select is not None:
            self.choose_button = ttk.Button(actions, name="media_choose", text=self.t("使用所选素材", "Use selection"),
                                            command=self.choose, style="Primary.Workbench.TButton")
            self.choose_button.pack(side="left")
        if self.on_select is None or self.embedded:
            caption = self.t("返回", "Back") if self.embedded else self.t("关闭", "Close")
            ttk.Button(actions, name="media_close", text=caption, command=self.close,
                       style="Workbench.TButton").pack(side="left")
        help_button = guide_button(actions, "media")
        if help_button is not None:
            help_button.pack(side="left", padx=(6, 0))

    def filter_control(self, parent, column, name, caption):
        ttk.Label(parent, text=caption, foreground=MUTED).grid(row=0, column=column, sticky="w")
        widget = ttk.Combobox(parent, name=name, state="readonly", width=11)
        widget.grid(row=1, column=column, sticky="ew", padx=(0, 10), pady=(3, 0))
        widget.bind("<<ComboboxSelected>>", lambda _event: self.filter())
        return widget

    def refresh(self, focus=None):
        self.items = self.catalog.items(self.native) if self.catalog is not None else self.native
        self.poster_times = self.catalog.poster_times() if self.catalog is not None else {}
        if self.native_only:
            self.items = tuple(item for item in self.items if item.key in self.native_keys)
        keys = {item.key for item in self.items}
        self.selected = {key: None for key in self.selected if key in keys}
        old_category = self.current_category()
        seen = {item.category for item in self.items}
        self.categories = (None, *(key for index, key in enumerate(CATEGORIES) if index < 4 or key in seen))
        self.category_filter.configure(values=(
            self.t("全部类别", "All categories"), *(self.t(*CATEGORIES[key]) for key in self.categories[1:])
        ))
        self.category_filter.current(self.categories.index(old_category) if old_category in self.categories else 0)
        self.filter(focus=focus)

    def current_category(self):
        index = self.category_filter.current()
        return self.categories[index] if 0 <= index < len(self.categories) else None

    def filter(self, *, focus=None):
        category = self.current_category()
        index = self.kind_filter.current()
        kind = tuple(KINDS)[index - 1] if index > 0 else None
        size = self.size_filter.current()
        if size >= 0:
            self.card_size = tuple(SIZES)[size]
        self.filtered = tuple(item for item in self.items
                              if (category is None or item.category == category)
                              and (kind is None or item.media_type == kind))
        selected_key = focus if focus is not None else self.cursor
        if selected_key is None or all(item.key != selected_key for item in self.filtered):
            selected_key = next((item.key for item in self.filtered if item.key in self.selected),
                                self.filtered[0].key if self.filtered else None)
        self.cursor = selected_key
        self.canvas.yview_moveto(0)
        self.update_status()
        self.schedule_draw()

    def active(self):
        return next((item for item in self.filtered if item.key == self.cursor), None)

    def current_selected(self):
        by_key = {item.key: item for item in self.items}
        return tuple(by_key[key] for key in self.selected if key in by_key)

    def selectable(self, item):
        return self.select_types is None or item.media_type in self.select_types

    def update_status(self, notice=""):
        n = len(self.selected)
        total = len(self.filtered)
        if self.operation is None:
            if not notice:
                cue = self.t("点击查看，Ctrl+点击或空格多选。", "Click to select. Ctrl+click or Space selects multiple.")
                notice = self.t(f"{total} 项 · 已选 {n}　{cue}", f"{total} items · {n} selected. {cue}")
            self.status.set(notice)
        self.preview_button.configure(state="normal" if self.active() else "disabled")
        if self.choose_button is not None:
            self.choose_button.configure(state="normal" if any(map(self.selectable, self.current_selected())) else "disabled")
        if self.apply is not None:
            self.apply.configure(state="normal" if n and self.operation is None else "disabled")

    def schedule_draw(self):
        if self.draw_timer is None:
            self.draw_timer = self.window.after_idle(self.draw)

    @property
    def row_height(self):
        return self.card_size + 2 * self.caption_font.metrics("linespace") + 21

    def card_dimensions(self):
        step = self.card_size + GAP
        self.columns = max(1, (self.canvas.winfo_width() - GAP) // step)
        rows = (len(self.filtered) + self.columns - 1) // self.columns
        total_height = GAP + rows * (self.row_height + GAP)
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), total_height))

    def drawing_key(self, item):
        poster = self.poster_times.get(item.key) if item.media_type == "video" else None
        return item.key, item.path, self.card_size, poster

    def draw(self):
        self.draw_timer = None
        canvas = self.canvas
        self.card_dimensions()
        canvas.delete("all")
        stride = self.row_height + GAP
        top = max(0, int(canvas.canvasy(0)))
        first = (max(0, top - GAP) // stride) * self.columns
        last = min(len(self.filtered), ((top + canvas.winfo_height()) // stride + 2) * self.columns)
        wanted = {self.drawing_key(item): item for item in self.filtered[first:last]}
        self.photos = {key: image for key, image in self.photos.items() if key in wanted}
        for key, future in list(self.pending.items()):
            if key not in wanted and future.cancel():
                self.pending.pop(key)
        if not self.filtered:
            canvas.create_text(18, 22, anchor="nw", fill=MUTED, text=self.t(
                "这里没有符合筛选条件的素材。", "No media matches these filters."))
        for index in range(first, last):
            item = self.filtered[index]
            self.paint_card(index, item)
        for key, item in wanted.items():
            if key not in self.pending and key not in self.cache:
                self.pending[key] = self.thumb_pool.submit(load_preview, item, key[2] - 12, key[3])
        if self.pending or self.operation is not None:
            self.schedule_poll()

    def ellipsis(self, value, width):
        if self.caption_font.measure(value) <= width:
            return value
        low, high = 0, len(value)
        while low < high:
            middle = (low + high + 1) // 2
            if self.caption_font.measure(value[:middle] + "…") <= width:
                low = middle
            else:
                high = middle - 1
        return value[:low] + "…"

    def paint_card(self, index, item):
        row, column = divmod(index, self.columns)
        x = GAP + column * (self.card_size + GAP)
        y = GAP + row * (self.row_height + GAP)
        end = x + self.card_size
        active = item.key == self.cursor and self.window.focus_get() == self.canvas
        selected = item.key in self.selected
        tags = ("media-card", f"index:{index}")
        self.canvas.create_rectangle(x, y, end, y + self.row_height, fill=TINT if selected else SURFACE,
                                     outline=ACCENT if selected or active else LINE, width=2 if active else 1, tags=tags)
        self.canvas.create_rectangle(x, y, end, y + self.card_size, fill=SUBTLE,
                                     outline=ACCENT if selected or active else LINE, tags=(*tags, "square"))
        key = self.drawing_key(item)
        preview = self.cache.get(key)
        video = item.media_type == "video"
        if preview is not None and not isinstance(preview, Exception):
            self.cache.move_to_end(key)
            photo = self.photos.get(key)
            if photo is None:
                photo = self.photos[key] = ImageTk.PhotoImage(preview.image, master=self.canvas)
            self.canvas.create_image(x + self.card_size // 2, y + self.card_size // 2, image=photo,
                                     tags=(*tags, "media-item-photo"))
        else:
            text = (self.t("无法预览", "Preview unavailable") if isinstance(preview, Exception)
                    else self.t("正在预览…", "Loading preview…"))
            self.canvas.create_text(x + self.card_size // 2, y + self.card_size // 2, text=text, fill=MUTED, tags=tags)
        if video:
            duration = f"▶  {_time(preview.duration_ms)}" if preview and not isinstance(preview, Exception) else "▶"
            width = self.caption_font.measure(duration) + 14
            bottom = y + self.card_size - 7
            self.canvas.create_rectangle(x + 7, bottom - 24, x + 7 + width, bottom,
                                         fill=INK, outline=INK, tags=tags)
            self.canvas.create_text(x + 14, bottom - 12, anchor="w", text=duration, fill="white", tags=tags)
        if selected:
            self.canvas.create_rectangle(end - 26, y + 7, end - 7, y + 26, fill=ACCENT, outline=ACCENT, tags=tags)
            self.canvas.create_text(end - 17, y + 16, text="✓", fill="white", tags=tags)
        metadata = [self.t(*CATEGORIES.get(item.category, CATEGORIES["unclassified"]))]
        if video:
            metadata += [self.t("视频", "Video")]
            if preview and not isinstance(preview, Exception):
                metadata += [_time(preview.duration_ms)]
        if item.purpose:
            metadata += [item.purpose]
        caption = getattr(item, "display_name", None) or getattr(item, "name", None) or item.path.name
        line = self.caption_font.metrics("linespace")
        self.canvas.create_text(x + 8, y + self.card_size + 6, anchor="nw", fill=INK, tags=tags,
                                text=self.ellipsis(caption, self.card_size - 16))
        self.canvas.create_text(x + 8, y + self.card_size + 9 + line, anchor="nw", fill=MUTED, tags=tags,
                                text=self.ellipsis(" · ".join(metadata), self.card_size - 16))

    def schedule_poll(self):
        if self.poll_timer is None:
            self.poll_timer = self.window.after(35, self.poll)

    def poll(self):
        self.poll_timer = None
        changed = False
        for key, future in list(self.pending.items()):
            if future.done():
                self.pending.pop(key)
                try:
                    self.cache[key] = future.result()
                except Exception as error:
                    self.cache[key] = error
                changed = True
        while len(self.cache) > CACHE_LIMIT:
            self.cache.popitem(last=False)
        if changed:
            self.schedule_draw()
        if self.operation is not None and self.operation.done():
            job, self.operation = self.operation, None
            cancelled = self.operation_stop is not None and self.operation_stop.is_set()
            imported_count, self.import_count = self.import_count, 0
            self.operation_stop = None
            self.cancel.grid_remove()
            if self.import_button is not None:
                self.import_button.configure(state="normal")
            try:
                imported = job.result()
                if imported:
                    self.kind_filter.current(0)
                self.refresh(focus=imported[0].key if imported else None)
            except (OSError, ValueError) as error:
                self.update_status(self.t("操作未保存。", "Changes could not be saved."))
                messagebox.showerror(self.title, _media_error(error, self.english), parent=self.window)
            else:
                if cancelled and not imported:
                    self.update_status(self.t("已取消导入。", "Import cancelled."))
                elif imported_count:
                    count = len(imported or ())
                    self.update_status(self.t(f"已读入 {count}/{imported_count} 项素材。",
                                              f"Read {count} of {imported_count} files."))
                    if not count:
                        self.update_status(self.t("未读入素材。请检查文件位置和格式。",
                                                  "No files imported. Check their locations and formats."))
                if self.on_change is not None and (imported or not imported_count):
                    self.on_change()
        if self.pending or self.operation is not None:
            self.schedule_poll()

    def item_at(self, event):
        x = int(self.canvas.canvasx(event.x)) - GAP
        y = int(self.canvas.canvasy(event.y)) - GAP
        if x < 0 or y < 0:
            return None
        column, offset_x = divmod(x, self.card_size + GAP)
        row, offset_y = divmod(y, self.row_height + GAP)
        index = row * self.columns + column
        if offset_x < self.card_size and offset_y < self.row_height and column < self.columns and index < len(self.filtered):
            return self.filtered[index]
        return None

    def click(self, event):
        self.canvas.focus_set()
        item = self.item_at(event)
        if item is not None:
            self.select(item, toggle=bool(event.state & 0x0004))

    def double_click(self, event):
        item = self.item_at(event)
        if item is not None:
            self.cursor = item.key
            self.preview()

    def select_focused(self, _event):
        item = self.active()
        if item is not None:
            self.select(item, toggle=True)
        return "break"

    def select(self, item, *, toggle=False):
        self.cursor = item.key
        if self.selectable(item):
            if toggle and item.key in self.selected:
                self.selected.pop(item.key)
            elif toggle:
                self.selected[item.key] = None
            else:
                self.selected = {item.key: None}
        self.update_status()
        self.schedule_draw()

    def move_focus(self, direction):
        if self.filtered:
            current = next((i for i, item in enumerate(self.filtered) if item.key == self.cursor), 0)
            direction = {"up": -self.columns, "down": self.columns}.get(direction, direction)
            index = max(0, min(len(self.filtered) - 1, current + direction))
            self.cursor = self.filtered[index].key
            stride = self.row_height + GAP
            y = GAP + index // self.columns * stride
            top = self.canvas.canvasy(0)
            height = self.canvas.winfo_height()
            if y < top or y + self.row_height > top + height:
                content = GAP + ((len(self.filtered) + self.columns - 1) // self.columns) * stride
                target = y if y < top else y + stride - height
                self.canvas.yview_moveto(target / max(1, content))
            self.update_status()
            self.schedule_draw()
        return "break"

    def scroll_by(self, *args):
        self.canvas.yview(*args)
        self.schedule_draw()
        return "break"

    def mousewheel(self, event):
        if event.delta:
            amount = max(1, abs(event.delta) // 120)
            return self.scroll_by("scroll", (amount if event.delta < 0 else -amount) * 3, "units")

    def import_media(self):
        files = filedialog.askopenfilenames(parent=self.window, title=self.t("导入素材", "Import media"),
                                            filetypes=((self.t("图片和视频", "Images and videos"), MEDIA_FILTER),))
        if not files:
            return
        self.import_count = len(files)
        self.operation_stop = Event()
        self.cancel.configure(state="normal")
        self.cancel.grid()
        category = self.current_category() or "unclassified"
        self.start_operation(
            self.work_pool.submit(self.catalog.import_paths, tuple(map(Path, files)), category, stop=self.operation_stop),
            self.t(f"正在导入 {len(files)} 项…", f"Importing {len(files)} items…"),
        )

    def apply_category(self):
        index = self.category_edit.current()
        if index >= 0 and self.selected:
            category = tuple(CATEGORIES)[index]
            keys = tuple(self.selected)
            self.start_operation(self.work_pool.submit(self.catalog.categorize, keys, category),
                                 self.t("正在保存类别…", "Saving categories…"))

    def start_operation(self, operation, caption):
        self.operation = operation
        self.status.set(caption)
        if self.import_button is not None:
            self.import_button.configure(state="disabled")
        self.update_status()
        self.schedule_poll()

    def cancel_operation(self):
        if self.operation_stop is not None:
            self.operation_stop.set()
            self.cancel.configure(state="disabled")
            self.status.set(self.t("正在取消…", "Cancelling…"))

    def preview(self):
        self.preview_timer = None
        if self.active() is not None and self.detail is None:
            detail = MediaDetail(self, self.filtered, self.cursor)
            if self.embedded:
                self.detail = detail
                self.body.pack_forget()
                detail.window.pack(fill="both", expand=True)
                detail.canvas.focus_set()

    def back_from_detail(self):
        self.detail = None
        if self.direct_preview:
            self.close()
        else:
            self.body.pack(fill="both", expand=True)
            self.canvas.focus_set()

    def choose(self):
        selection = tuple(item for item in self.current_selected() if self.selectable(item))
        if selection:
            try:
                self.on_select(selection)
            except (OSError, ValueError) as error:
                messagebox.showerror(self.title, _media_error(error, self.english), parent=self.window)
                return
            self.close()

    def close(self):
        _close_popup(self.window, self.old_grab)
        if self.on_close is not None:
            self.on_close()

    def destroyed(self, event):
        if event.widget == self.window:
            for timer in (self.draw_timer, self.poll_timer, self.preview_timer):
                if timer is not None:
                    self.window.after_cancel(timer)
            if self.operation_stop is not None:
                self.operation_stop.set()
            self.thumb_pool.shutdown(wait=False, cancel_futures=True)
            self.work_pool.shutdown(wait=False, cancel_futures=True)
            # Release Tcl-owned resources here on the UI thread. A decode worker
            # can trigger Python's cyclic collector after these widgets close.
            self.photos.clear()
            self.status = None


class MediaDetail:
    """Fullscreen-sized inspection with a local silent video transport."""

    def __init__(self, gallery, items, key):
        self.gallery = gallery
        self.items = items
        self.index = next(i for i, item in enumerate(items) if item.key == key)
        self.old_grab = gallery.window.grab_current() if not gallery.embedded else None
        if gallery.embedded:
            self.window = ttk.Frame(gallery.window, name="media_detail")
        else:
            self.window = tk.Toplevel(gallery.window, name="media_detail", bg=BACKGROUND)
            self.window.transient(gallery.window)
            self.window.geometry("880x660")
            self.window.minsize(620, 460)
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            self.window.bind("<Escape>", lambda _event: self.close())
        self.window.bind("<Destroy>", self.destroyed)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="media-detail")
        self.future = None
        self.poll_timer = None
        self.paint_timer = None
        self.seek_timer = None
        self.stop = None
        self.frames = None
        self.frame = None
        self.duration_ms = 0
        self.current_ms = 0
        self.zoom = 1
        self.photo = None
        self.setting_scale = False
        self.build()
        self.load()
        if not gallery.embedded:
            self.window.grab_set()
        self.canvas.focus_set()

    @property
    def item(self):
        return self.items[self.index]

    @property
    def video(self):
        return self.item.media_type == "video"

    def t(self, zh, en):
        return self.gallery.t(zh, en)

    def build(self):
        body = ttk.Frame(self.window, padding=(16, 13))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        self.name = ttk.Label(body, font=("TkDefaultFont", 14, "bold"))
        self.name.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        self.source = ttk.Label(body, foreground=MUTED, justify="left")
        self.source.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        body.bind("<Configure>", lambda event: self.resize_header(event.width))

        view = ttk.Frame(body)
        view.grid(row=2, column=0, sticky="nsew")
        view.columnconfigure(0, weight=1)
        view.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(view, name="media_detail_preview", bg="#262321", takefocus=True,
                                borderwidth=0, highlightthickness=1, highlightbackground=LINE,
                                highlightcolor=ACCENT)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical = ttk.Scrollbar(view, command=self.canvas.yview)
        self.horizontal = ttk.Scrollbar(view, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.horizontal.set, yscrollcommand=self.vertical.set)
        self.canvas.bind("<Configure>", self.schedule_paint)
        self.canvas.bind("<ButtonPress-1>", lambda event: self.canvas.scan_mark(event.x, event.y))
        self.canvas.bind("<B1-Motion>", self.pan)
        self.canvas.bind("<Control-MouseWheel>", lambda event: self.enlarge(1.25 if event.delta > 0 else 0.8))
        self.canvas.bind("<Control-Button-4>", lambda _event: self.enlarge(1.25))
        self.canvas.bind("<Control-Button-5>", lambda _event: self.enlarge(0.8))
        self.canvas.bind("<Left>", lambda _event: self.navigate(-1))
        self.canvas.bind("<Right>", lambda _event: self.navigate(1))
        self.canvas.bind("<space>", lambda _event: self.toggle_play())
        self.canvas.bind("<plus>", lambda _event: self.enlarge(1.25))
        self.canvas.bind("<minus>", lambda _event: self.enlarge(0.8))
        if self.gallery.embedded:
            self.canvas.bind("<Escape>", lambda _event: self.close())

        self.transport = ttk.Frame(body)
        self.transport.grid(row=3, column=0, sticky="ew", pady=(9, 0))
        self.transport.columnconfigure(0, weight=1)
        self.seek_value = tk.DoubleVar(self.transport)
        self.scrub = ttk.Scale(self.transport, name="media_scrub", from_=0, to=1,
                               variable=self.seek_value, command=self.seek)
        self.scrub.grid(row=0, column=0, sticky="ew", padx=(0, 9))
        self.timestamp = ttk.Label(self.transport, width=22, anchor="e", foreground=MUTED)
        self.timestamp.grid(row=0, column=1, sticky="e")
        transport_actions = ttk.Frame(self.transport)
        transport_actions.grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))
        self.play = self.button(transport_actions, "media_play", "播放", "Play", self.toggle_play)
        self.save_poster = self.button(
            transport_actions, "media_save_poster", "设为封面", "Set as cover", self.store_poster,
        ) if self.gallery.catalog is not None else None
        self.original = self.button(transport_actions, "media_original", "用播放器打开原视频", "Open original in player",
                                    self.open_original)

        self.image_actions = ttk.Frame(body)
        self.image_actions.grid(row=3, column=0, sticky="w", pady=(9, 0))
        self.button(self.image_actions, "media_fit", "适合窗口", "Fit to window", self.fit_image)
        self.button(self.image_actions, "media_zoom_in", "放大", "Zoom in", lambda: self.enlarge(1.25))
        self.button(self.image_actions, "media_zoom_out", "缩小", "Zoom out", lambda: self.enlarge(0.8))

        lower = ttk.Frame(body)
        lower.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        lower.columnconfigure(0, weight=1)
        self.notice = ttk.Label(lower, name="media_detail_status", foreground=MUTED, justify="left")
        self.notice.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.relink_button = ttk.Button(lower, name="media_relink", text=self.t("重新定位素材", "Relink source"),
                                        style="Workbench.TButton", command=self.relink)
        self.relink_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.relink_button.grid_remove()

        pages = ttk.Frame(lower)
        pages.grid(row=1, column=0, sticky="w")
        self.previous = self.button(pages, "media_previous", "上一项", "Previous", lambda: self.navigate(-1))
        self.next = self.button(pages, "media_next", "下一项", "Next", lambda: self.navigate(1))
        self.counter = ttk.Label(pages, foreground=MUTED)
        self.counter.pack(side="left", padx=(2, 0))
        caption = self.t("返回", "Back") if self.gallery.embedded else self.t("关闭", "Close")
        actions = ttk.Frame(lower)
        actions.grid(row=1, column=1, sticky="e")
        help_button = guide_button(actions, "media_preview")
        if help_button is not None:
            help_button.pack(side="left", padx=(0, 6))
        ttk.Button(actions, name="media_detail_close", text=caption, command=self.close,
                   style="Workbench.TButton").pack(side="left")

    def resize_header(self, width):
        text_width = max(160, width - 36)
        self.name.configure(wraplength=text_width)
        self.source.configure(wraplength=text_width)
        self.notice.configure(wraplength=max(160, width - 175))

    def button(self, parent, name, zh, en, command):
        button = ttk.Button(parent, name=name, text=self.t(zh, en), command=command, style="Workbench.TButton")
        button.pack(side="left", padx=(0, 5))
        return button

    def schedule_poll(self):
        if self.poll_timer is None:
            self.poll_timer = self.window.after(27, self.poll)

    def load(self):
        self.cancel_seek()
        self.stop_play()
        self.gallery.cursor = self.item.key
        self.gallery.schedule_draw()
        self.gallery.update_status()
        self.frame = None
        self.photo = None
        self.zoom = 1
        self.duration_ms = self.current_ms = 0
        self.name.configure(text=self.item.display_name)
        category = CATEGORIES.get(self.item.category, CATEGORIES["unclassified"])
        self.source.configure(text=" · ".join(x for x in (self.t(*category), self.item.purpose, str(self.item.path)) if x))
        if not self.gallery.embedded:
            self.window.title(self.t("素材预览", "Media preview"))
        self.counter.configure(text=f"{self.index + 1} / {len(self.items)}")
        self.previous.configure(state="normal" if self.index else "disabled")
        self.next.configure(state="normal" if self.index < len(self.items) - 1 else "disabled")
        self.relink_button.grid_remove()
        for widget, show in ((self.transport, self.video), (self.image_actions, not self.video),
                             (self.horizontal, not self.video), (self.vertical, not self.video)):
            widget.grid() if show else widget.grid_remove()
        self.notice.configure(text=self.t("正在读取预览…", "Loading media…"))
        self.update_transport()
        self.schedule_paint()
        time_ms = self.gallery.poster_times.get(self.item.key) if self.video else None
        self.request_frame(time_ms)

    def request_frame(self, time_ms):
        if self.future is not None:
            self.future.cancel()
        size = (1250, 900) if self.video else (1600, 1600)
        self.future = self.executor.submit(load_preview, self.item, size, time_ms)
        self.schedule_poll()

    def poll(self):
        self.poll_timer = None
        if self.future is not None and self.future.done():
            prepared, self.future = self.future, None
            try:
                result = prepared.result()
            except Exception as error:
                self.show_error(error)
            else:
                self.frame, self.current_ms, self.duration_ms = result.image, result.time_ms, result.duration_ms
                help_text = self.t("静音预览，可拖动时间轴。", "Silent preview. Drag the timeline to seek.") if self.video else self.t(
                    "放大后拖动画面查看细节。", "Zoom in, then drag to inspect the image.")
                self.notice.configure(text=help_text)
                self.update_transport()
                self.schedule_paint()
        frames = self.frames
        if frames is not None:
            try:
                while True:
                    image, time_ms, error = frames.get_nowait()
                    if image is None:
                        self.stop_play()
                        if error:
                            self.show_error(error)
                        break
                    self.frame, self.current_ms = image, time_ms
                    self.update_transport()
                    self.schedule_paint()
            except Empty:
                pass
        if self.future is not None or self.frames is not None:
            self.schedule_poll()

    def show_error(self, error):
        self.notice.configure(text=_media_error(error, self.gallery.english))
        self.update_transport()
        if self.gallery.catalog is not None and self.item.key.startswith("import:"):
            self.relink_button.grid()

    def update_transport(self):
        ready = self.duration_ms > 0 and self.frame is not None
        self.setting_scale = True
        self.scrub.configure(to=max(1, self.duration_ms - 1))
        self.seek_value.set(self.current_ms)
        self.setting_scale = False
        self.timestamp.configure(text=f"{_time(self.current_ms)} / {_time(self.duration_ms)}")
        self.scrub.state(["!disabled"] if ready else ["disabled"])
        self.play.configure(state="normal" if ready else "disabled")
        self.original.configure(state="normal" if self.video else "disabled")
        if self.save_poster is not None:
            self.save_poster.configure(state="normal" if ready else "disabled")

    def schedule_paint(self, _event=None):
        if self.paint_timer is None:
            self.paint_timer = self.window.after_idle(self.paint)

    def paint(self):
        self.paint_timer = None
        canvas = self.canvas
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        canvas.delete("all")
        self.photo = None
        if self.frame is None:
            canvas.configure(scrollregion=(0, 0, width, height))
            return
        image = self.frame
        scale = min((width - 4) / image.width, (height - 4) / image.height, 1) * self.zoom
        scale = min(scale, 3200 / max(image.size))
        size = max(1, round(image.width * scale)), max(1, round(image.height * scale))
        shown = image.resize(size, Image.Resampling.LANCZOS) if size != image.size else image
        self.photo = ImageTk.PhotoImage(shown, master=canvas)
        scene_width, scene_height = max(width, size[0]), max(height, size[1])
        canvas.configure(scrollregion=(0, 0, scene_width, scene_height))
        canvas.create_image(scene_width // 2, scene_height // 2, image=self.photo, tags=("media-detail-photo",))

    def enlarge(self, factor):
        if not self.video and self.frame is not None:
            self.zoom = min(4, max(1, self.zoom * factor))
            self.schedule_paint()
        return "break"

    def fit_image(self):
        self.zoom = 1
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.schedule_paint()

    def pan(self, event):
        if not self.video and self.zoom > 1:
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def seek(self, value):
        if self.setting_scale or not self.duration_ms:
            return
        self.stop_play()
        self.cancel_seek()
        time_ms = min(self.duration_ms - 1, max(0, round(float(value))))
        self.timestamp.configure(text=f"{_time(time_ms)} / {_time(self.duration_ms)}")
        self.seek_timer = self.window.after(120, lambda: self.seek_now(time_ms))

    def seek_now(self, time_ms):
        self.seek_timer = None
        self.request_frame(time_ms)

    def cancel_seek(self):
        if self.seek_timer is not None:
            self.window.after_cancel(self.seek_timer)
            self.seek_timer = None

    def toggle_play(self):
        if self.video and self.duration_ms and self.frame is not None:
            if self.stop is not None:
                self.stop_play()
                return "break"
            self.cancel_seek()
            if self.future is not None:
                self.future.cancel()
                self.future = None
            self.stop = Event()
            self.frames = Queue(maxsize=3)
            timestamp = round(self.seek_value.get())
            start = 0 if timestamp >= self.duration_ms - 100 else timestamp
            Thread(target=self.run_playback, args=(self.item, start, self.stop, self.frames),
                   name="media-playback", daemon=True).start()
            self.play.configure(text=self.t("暂停", "Pause"))
            self.schedule_poll()
        return "break"

    @staticmethod
    def put_frame(output, packet):
        while True:
            try:
                output.put_nowait(packet)
                return
            except Full:
                try:
                    output.get_nowait()
                except Empty:
                    pass

    @classmethod
    def run_playback(cls, item, start, stop, output):
        clock = None
        error = None
        try:
            for image, time_ms in iter_video_frames(item, (960, 640), start, stop=stop):
                if clock is None:
                    clock = monotonic()
                if stop.wait(max(0, clock + (time_ms - start) / 1000 - monotonic())):
                    return
                cls.put_frame(output, (image, time_ms, None))
        except Exception as exc:
            error = exc
        if not stop.is_set():
            cls.put_frame(output, (None, 0, error))

    def stop_play(self):
        if self.stop is not None:
            self.stop.set()
            self.stop = self.frames = None
        self.play.configure(text=self.t("播放", "Play"))

    def store_poster(self):
        if self.gallery.catalog is None or not self.video or self.frame is None or self.future is not None:
            return
        self.stop_play()
        self.cancel_seek()
        try:
            self.gallery.catalog.set_poster(self.item.key, self.current_ms)
            self.gallery.refresh(focus=self.item.key)
        except (OSError, ValueError) as error:
            self.show_error(error)
            return
        self.notice.configure(text=self.t(f"已保存封面 · {_time(self.current_ms)}",
                                          f"Cover saved · {_time(self.current_ms)}"))
        if self.gallery.on_change is not None:
            self.gallery.on_change()

    def navigate(self, delta):
        index = self.index + delta
        if 0 <= index < len(self.items):
            self.index = index
            self.load()
        return "break"

    def relink(self):
        path = filedialog.askopenfilename(parent=self.window, title=self.t("重新定位素材", "Relink source"),
                                          filetypes=((self.t("图片和视频", "Images and videos"), MEDIA_FILTER),))
        if not path:
            return
        try:
            self.gallery.catalog.relink(self.item.key, Path(path))
            self.gallery.refresh(focus=self.item.key)
            updated = next(item for item in self.gallery.items if item.key == self.item.key)
        except (OSError, ValueError) as error:
            self.show_error(error)
            return
        self.items = tuple(updated if item.key == self.item.key else item for item in self.items)
        self.load()
        if self.gallery.on_change is not None:
            self.gallery.on_change()

    def open_original(self):
        import os
        import subprocess
        import sys

        try:
            if not self.item.path.is_file():
                raise FileNotFoundError(self.item.path)
            if os.name == "nt":
                os.startfile(str(self.item.path))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.item.path)])
        except OSError as error:
            self.show_error(error)

    def close(self):
        _close_popup(self.window, self.old_grab)
        if self.gallery.embedded:
            self.gallery.back_from_detail()

    def destroyed(self, event):
        if event.widget == self.window:
            for timer in (self.seek_timer, self.paint_timer, self.poll_timer):
                if timer is not None:
                    self.window.after_cancel(timer)
            if self.stop is not None:
                self.stop.set()
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.photo = None
            self.seek_value = None
