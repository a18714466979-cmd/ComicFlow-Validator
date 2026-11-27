"""Read-only side-by-side image and text review for a validated delivery ZIP."""

import tkinter as tk
from functools import lru_cache
from io import BytesIO
from tkinter import messagebox, scrolledtext, ttk
from zipfile import BadZipFile

from PIL import Image, ImageTk

from .production_layout import valid_box
from .shot_review import load_shots, pixel_selection, shot_id, shot_summary
from .storyboard_review import ReviewResult, read_preview


def read_image(result: ReviewResult, path: str) -> Image.Image:
    with Image.open(BytesIO(read_preview(result, path))) as image:
        if image.width * image.height > 32_000_000:
            raise ValueError("图片超过内置预览分辨率。")
        return image.convert("RGB")


class ImagePane(ttk.LabelFrame):
    """Preview one source image and retain manually selected regions by shot."""

    def __init__(self, parent, title: str, result: ReviewResult):
        super().__init__(parent, text=title, padding=5)
        self.result = result
        self.image = None
        self.photo = None
        self.path = None
        self.key = None
        self.regions = {}
        self.auto_region = None
        self.zoomed = False
        self.image_bounds = None
        self.drag_start = None
        self.drag_box = None
        self.notice = ""

        self.canvas = tk.Canvas(self, background="#20252b", highlightthickness=0, height=185)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.draw())
        self.canvas.bind("<Button-1>", self.begin_selection)
        self.canvas.bind("<B1-Motion>", self.move_selection)
        self.canvas.bind("<ButtonRelease-1>", self.end_selection)
        tools = ttk.Frame(self)
        tools.pack(fill="x", pady=(4, 0))
        self.mode = ttk.Label(tools, text="")
        self.mode.pack(side="left")
        self.toggle_button = ttk.Button(tools, text="显示整图", command=self.toggle)
        self.toggle_button.pack(side="right")

    def show(self, key: tuple[str, str], path: str | None, notice: str, region=None) -> None:
        self.key = key
        self.notice = notice
        if path != self.path:
            self.path = path
            self.image = None
            if path in self.result.members:
                try:
                    self.image = read_image(self.result, path)
                except (OSError, ValueError, BadZipFile) as exc:
                    self.notice = f"无法预览：{exc}"
        self.auto_region = region if self.image and valid_box(region, self.image.size) else None
        self.zoomed = bool(self.image and (key in self.regions or self.auto_region))
        self.draw()

    def toggle(self) -> None:
        self.zoomed = not self.zoomed
        self.draw()

    def draw(self) -> None:
        self.canvas.delete("all")
        self.drag_start = self.drag_box = self.image_bounds = None
        self.photo = None
        width = max(20, self.canvas.winfo_width())
        height = max(20, self.canvas.winfo_height())
        region = self.regions.get(self.key) or self.auto_region
        self.toggle_button.configure(state="normal" if region and self.image else "disabled",
                                     text="显示整图" if self.zoomed else "查看本镜窗口")
        if self.image is None:
            self.mode.configure(text="无可预览图像")
            self.canvas.create_text(width / 2, height / 2, text=self.notice, width=max(15, width - 30), fill="white")
            return

        image = self.image.crop(region) if self.zoomed and region else self.image
        scale = min((width - 8) / image.width, (height - 8) / image.height)
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        self.photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS), master=self.canvas)
        left, top = (width - size[0]) // 2, (height - size[1]) // 2
        self.canvas.create_image(left, top, anchor="nw", image=self.photo)
        self.image_bounds = (left, top, *size)
        title = "手动框选 · 局部预览" if self.key in self.regions else "包内坐标 · 本镜窗口"
        self.mode.configure(text=title if self.zoomed else "整图预览 · 拖动框选核对区域")

    def begin_selection(self, event) -> None:
        if self.image_bounds is None or self.zoomed:
            return
        left, top, width, height = self.image_bounds
        if left <= event.x < left + width and top <= event.y < top + height:
            self.drag_start = (event.x, event.y)
            self.drag_box = self.canvas.create_rectangle(*self.drag_start, *self.drag_start, outline="#ffcf60", width=2)

    def move_selection(self, event) -> None:
        if self.drag_box is not None:
            self.canvas.coords(self.drag_box, *self.drag_start, event.x, event.y)

    def end_selection(self, event) -> None:
        if self.drag_start is None:
            return
        selected = pixel_selection(self.drag_start, (event.x, event.y), self.image_bounds, self.image.size)
        if selected:
            self.regions[self.key] = selected
            self.zoomed = True
        self.draw()


def open_shot_review(parent: tk.Tk, result: ReviewResult, group: str = "", shot: str = "") -> None:
    try:
        shots = load_shots(result)
    except (ValueError, OSError, BadZipFile) as exc:
        messagebox.showerror("无法打开逐格复核", str(exc), parent=parent)
        return
    if not shots:
        messagebox.showinfo("没有可对照的镜头", "交付包中没有可读取的镜号记录。", parent=parent)
        return

    window = tk.Toplevel(parent)
    window.title("ComicFlow 逐格复核")
    window.geometry("1250x850")
    window.minsize(850, 650)
    window.transient(parent)
    # Keep the validated archive snapshot available until this review is closed.
    window.grab_set()
    navigation = ttk.Frame(window, padding=(12, 8))
    navigation.pack(fill="x")
    selection = ttk.Combobox(navigation, values=[f"{row.group} / {row.shot}" for row in shots], state="readonly", width=28)
    selection.pack(side="left")
    notes = ttk.Label(window, padding=(12, 0), wraplength=1000)
    notes.pack(fill="x")
    plate_details = ttk.Label(window, padding=(12, 3), wraplength=1000)
    plate_details.pack(fill="x")
    split = ttk.Panedwindow(window, orient="vertical")
    split.pack(fill="both", expand=True, padx=12, pady=4)

    pictures = ttk.Panedwindow(split, orient="horizontal")
    texts = ttk.Panedwindow(split, orient="horizontal")
    split.add(pictures, weight=3)
    split.add(texts, weight=2)
    board = ImagePane(pictures, "故事板", result)
    plate = ImagePane(pictures, "彩色净板", result)
    pictures.add(board, weight=1)
    pictures.add(plate, weight=1)
    text_panes = []
    for title in ("生产记录 · 本镜", "SD2 提示词 · 本镜"):
        frame = ttk.LabelFrame(texts, text=title, padding=5)
        pane = scrolledtext.ScrolledText(frame, wrap="word", height=7, state="disabled")
        pane.pack(fill="both", expand=True)
        texts.add(frame, weight=1)
        text_panes.append(pane)

    adjacent = ttk.Frame(window, padding=(12, 4, 12, 9))
    adjacent.pack(fill="x")
    adjacent.columnconfigure(0, weight=1, uniform="neighbors")
    adjacent.columnconfigure(1, weight=1, uniform="neighbors")
    neighbor_labels = []
    for column, title in enumerate(("上一镜", "下一镜")):
        frame = ttk.LabelFrame(adjacent, text=title, padding=5)
        frame.grid(row=0, column=column, sticky="nsew", padx=2)
        label = ttk.Label(frame, wraplength=240, compound="left")
        label.pack(anchor="w", fill="x")
        neighbor_labels.append(label)

    @lru_cache(maxsize=12)
    def neighbor_thumbnail(path: str | None, region: tuple[int, int, int, int] | None):
        if not path:
            return None
        try:
            image = board.image if board.path == path and board.image is not None else read_image(result, path)
        except (OSError, ValueError, BadZipFile):
            return None
        preview = image.crop(region) if valid_box(region, image.size) else image.copy()
        preview.thumbnail((144, 81), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(preview, master=window)

    def show(index: int) -> None:
        selection.current(index)
        row = shots[index]
        key = (row.group, row.shot)
        notes.configure(text=" · ".join(row.notices) or "按包内镜号和局部对应表显示，画面内容由人工核对。")
        reference = row.plate
        plate_path = f"{row.group}/{reference.filename}" if reference else None
        plate_details.configure(text=(f"{reference.slot} · {reference.scene} · {reference.filename} · {reference.description}"
                                     if reference else "该镜暂无唯一净板对应。"))
        board.show(key, row.storyboard, "未找到唯一故事板", row.board_box)
        plate.show(key, plate_path, "净板缺失或对应关系不明确", row.plate_box)
        for pane, text in zip(text_panes, (row.production, row.sd2)):
            pane.configure(state="normal")
            pane.delete("1.0", "end")
            pane.insert("1.0", text or "没有可定位的唯一记录。")
            pane.configure(state="disabled")
        for label, neighbor in zip(neighbor_labels, (index - 1, index + 1)):
            if 0 <= neighbor < len(shots):
                other = shots[neighbor]
                manual = board.regions.get((other.group, other.shot))
                region = manual or other.board_box
                thumbnail = neighbor_thumbnail(other.storyboard, region)
                summary = shot_summary(other)
                if len(summary) > 110:
                    summary = summary[:110] + "…"
                image_label = " · 已框选" if manual else " · 镜头窗口" if region else " · 整板" if thumbnail else ""
                label.configure(text=f"{other.shot}{image_label}\n{summary}", image=thumbnail or "")
                label.photo = thumbnail
            else:
                label.configure(text="包内无相邻镜头", image="")
                label.photo = None
        previous.configure(state="normal" if index else "disabled")
        following.configure(state="normal" if index + 1 < len(shots) else "disabled")

    def step(offset: int) -> None:
        index = selection.current() + offset
        if 0 <= index < len(shots):
            show(index)

    previous = ttk.Button(navigation, text="上一镜", command=lambda: step(-1))
    previous.pack(side="left", padx=6)
    following = ttk.Button(navigation, text="下一镜", command=lambda: step(1))
    following.pack(side="left")
    selection.bind("<<ComboboxSelected>>", lambda _event: show(selection.current()))

    normalized = shot_id(shot, group.partition("_")[0].upper()) if shot else ""
    group_index = next((i for i, row in enumerate(shots) if row.group == group), 0)
    initial = next((i for i, row in enumerate(shots) if row.group == group and row.shot == normalized), group_index)
    show(initial)
    parent.wait_window(window)
