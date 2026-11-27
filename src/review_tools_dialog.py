"""Local technical inspection of images and adjacent cuts in a delivery package."""

import re
import tkinter as tk
from dataclasses import dataclass
from io import BytesIO
from math import gcd
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from zipfile import BadZipFile

from PIL import Image, ImageTk

from .camera_preflight import camera_cuts, camera_findings_text
from .production_rules import ENGLISH
from .shot_review import ShotReview, load_shots
from .shot_review_dialog import ImagePane
from .storyboard_review import PREVIEW_LIMIT, ReviewResult


IMAGE_FORMATS = ("PNG", "JPEG", "WEBP")
MAX_PREVIEW_PIXELS = 32_000_000
FIELD_LABELS = (
    ("景别", "Shot size"),
    ("机位/角度", "Camera / angle"),
    ("机位空间", "Camera position"),
    ("可见范围", "Visible area"),
    ("运镜", "Camera movement"),
    ("动作起止", "Action start and end"),
    ("连续性", "Continuity"),
    ("动作阶段与机位变化", "Action phase and camera changes"),
)


def label(parent, chinese, english):
    return english if getattr(parent._root(), "ui_language", "zh") == "en" else chinese


@dataclass(frozen=True)
class ImageFacts:
    width: int
    height: int
    size_bytes: int
    image_format: str

    @property
    def ratio(self):
        factor = gcd(self.width, self.height)
        return f"{self.width // factor}:{self.height // factor}"

    @property
    def is_wide(self):
        return self.width * 9 == self.height * 16


def inspect_image(path: Path):
    """Check the original file and return decoded preview pixels from those same bytes."""
    suffix = path.suffix.lower()
    if suffix == ".txt" or suffix not in PREVIEW_LIMIT:
        raise ValueError("请选 PNG、JPEG 或 WebP 图片。")
    limit = PREVIEW_LIMIT[suffix]
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("文件超过内置预览大小限制。")
    with Image.open(BytesIO(data), formats=IMAGE_FORMATS) as image:
        width, height = image.size
        if width * height > MAX_PREVIEW_PIXELS:
            raise ValueError("图片超过内置预览分辨率。")
        if getattr(image, "is_animated", False):
            raise ValueError("请选择静态图片。")
        facts = ImageFacts(width, height, len(data), image.format)
        image.verify()
    with Image.open(BytesIO(data), formats=IMAGE_FORMATS) as image:
        image.load()
        preview = image.convert("RGBA")
        preview.thumbnail((1024, 640), Image.Resampling.LANCZOS)
    return facts, preview


def open_image_inspection(parent):
    window = tk.Toplevel(parent)
    window.title(label(parent, "图片尺寸与比例检查", "Image size and ratio"))
    window.geometry("820x620")
    window.minsize(550, 420)
    window.transient(parent)
    body = ttk.Frame(window, padding=12)
    body.pack(fill="both", expand=True)
    actions = ttk.Frame(body)
    actions.pack(fill="x")
    facts_line = tk.StringVar(window)
    verdict_line = tk.StringVar(window)
    filename = tk.StringVar(window)
    ttk.Label(body, textvariable=filename, wraplength=525).pack(anchor="w", pady=(8, 3))
    ttk.Label(body, textvariable=facts_line).pack(anchor="w")
    ttk.Label(body, textvariable=verdict_line, wraplength=525).pack(anchor="w", pady=(3, 8))
    canvas = tk.Canvas(body, bg="#20252b", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    image = None

    def render(_event=None):
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if image is None or min(width, height) < 2:
            canvas.photo = None
            return
        thumbnail = image.copy()
        thumbnail.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas.photo = ImageTk.PhotoImage(thumbnail, master=canvas)
        canvas.create_image(width // 2, height // 2, image=canvas.photo)

    def choose():
        nonlocal image
        selected = filedialog.askopenfilename(
            parent=window, filetypes=((label(window, "图片", "Images"), "*.png *.jpg *.jpeg *.webp"),),
        )
        if not selected:
            return
        path = Path(selected)
        filename.set(path.name)
        facts_line.set("")
        try:
            facts, image = inspect_image(path)
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            image = None
            verdict_line.set(label(window, "图片检查未完成", "Image inspection incomplete") + f" · {exc}")
        else:
            facts_line.set(
                f"{facts.image_format} · {facts.width} × {facts.height} px · {facts.ratio} · "
                f"{facts.size_bytes:,} {label(window, '字节', 'bytes')}"
            )
            verdict_line.set(
                label(window, "完整解码 · 比例符合 16:9", "Decoded · Ratio matches 16:9")
                if facts.is_wide else
                label(window, "完整解码 · 比例与 16:9 不同", "Decoded · Ratio differs from 16:9")
            )
        render()

    ttk.Button(actions, text=label(window, "选择本地图片", "Choose local image"), command=choose).pack(side="left")
    ttk.Button(actions, text=label(window, "关闭", "Close"), command=window.destroy).pack(side="right")
    verdict_line.set(label(window, "请选择需要核对的图片。", "Choose an image to inspect."))
    canvas.bind("<Configure>", render)
    return window


def shot_fields(shot: ShotReview):
    """Use explicit production fields and fall back to the matching prompt for older packages."""
    fields = {}
    alternate = {"动作起止": "动作"}
    for key, _caption in FIELD_LABELS:
        alias = alternate.get(key, key)
        match_field = rf"^(?:{re.escape(key)}|{re.escape(alias)})[ \t]*[：:][ \t]*([^\r\n]+)"
        for source in (shot.production, shot.sd2):
            match = re.search(match_field, source, re.MULTILINE)
            if match and match[1].strip():
                fields[key] = match[1].strip()
                break
    return fields


def boundary_type(first: ShotReview, second: ShotReview):
    if first.group != second.group:
        return "group"
    if first.storyboard and second.storyboard and first.storyboard != second.storyboard:
        return "page"
    return "panel"


def nonconsecutive_groups(first: ShotReview, second: ShotReview):
    """Keep ZIP entries comparable while noting when intermediate groups are absent."""
    first_number = re.match(r"SB(\d+)", first.group, re.IGNORECASE)
    second_number = re.match(r"SB(\d+)", second.group, re.IGNORECASE)
    return bool(first_number and second_number and int(second_number[1]) - int(first_number[1]) != 1)


def open_cut_review(parent, result: ReviewResult | None, rules=ENGLISH):
    title = label(parent, "景别与镜头衔接复核", "Shot framing & continuity")
    if result is None or not result.members:
        messagebox.showinfo(title, label(parent, "先打开交付 ZIP 并运行验收。", "Open a delivery ZIP and run validation first."),
                            parent=parent)
        return
    try:
        shots = load_shots(result)
    except (BadZipFile, OSError, ValueError) as exc:
        messagebox.showerror(title, str(exc), parent=parent)
        return
    if len(shots) < 2:
        messagebox.showinfo(title, label(parent, "交付包需有至少两条镜头记录。", "At least two shot records are needed."),
                            parent=parent)
        return

    window = tk.Toplevel(parent)
    window.title(title)
    window.geometry("1080x700")
    window.minsize(790, 530)
    window.transient(parent)
    window.grab_set()
    controls = ttk.Frame(window, padding=(10, 8))
    controls.pack(fill="x")
    selection = ttk.Combobox(controls, state="readonly", width=31)
    selection.pack(side="left", padx=(0, 6))
    previous = ttk.Button(controls, text=label(window, "上一处", "Previous cut"), command=lambda: advance(-1))
    previous.pack(side="left", padx=(0, 4))
    following = ttk.Button(controls, text=label(window, "下一处", "Next cut"), command=lambda: advance(1))
    following.pack(side="left", padx=(0, 4))
    boundaries_only = tk.BooleanVar(window)
    ttk.Checkbutton(controls, text=label(window, "仅跨页或跨组", "Across pages or groups"),
                    variable=boundaries_only, command=lambda: refresh()).pack(side="left", padx=4)
    ttk.Button(controls, text=label(window, "关闭", "Close"), command=window.destroy).pack(side="right")
    summary = ttk.Label(window, padding=(10, 3), wraplength=760)
    summary.pack(fill="x")
    pair = ttk.Panedwindow(window, orient="horizontal")
    pair.pack(fill="both", expand=True, padx=10, pady=(4, 10))
    views = []
    for chinese, english in (("前镜", "Outgoing shot"), ("后镜", "Incoming shot")):
        frame = ttk.Frame(pair, padding=5)
        pair.add(frame, weight=1)
        heading = ttk.Label(frame)
        heading.pack(anchor="w", pady=(0, 4))
        preview = ImagePane(frame, "故事板", result)
        preview.pack(fill="both", expand=True)
        details = scrolledtext.ScrolledText(frame, height=10, width=40, wrap="word", state="disabled")
        details.pack(fill="both", expand=True, pady=(4, 0))
        views.append((label(window, chinese, english), heading, preview, details))

    def render(view, shot=None):
        caption, heading, preview, details = view
        heading.configure(text=f"{caption} · {shot.shot}" if shot else caption)
        details.configure(state="normal")
        details.delete("1.0", "end")
        if shot:
            preview.show((shot.group, shot.shot), shot.storyboard, "未找到唯一故事板", shot.board_box)
            fields = shot_fields(shot)
            missing = label(window, "无记录", "Not recorded")
            rows = [f"{label(window, key, english)} · {fields.get(key, missing)}" for key, english in FIELD_LABELS]
            if shot.storyboard:
                rows.insert(0, shot.storyboard)
                if preview.image is not None and not preview.auto_region:
                    rows.append(label(window, "该镜没有有效窗口坐标。可在整板上手工框选实际格子。",
                                      "No valid crop coordinates. Select the panel on the full sheet."))
            details.insert("1.0", "\n".join(rows + list(shot.notices)))
        else:
            preview.show(("", ""), None, "无可预览图像")
        details.configure(state="disabled")

    types = [boundary_type(first, second) for first, second in zip(shots, shots[1:])]
    choices = []
    kind_labels = {
        "group": label(window, "跨组", "Across groups"),
        "page": label(window, "跨故事板页", "Across board pages"),
        "panel": label(window, "组内相邻镜头", "Within a group"),
    }

    def show(index):
        has_pair = 0 <= index < len(choices)
        previous.configure(state="normal" if has_pair and index > 0 else "disabled")
        following.configure(state="normal" if has_pair and index + 1 < len(choices) else "disabled")
        if not has_pair:
            summary.configure(text=label(window, "包内没有可定位的跨页或跨组衔接。",
                                         "No cross-page or cross-group cuts could be located."))
            for view in views:
                render(view)
            return
        selection.current(index)
        position = choices[index]
        first, second = shots[position:position + 2]
        guidance = label(
            window,
            "对照实际画面核对景别、机位、视线和动作交接。跨页或跨组时核对方位、持物和人物状态是否延续。",
            "Compare framing, angle, eyelines and action in the images. Across pages or groups, check geography, props in hand and character state.",
        )
        if types[position] == "group" and nonconsecutive_groups(first, second):
            guidance = label(
                window,
                "包内组号不连续。只能对照包内这两镜，实际前后衔接需核对中间组。",
                "Group numbers do not follow each other. Compare the included shots here and check the missing groups separately.",
            )
        else:
            pair_fields = ((first.shot, shot_fields(first)), (second.shot, shot_fields(second)))
            warnings = camera_findings_text(camera_cuts(pair_fields, rules),
                                            english=getattr(window._root(), "ui_language", "zh") == "en")
            if warnings:
                guidance = warnings + "\n" + guidance
        summary.configure(text=f"{kind_labels[types[position]]} · {guidance}")
        for view, shot in zip(views, (first, second)):
            render(view, shot)

    def advance(delta):
        show(selection.current() + delta)

    def refresh():
        selected = selection.get()
        choices[:] = [index for index, kind in enumerate(types) if not boundaries_only.get() or kind != "panel"]
        descriptions = [f"{shots[index].shot} → {shots[index+1].shot} · {kind_labels[types[index]]}"
                        for index in choices]
        selection.configure(values=descriptions, state="readonly" if descriptions else "disabled")
        selection.set("")
        show(descriptions.index(selected) if selected in descriptions else 0)

    selection.bind("<<ComboboxSelected>>", lambda _event: show(selection.current()))
    refresh()
    return window
