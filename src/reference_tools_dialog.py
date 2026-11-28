"""Select costume and pose images as local generation-only references."""

import tkinter as tk
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from .director_desk import open_director
from .image_api import MAX_IMAGE_BYTES
from .production_images import FORMATS
from .production_project import ACTIONS


COSTUME_ROOT = Path(__file__).resolve().parents[1] / "assets" / "costume_references"
SHISEI_SOURCE = ("https://github.com/wquguru/shisei/blob/8f61ceab10e45f8d3afd254900903733a0ba76ee/"
                 "images/costume/grey/w900/")
COSTUME_GROUPS = (
    ("现代日常", "Modern everyday", (
        ("C115", "牛仔夹克与直筒牛仔裤", "Denim jacket & straight jeans",
         "8b793defd10eeb314b1da0520c01c6af15596aa7e7e9dd9b35d78f186a822504"),
        ("C140", "针织开衫与喇叭长裙", "Cardigan & flared long skirt",
         "f3633214d355a5f551306e7023905fd34675761250291e47df8f77ac3f63ce09"),
        ("C165", "粉色碎花泡袖连衣裙", "Pink floral puff-sleeve dress",
         "77164722dd6cb8533d29f83e1f0e18ebdba472e0e7487ecb40247ac877836af8"),
        ("C383", "燕麦色罗纹针织家居服", "Oatmeal rib-knit lounge set",
         "737e4a982e039d8c731d28041172bb19c29da67010becc7ce543985e2bb3e1a3"),
    )),
    ("通勤与职业", "Workwear & uniforms", (
        ("C125", "石色风衣与九分裤", "Stone trench & cropped trousers",
         "5370d46849041714aba7c2e5d9433ccb75fb9975e8719d6f29990f92e6f14ac5"),
        ("C199", "黑色三件套西装", "Black three-piece suit",
         "12d2a5849ff551a93c83b6e4ba061ad3ff83d30ecd1f04890960fcf7048bd0ad"),
        ("C255", "医生白大褂与浅蓝衬衫", "White doctor's coat & blue shirt",
         "7fad39c6b1f9a5bae7eb75536f7e02e8e306e355de49855929c4b0d2cab0a61a"),
        ("C259", "白底浅蓝边护士服", "White nurse uniform & blue trim",
         "d43dbc06d49f1d0e6026c1419888d8f2ceefa6907866a59eca92b0c3428047bc"),
    )),
    ("婚礼与宴会", "Weddings & eveningwear", (
        ("C208", "祖母绿鱼尾晚礼服", "Emerald mermaid evening gown",
         "ab1b413216c35c6d7674b6b91955a06df8de6a62c5d400c41746f90d7090e736"),
        ("C214", "象牙白 A 字蕾丝婚纱", "Ivory A-line lace bridal gown",
         "2997cab02364bd2d21f13256dd22c561263a77ad4329430d233f43b18b8d03c4"),
        ("C221", "正红金绣秀禾服", "Red & gold Xiuhe bridal dress",
         "6916bf2ff04b4c4ea84660ed50ad1e13dc9fcfe8ef721457c4cd8fd3a7e48de9"),
    )),
    ("古装与民国", "Historical & Republican era", (
        ("C003", "汉 · 赭褐曲裾深衣", "Han · Umber quju shenyi",
         "c18329961ea22a212b7e901d5cfbceea7b765ea46327f1880ad81047df6b7d8b"),
        ("C008", "魏晋 · 天青大袖衫与间色裙", "Wei–Jin · Blue robe & striped skirt",
         "c67ab1f90a4ab50a0203ea8ba019d064bb1f65af772d9d98ffba21895b954f68"),
        ("C012", "唐 · 石榴红齐胸襦裙", "Tang · Pomegranate qixiong ruqun",
         "36cc1a254debee7ae60e4a85f90c972a667058339ed4af94f66a2b9b5fe3442b"),
        ("C021", "宋 · 天水碧褙子与宋裤", "Song · Celadon beizi and trousers",
         "2870f9d8644850933551764682b02b9a99c549a45ef12e92a7951428dc6d8ade"),
        ("C032", "明 · 交领短袄与马面裙", "Ming · Cross-collar ao & skirt",
         "6a80bea4e8693fd5f5350629297e3153bc486daa8e74ea3bad33adb96d736d5d"),
        ("C051", "民国 · 米色碎花倒大袖旗袍", "1920s · Floral bell-sleeve qipao",
         "4a3e587de1c4ac5c999b665b696273507c0e56baf707e4439d2022f46ec1e7a7"),
    )),
    ("动作与幻想", "Action & fantasy", (
        ("C175", "黑色冲锋衣与机能裤", "Black shell & tech joggers",
         "33e0710321a8ccf91576c635f48bf9e2fb26e994ec449b955dccf622a824de84"),
        ("C319", "苔绿游侠装", "Moss-green ranger outfit",
         "e5a1ba409c542634c67246b5d8189f023394d78c868e2265b0d8894d39c74138"),
        ("C331", "深色赛博朋克街头装", "Dark cyberpunk streetwear",
         "f9249a878cf1e5bcdb9fd5063056449d9bccbeb84fcd5123ba13dbe91c558978"),
        ("C335", "沙土色废土拾荒装", "Sand-toned wasteland outfit",
         "ee3f06d4aa2e223f7845e64baabd13dfa5020db366ecc2b5171b22689c21f763"),
        ("C337", "石墨色星舰制服", "Graphite starship crew uniform",
         "c657848f81a7990bdb179ac46427af7521142b2c33eea7c7b9329fb1e86cb700"),
        ("C341", "冰蓝仙侠纱衣", "Ice-blue xianxia gauze robe",
         "e38868a4254a4d366e149476f86496704d3678986b992ab6118fdbfb7983e042"),
    )),
)
COSTUMES = tuple(outfit for _, _, group in COSTUME_GROUPS for outfit in group)


def filter_costumes(outfits, query):
    words = query.casefold().split()
    return tuple(outfit for outfit in outfits if all(
        word in " ".join(outfit[:3]).casefold() for word in words
    ))


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


def open_reference_tools(parent, project, path, kind, on_confirm, *, mount=None, on_close=None,
                         latest_project=None, save_project=None):
    if kind not in {"costume", "pose"}:
        raise ValueError("未知参考图用途。")
    costume = kind == "costume"
    english = getattr(parent._root(), "ui_language", "zh") == "en"

    def tr(zh, en):
        return en if english else zh

    title = tr("角色服装设计", "Character costume design") if costume else tr("角色动作设计", "Character pose design")
    previous_grab = None
    if mount is not None:
        window = ttk.Frame(mount, name=f"{kind}_reference_editor")
        window.pack(fill="both", expand=True)
    else:
        window = tk.Toplevel(parent)
        window.title(title)
        window.geometry("850x620")
        window.minsize(760, 570)
        window.transient(parent.winfo_toplevel())
        previous_grab = parent.grab_current()
        window.grab_set()

    capture_folder = None

    def cleanup(event):
        if event.widget is not window:
            return
        if capture_folder is not None:
            capture_folder.cleanup()

    def close():
        window.destroy()
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
        if on_close is not None:
            on_close()

    if mount is None:
        window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Destroy>", cleanup, add="+")
    content = ttk.Frame(window, padding=14)
    content.pack(fill="both", expand=True)
    note = (
        tr("在本机按分类或关键词找服装，也可导入有权使用的参考图。内置服装来自 Shisei（CC0）。",
           "Find outfits by category or keyword on this device, or import a licensed reference. Built-in outfits are from Shisei (CC0).")
        if costume else tr("用内置 3D 导演台摆放角色和机位，把当前画面直接带回预览。也可导入已有的姿态参考图。",
                           "Set up characters and cameras in the built-in 3D Director Desk and send a still to this preview, or import an existing pose image.")
    )
    ttk.Label(content, text=note, wraplength=780).pack(anchor="w", pady=(0, 9))

    tools = ttk.Frame(content)
    tools.pack(fill="x", pady=(0, 9))

    def use_capture(source):
        nonlocal capture_folder
        if capture_folder is None:
            capture_folder = TemporaryDirectory(prefix="comicflow-pose-")
        target = Path(capture_folder.name) / "director-frame.png"
        target.write_bytes(source.read_bytes())
        show(target, tr("3D 导演台取景", "3D Director Desk still"),
             tr("内置 3D 导演台取景", "Built-in 3D Director Desk still"))

    def launch_director():
        try:
            open_director(window, path, "pose", use_capture, language=tr("zh", "en"))
        except (OSError, RuntimeError) as error:
            messagebox.showerror(title, str(error), parent=window)

    if not costume:
        ttk.Button(tools, text=tr("打开内置 3D 导演台", "Open built-in 3D Director Desk"),
                   command=launch_director).pack(side="left")

    body = ttk.Frame(content)
    body.pack(fill="both", expand=True)
    preview_frame = ttk.LabelFrame(body, text=tr("参考图预览", "Reference preview"), padding=8)
    preview_frame.pack(side="right", fill="both", expand=True)
    picture = ttk.Label(preview_frame, anchor="center", text=tr("请选择参考图", "Select a reference image"))
    picture.pack(fill="both", expand=True)
    visible_costumes = ()
    if costume:
        catalogue = ttk.Frame(body)
        catalogue.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(catalogue, text=tr("服装分类", "Costume category")).pack(anchor="w")
        categories = ttk.Combobox(catalogue, state="readonly", values=(
            f'{tr("全部服装", "All costumes")} ({len(COSTUMES)})',
            *(tr(zh_name, en_name) for zh_name, en_name, _ in COSTUME_GROUPS),
        ))
        categories.pack(fill="x", pady=(3, 7))
        categories.current(0)
        query = tk.StringVar(window)
        ttk.Label(catalogue, text=tr("搜索服装名称或编号", "Search outfit name or ID")).pack(anchor="w")
        ttk.Entry(catalogue, name="costume_search", textvariable=query).pack(fill="x", pady=(3, 7))
        query.trace_add("write", lambda *_args: show_category())
        listing = ttk.Frame(catalogue)
        listing.pack(fill="both", expand=True)
        selection = tk.Listbox(listing, width=36, exportselection=False, selectmode="browse", activestyle="dotbox")
        scrollbar = ttk.Scrollbar(listing, command=selection.yview)
        selection.configure(yscrollcommand=scrollbar.set)
        selection.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        selection.bind("<<ListboxSelect>>", lambda _event: pick_costume())
        categories.bind("<<ComboboxSelected>>", lambda _event: show_category())
    status = tk.StringVar(window)
    ttk.Label(content, textvariable=status, wraplength=770).pack(anchor="w", pady=(8, 0))
    footer = ttk.Frame(content)
    footer.pack(fill="x", pady=(8, 0))
    ttk.Button(footer, text=tr("取消", "Cancel"), command=close).pack(side="right", padx=(8, 0))
    chosen = None

    def clear_preview():
        nonlocal chosen
        chosen = None
        confirm.state(["disabled"])
        picture.configure(image="", text=tr("请选择参考图", "Select a reference image"))
        picture.image = None
        status.set("")

    def show(source, caption, origin="", expected_digest=""):
        nonlocal chosen
        clear_preview()
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
            identity, zh_name, en_name, digest = visible_costumes[selected[0]]
            filename = f"costume_{identity}_front.webp"
            source = COSTUME_ROOT / filename
            if chosen is None or chosen[0] != source:
                show(source, tr(zh_name, en_name), SHISEI_SOURCE + filename, digest)

    def show_category():
        nonlocal visible_costumes
        group = categories.current()
        outfits = COSTUME_GROUPS[group - 1][2] if group > 0 else COSTUMES
        visible_costumes = filter_costumes(outfits, query.get())
        selection.delete(0, "end")
        if not visible_costumes:
            clear_preview()
            status.set(tr("当前分类没有符合的服装。", "No matching outfits in this category."))
            return
        selection.insert("end", *(tr(zh_name, en_name) for _, zh_name, en_name, _ in visible_costumes))
        selection.selection_set(0)
        selection.activate(0)
        selection.see(0)
        pick_costume()

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
        if costume:
            pick_costume()
        if chosen is None:
            return
        source, seen_digest, origin = chosen
        try:
            working = latest_project() if latest_project is not None else project
            asset = import_reference(working, path, source, kind, seen_digest=seen_digest, origin=origin)
            if save_project is not None:
                save_project(working)
        except (OSError, ValueError, RuntimeError, Image.DecompressionBombError) as exc:
            messagebox.showerror(title, str(exc), parent=window)
            return
        close()
        try:
            on_confirm(asset.id)
        except (OSError, RuntimeError, ValueError, tk.TclError) as exc:
            messagebox.showerror(title, str(exc), parent=parent)

    ttk.Button(tools, text=tr("导入本地参考图", "Import local reference"), command=select_local).pack(
        side="left", padx=(0, 8) if costume else 8
    )
    confirm = ttk.Button(footer, text=tr("使用参考图进入生图", "Use reference in image generation"),
                         command=apply, state="disabled")
    confirm.pack(side="right")
    if costume:
        show_category()
    return window
