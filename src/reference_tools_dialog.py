"""Select costume and pose images as local generation-only references."""

import tkinter as tk
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import filedialog, messagebox, ttk
import webbrowser

from PIL import Image, ImageOps, ImageTk

from .image_api import MAX_IMAGE_BYTES
from .production_images import FORMATS
from .production_project import ACTIONS


COSTUME_GALLERY = "https://posewear.pages.dev/#costume"
DIRECTOR_DESK = "https://xiaozangao.github.io/3d-director-desk/"
COSTUME_ROOT = Path(__file__).resolve().parents[1] / "assets" / "costume_references"
SHISEI_SOURCE = ("https://github.com/wquguru/shisei/blob/8f61ceab10e45f8d3afd254900903733a0ba76ee/"
                 "images/costume/grey/w900/")
COSTUMES = (
    ("C003", "汉 · 赭褐曲裾深衣", "Han · Umber quju shenyi",
     "c18329961ea22a212b7e901d5cfbceea7b765ea46327f1880ad81047df6b7d8b"),
    ("C012", "唐 · 石榴红齐胸襦裙", "Tang · Pomegranate qixiong ruqun",
     "36cc1a254debee7ae60e4a85f90c972a667058339ed4af94f66a2b9b5fe3442b"),
    ("C021", "宋 · 天水碧褙子与宋裤", "Song · Celadon beizi and trousers",
     "2870f9d8644850933551764682b02b9a99c549a45ef12e92a7951428dc6d8ade"),
    ("C032", "明 · 交领短袄与马面裙", "Ming · Cross-collar ao and horse-face skirt",
     "6a80bea4e8693fd5f5350629297e3153bc486daa8e74ea3bad33adb96d736d5d"),
    ("C051", "民国 · 米色碎花倒大袖旗袍", "1920s · Cream floral bell-sleeve qipao",
     "4a3e587de1c4ac5c999b665b696273507c0e56baf707e4439d2022f46ec1e7a7"),
)


def read_reference(path, expected_digest=""):
    with path.open("rb") as stream:
        data = stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("参考图超过 32 MiB。")
    if expected_digest and sha256(data).hexdigest() != expected_digest:
        raise ValueError("内置服装的 SHA-256 与原始参考不符。")
    with Image.open(BytesIO(data)) as image:
        kind = image.format
        if kind not in FORMATS or image.width * image.height > 32_000_000 or getattr(image, "n_frames", 1) != 1:
            raise ValueError("请选择单帧 PNG、JPEG 或 WebP，最多 3200 万像素。")
        image.load()
        preview = ImageOps.exif_transpose(image)
        return data, kind, preview


def import_reference(project, project_path, source, kind, *, seen_digest, origin=""):
    data, image_kind, image = read_reference(source)
    source_digest = sha256(data).hexdigest()
    if seen_digest != source_digest:
        raise ValueError("参考图在预览后发生变化，请重新选择。")

    # Preserve original PNG bytes. Image requests take PNG, so an original JPEG
    # or WebP is preserved at its source and the derived PNG records that source.
    if image_kind != "PNG":
        with BytesIO() as stream:
            image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB").save(
                stream, format="PNG"
            )
            data = stream.getvalue()
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("转为 PNG 后超过 32 MiB，请选择更小的参考图。")
    png_digest = sha256(data).hexdigest()
    linked = next((item for item in project.images if item.digest == png_digest and not item.reference_only), None)
    if linked is not None:
        project.checked_image(project_path, linked)
        return linked

    label = "服装" if kind == "costume" else "动作"
    source_name = origin or str(source.resolve())
    source_record = source_name if image_kind == "PNG" else f"{source_name} | {image_kind} SHA-256 {source_digest}"
    filename = f"{kind}_reference_{png_digest[:16]}.png"
    existing = next((item for item in project.images if item.digest == png_digest and item.reference_only
                     and (item.origin == source_record or item.filename == filename)), None)
    if existing is not None:
        project.checked_image(project_path, existing)
        return existing

    with TemporaryDirectory(prefix="comicflow-reference-") as folder:
        local = Path(folder) / filename
        local.write_bytes(data)
        return project.import_image(
            project_path, local, filename, action=ACTIONS[0], version="R1",
            reason=f"作为{label}生图参考，" + ("按原字节导入。" if image_kind == "PNG" else f"从 {image_kind} 转为 PNG。"),
            inspection=f"选择前已预览；导入时完整解码并核对源图 SHA-256。{image.width}×{image.height}。",
            reference_only=True, origin_label=source_record,
        )


def open_reference_tools(parent, project, path, kind, on_confirm):
    if kind not in {"costume", "pose"}:
        raise ValueError("未知参考图用途。")
    costume = kind == "costume"
    english = getattr(parent._root(), "ui_language", "zh") == "en"

    def tr(zh, en):
        return en if english else zh

    window = tk.Toplevel(parent)
    title = tr("角色服装设计", "Character costume design") if costume else tr("角色动作设计", "Character pose design")
    window.title(title)
    window.geometry("850x620")
    window.minsize(760, 570)
    window.transient(parent)
    previous_grab = parent.grab_current()
    window.grab_set()

    def close():
        window.destroy()
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()

    window.protocol("WM_DELETE_WINDOW", close)
    content = ttk.Frame(window, padding=14)
    content.pack(fill="both", expand=True)
    note = (
        tr("选择一套女装参考，或导入拥有使用权的服装图。内置历代服饰来自 Shisei（CC0）。",
           "Choose a costume or import a licensed reference. Built-in historical outfits are from Shisei (CC0).")
        if costume else tr("在在线 3D 导演台摆放角色、动作和机位，保存画面截图后导入。也可直接使用已有的姿态参考。",
                           "Arrange characters, poses and cameras in the online 3D Director Desk, then import a still or use an existing pose image.")
    )
    ttk.Label(content, text=note, wraplength=780).pack(anchor="w", pady=(0, 9))

    tools = ttk.Frame(content)
    tools.pack(fill="x", pady=(0, 9))

    def browse():
        url = COSTUME_GALLERY if costume else DIRECTOR_DESK
        if not webbrowser.open_new_tab(url):
            messagebox.showinfo(title, url, parent=window)

    ttk.Button(tools, text=(tr("打开 PoseWear 服装图库", "Open PoseWear costume gallery") if costume else
                           tr("打开在线 3D 导演台", "Open online 3D Director Desk")), command=browse).pack(side="left")

    body = ttk.Frame(content)
    body.pack(fill="both", expand=True)
    preview_frame = ttk.LabelFrame(body, text=tr("参考图预览", "Reference preview"), padding=8)
    preview_frame.pack(side="right", fill="both", expand=True)
    picture = ttk.Label(preview_frame, anchor="center", text=tr("请选择参考图", "Select a reference image"))
    picture.pack(fill="both", expand=True)
    if costume:
        selection = tk.Listbox(body, width=36, exportselection=False, selectmode="browse", activestyle="dotbox")
        selection.pack(side="left", fill="y", padx=(0, 12))
        for _, zh_name, en_name, _ in COSTUMES:
            selection.insert("end", tr(zh_name, en_name))
        selection.bind("<<ListboxSelect>>", lambda _event: pick_costume())
    status = tk.StringVar(window)
    ttk.Label(content, textvariable=status, wraplength=770).pack(anchor="w", pady=(8, 0))
    footer = ttk.Frame(content)
    footer.pack(fill="x", pady=(8, 0))
    ttk.Button(footer, text=tr("取消", "Cancel"), command=close).pack(side="right", padx=(8, 0))
    chosen = None

    def show(source, caption, origin="", expected_digest=""):
        nonlocal chosen
        chosen = None
        confirm.state(["disabled"])
        picture.configure(image="", text=tr("请选择参考图", "Select a reference image"))
        picture.image = None
        status.set("")
        try:
            data, _, image = read_reference(source, expected_digest)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            status.set(str(exc))
            return
        details = f"{caption} · {image.width}×{image.height}"
        image.thumbnail((440, 365), Image.Resampling.LANCZOS)
        picture.image = ImageTk.PhotoImage(image, master=window)
        picture.configure(image=picture.image, text="")
        chosen = (source, sha256(data).hexdigest(), origin)
        status.set(details)
        confirm.state(["!disabled"])

    def pick_costume():
        if selected := selection.curselection():
            identity, zh_name, en_name, digest = COSTUMES[selected[0]]
            filename = f"costume_{identity}_front.webp"
            show(COSTUME_ROOT / filename, tr(zh_name, en_name), SHISEI_SOURCE + filename, digest)

    def select_local():
        selected = filedialog.askopenfilename(
            parent=window, filetypes=((tr("参考图片", "Reference images"), "*.png *.jpg *.jpeg *.webp"),)
        )
        if selected:
            if costume:
                selection.selection_clear(0, "end")
            source = Path(selected)
            show(source, source.name)

    def apply():
        if chosen is None:
            return
        source, seen_digest, origin = chosen
        try:
            asset = import_reference(project, path, source, kind, seen_digest=seen_digest, origin=origin)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            messagebox.showerror(title, str(exc), parent=window)
            return
        close()
        on_confirm(asset.id)

    ttk.Button(tools, text=tr("导入本地参考图", "Import local reference"), command=select_local).pack(
        side="left", padx=8
    )
    confirm = ttk.Button(footer, text=tr("使用参考图进入生图", "Use reference in image generation"),
                         command=apply, state="disabled")
    confirm.pack(side="right")
    if costume:
        selection.selection_set(0)
        pick_costume()
