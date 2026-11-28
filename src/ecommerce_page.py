"""Video-first production workspace for ecommerce storyboard deliveries."""

from copy import deepcopy
from dataclasses import replace
from io import BytesIO
import os
from pathlib import Path
from queue import Empty, Queue
from subprocess import Popen
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from uuid import uuid4

from PIL import Image, ImageTk

from .brand import APP_FOLDER
from .ecommerce_ai import (
    draft_ecommerce_shots, preview_ecommerce_analysis, preview_ecommerce_image, submit_ecommerce_image,
)
from .ecommerce_delivery import (
    asset_audit, board_layout, compose_product_sheet, label_board_sheet, publish_ecommerce_delivery,
    render_group_prompt, stage_ecommerce_delivery,
)
from .ecommerce_project import EcommerceProject, EcommerceShot, parse_shots, render_shots, time_range
from .ecommerce_video import VIDEO_FILTER, analyze_video, format_timestamp, inspect_video, preview_frame, preview_sheet
from .image_api import query_image
from .production_project import atomic_text
from .reference_tools_dialog import read_reference


PHASES = (
    ("导入与产品", "Source & product"), ("分镜分析", "Shot analysis"),
    ("资产与故事板", "Assets & boards"), ("提示词与交付", "Prompts & delivery"),
)
IMAGE_FILTER = ("PNG / JPEG / WebP", "*.png *.jpg *.jpeg *.webp")
SHOT_FIELDS = (
    ("scene", "场景", "Scene"), ("size", "景别", "Shot size"), ("angle", "机位/角度", "Camera angle"),
    ("camera", "运镜", "Camera movement"), ("action", "画面/事件", "On-screen action"),
    ("positions", "人物站位", "Staging"), ("axis", "视线/轴线", "Eyeline and axis"),
    ("performance", "表演/情绪", "Performance"),
    ("dialogue", "原语言对白", "Original dialogue"), ("sound", "声音", "Sound"),
    ("continuity", "连续性", "Continuity"), ("constraints", "视频模型约束", "Model constraints"),
    ("visual_text", "画面文字原文", "On-screen text"), ("characters", "人物，逐行输入", "Characters, one per line"),
    ("props", "道具，逐行输入", "Props, one per line"),
)
KINDS = {
    "character": ("人物", "Character"), "scene": ("场景", "Scene"), "props": ("道具", "Props"),
    "product": ("产品", "Product"), "board": ("故事板", "Storyboard"),
}
STATUSES = {
    "reuse": ("已绑定", "Linked"), "derive": ("可用产品照片合成", "Compose from product photos"),
    "generate": ("待制作或导入", "Needs a new or imported sheet"),
}


class EcommercePage:
    def __init__(self, page, vision_session, image_session, open_api):
        self.page = page
        self.window = page.winfo_toplevel()
        self.vision_session, self.image_session = vision_session, image_session
        self.open_api = open_api
        self.project = EcommerceProject("")
        self.path = None
        self.saved = deepcopy(self.project)
        self.info = None
        self.labels = []
        self.tables = []
        self.buttons = []
        self.form_controls = []
        self.busy = False
        self.jobs = {}
        self.staged = None
        self.stage_folder = None
        self.assets = {}
        self.status = tk.StringVar(page)
        self.video_status = tk.StringVar(page)
        self.group_status = tk.StringVar(page)
        self.name, self.product_name, self.source_product = (tk.StringVar(page) for _ in range(3))
        self.product_required = tk.BooleanVar(page, self.project.product_required)
        self.product_reviewed = tk.BooleanVar(page)
        self.build()
        self.product_name.trace_add("write", self.check_product_name)
        self.load_form()
        self.refresh_language()

    def t(self, zh, en):
        return en if getattr(self.window, "ui_language", "zh") == "en" else zh

    def label(self, parent, zh, en, **options):
        control = ttk.Label(parent, **options)
        self.labels.append((control, zh, en))
        return control

    def button(self, parent, zh, en, command, *, primary=False):
        style = "Primary.Workbench.TButton" if primary else "Workbench.TButton"
        control = ttk.Button(parent, command=lambda: self.guard(command), style=style)
        self.labels.append((control, zh, en))
        self.buttons.append(control)
        control.pack(side="left", padx=(0, 5), pady=3)
        return control

    def check(self, parent, zh, en, variable, command=None):
        control = ttk.Checkbutton(parent, variable=variable, command=command)
        self.labels.append((control, zh, en))
        self.form_controls.append(control)
        return control

    def table(self, parent, columns):
        area = ttk.Frame(parent)
        area.pack(fill="both", expand=True)
        view = ttk.Treeview(area, columns=[item[0] for item in columns], show="headings", selectmode="browse", height=9)
        scrollbar = ttk.Scrollbar(area, orient="vertical", command=view.yview)
        view.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        view.pack(side="left", fill="both", expand=True)
        for identifier, _, _, width in columns:
            view.column(identifier, width=width, minwidth=48)
        self.tables.append((view, columns))
        return view

    def build(self):
        top = ttk.Frame(self.page, padding=(12, 9, 12, 3))
        top.pack(fill="x")
        self.label(top, "电商信息流视频复刻", "E-commerce video recreation",
                   font=("TkDefaultFont", 16, "bold")).pack(side="left")
        actions = ttk.Frame(top)
        actions.pack(side="right")
        self.button(actions, "新建电商项目", "New project", self.new)
        self.button(actions, "打开电商项目", "Open project", self.open)
        self.button(actions, "保存电商项目", "Save project", self.save, primary=True)

        self.steps = ttk.Notebook(self.page)
        self.steps.pack(fill="both", expand=True, padx=12, pady=6)
        pages = [ttk.Frame(self.steps, padding=10) for _ in PHASES]
        for phase in pages:
            self.steps.add(phase)
        self.build_source(pages[0])
        self.build_shots(pages[1])
        self.build_assets(pages[2])
        self.build_delivery(pages[3])
        ttk.Label(self.page, textvariable=self.status, wraplength=850, padding=(12, 0, 12, 10)).pack(anchor="w")

    def build_source(self, page):
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "导入参考视频", "Import reference video", self.import_video, primary=True)
        self.button(row, "播放参考视频", "Play reference video", self.play_video)
        self.button(row, "预览参考帧", "Preview reference frame", self.preview_video)
        ttk.Label(page, textvariable=self.video_status, wraplength=800).pack(anchor="w", pady=(4, 10))

        form = ttk.Frame(page)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        for index, (zh, en, variable) in enumerate((
            ("项目名", "Project name", self.name), ("自有产品名", "Your product name", self.product_name),
            ("原产品名（对白明确替换时填写）", "Source product name (only for an explicit replacement)", self.source_product),
        )):
            self.label(form, zh, en).grid(row=index, column=0, sticky="w", padx=(0, 7), pady=4)
            control = ttk.Entry(form, textvariable=variable)
            control.grid(row=index, column=1, sticky="ew", pady=4)
            self.form_controls.append(control)

        self.check(page, "参考片有主推产品", "The reference features a product", self.product_required,
                   self.product_edited).pack(anchor="w", pady=(5, 0))
        row = ttk.Frame(page)
        row.pack(fill="x", pady=5)
        self.button(row, "导入产品照片", "Import product photos", self.import_products)
        self.button(row, "查看选中照片", "Preview selected photo", self.preview_product)
        self.button(row, "移除选中照片", "Remove selected photo", self.remove_product)
        photos = ttk.Frame(page)
        photos.pack(fill="both", expand=True)
        self.product_list = tk.Listbox(photos, height=4, exportselection=False)
        self.product_list.pack(fill="both", expand=True)
        self.product_list.bind("<Double-1>", lambda _event: self.guard(self.preview_product))
        self.check(page, "确认产品照片覆盖所需角度", "Product photos cover all required views",
                   self.product_reviewed).pack(anchor="w", pady=(6, 2))
        self.label(page, "对照原片核对正反面、侧面、包装与演示需要的状态。缺图时先补照片。",
                   "Check front, back, side, packaging and the states used in the reference. Add missing photos first.",
                   wraplength=820).pack(anchor="w")
        row = ttk.Frame(page)
        row.pack(fill="x", pady=3)
        self.button(row, "下一步：分镜分析", "Next: Shot analysis", self.enter_shots, primary=True)

    def build_shots(self, page):
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "检测镜头切点", "Detect candidate cuts", self.detect_cuts, primary=True)
        self.button(row, "AI 辅助看图拆镜", "Draft shots from frames with AI", self.ai_shots)
        self.button(row, "播放参考视频", "Play reference video", self.play_video)
        self.button(row, "导入原声对白 TXT", "Import original dialogue TXT", self.import_transcript)
        self.button(row, "API 设置", "API settings", self.open_api)
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "添加镜头", "Add shot", lambda: self.edit_shot(None))
        self.button(row, "编辑镜头", "Edit shot", lambda: self.edit_shot(self.selected_shot()))
        self.button(row, "查看参考帧", "View reference frame", self.inspect_shot)
        self.button(row, "删除选中镜头", "Remove shot", self.remove_shot)
        self.button(row, "导入分镜 JSON", "Import shot JSON", self.import_shots)
        self.button(row, "导出分镜 JSON", "Export shot JSON", self.export_shots)
        self.button(row, "公共连续性", "Shared continuity", self.edit_continuity)
        self.shot_table = self.table(page, (
            ("id", "镜号", "ID", 70), ("time", "时间码", "Time", 173), ("scene", "场景", "Scene", 115),
            ("action", "画面动作", "Action", 265), ("dialogue", "对白", "Dialogue", 175),
        ))
        self.shot_table.bind("<Double-1>", lambda _event: self.guard(lambda: self.edit_shot(self.selected_shot())))
        self.label(page, "切点是候选，场景切换和原声对白需人工核对。分组按场景、15 秒上限和格数限制执行。",
                   "Visual cuts are candidates. Confirm scene changes and original dialogue. Groups enforce scene, duration and panel limits.",
                   wraplength=800).pack(anchor="w", pady=(8, 2))
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "确认分镜并分析资产", "Approve shots & audit assets", self.approve_shots, primary=True)
        ttk.Label(row, textvariable=self.group_status).pack(side="left", padx=7)

    def build_assets(self, page):
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "刷新资产清单", "Refresh asset audit", self.audit)
        self.button(row, "合成自有产品总图", "Compose product sheet", self.make_product)
        self.button(row, "导入批准图像", "Import approved image", self.import_asset)
        self.button(row, "预览资产", "Preview asset", self.preview_asset)
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "用 API 制作选中资产", "Generate selected asset with API", self.generate_asset, primary=True)
        self.button(row, "查询生图任务", "Check image job", self.poll_asset)
        self.button(row, "API 设置", "API settings", self.open_api)
        self.asset_table = self.table(page, (
            ("kind", "类别", "Category", 106), ("name", "用途", "Asset", 247),
            ("state", "状态", "State", 182), ("path", "文件", "File", 252),
        ))
        self.asset_table.bind("<Double-1>", lambda _event: self.guard(self.preview_asset))
        self.label(page, "先完成角色、场景和道具，再制作全组一张 9:16 彩色故事板。人物只借鉴服装和角色设定，重新设计面貌。",
                   "Prepare characters, scenes and props first. Each group uses one color 9:16 storyboard. Redesign actor faces.",
                   wraplength=810).pack(anchor="w", pady=(8, 3))
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "下一步：提示词与交付", "Next: Prompts & delivery", self.enter_delivery, primary=True)

    def build_delivery(self, page):
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "预览 SD2 提示词", "Preview SD2 prompts", self.show_prompts)
        self.button(row, "生成交付预览", "Prepare delivery preview", self.prepare_delivery, primary=True)
        self.button(row, "查看选中文件", "Review selected file", self.open_delivery_file)
        self.delivery_table = self.table(page, (
            ("group", "分组", "Group", 95), ("name", "交付文件", "Delivery file", 610),
        ))
        self.delivery_table.bind("<Double-1>", lambda _event: self.guard(self.open_delivery_file))
        self.final_review = tk.BooleanVar(page)
        self.check(page, "已逐格核对画面、原语言对白、产品细节及独立人物资产",
                   "I checked panels, original dialogue, product details and individual character sheets",
                   self.final_review).pack(anchor="w", pady=(8, 4))
        row = ttk.Frame(page)
        row.pack(fill="x")
        self.button(row, "验收并导出 ZIP", "Validate & export ZIP", self.export_delivery, primary=True)

    def refresh_language(self):
        for widget, zh, en in self.labels:
            widget.configure(text=self.t(zh, en))
        for index, titles in enumerate(PHASES):
            self.steps.tab(index, text=self.t(*titles))
        for table, columns in self.tables:
            for key, zh, en, _ in columns:
                table.heading(key, text=self.t(zh, en))
        self.refresh_video()
        self.refresh_assets()

    def guard(self, operation):
        if self.busy:
            return
        try:
            operation()
        except (ValueError, OSError, RuntimeError, tk.TclError, Image.DecompressionBombError) as error:
            self.error(error)

    def error(self, error):
        self.status.set(str(error))
        messagebox.showerror(self.t("电商信息流视频复刻", "E-commerce video recreation"), str(error), parent=self.window)

    def background(self, operation, finished, zh, en):
        result = Queue()
        self.busy = True
        self.status.set(self.t(zh, en))
        controls = self.buttons + self.form_controls
        for control in controls:
            control.state(["disabled"])

        def work():
            try:
                result.put((True, operation()))
            except Exception as error:
                result.put((False, error))

        def receive():
            try:
                ok, value = result.get_nowait()
            except Empty:
                self.window.after(80, receive)
                return
            self.busy = False
            for control in controls:
                control.state(["!disabled"])
            if ok:
                self.guard(lambda: finished(value))
            else:
                self.error(value)

        Thread(target=work, daemon=True).start()
        self.window.after(80, receive)

    def load_form(self):
        self.name.set(self.project.name)
        self.product_name.set(self.project.product_name)
        self.source_product.set(self.project.source_product_name)
        self.product_required.set(self.project.product_required)
        self.product_reviewed.set(self.project.product_reviewed)
        self.refresh_video()
        self.refresh_products()
        self.refresh_shots()
        self.assets = {}
        self.refresh_assets()
        self.clear_preview()

    def form(self):
        self.project.name = self.name.get().strip()
        self.project.product_name = self.product_name.get().strip()
        self.project.source_product_name = self.source_product.get().strip()
        self.project.product_required = self.product_required.get()
        self.project.product_reviewed = self.product_reviewed.get()

    def allow_close(self):
        if self.busy:
            self.status.set(self.t("正在处理，请稍候。", "Processing. Please wait."))
            return False
        self.form()
        if self.project != self.saved:
            response = messagebox.askyesnocancel(
                self.t("电商项目尚未保存", "Unsaved ecommerce project"),
                self.t("保存当前电商项目？", "Save the current ecommerce project?"), parent=self.window)
            if response is None:
                return False
            if response:
                self.guard(self.save)
                if self.project != self.saved:
                    return False
        self.clear_preview()
        return True

    def new(self):
        if not self.allow_close():
            return
        self.project = EcommerceProject("")
        self.saved, self.path, self.info = deepcopy(self.project), None, None
        self.jobs.clear()
        self.load_form()
        self.steps.select(0)
        self.status.set(self.t("请导入参考视频。", "Import a reference video to start."))

    def project_filetypes(self):
        return ((self.t("电商视频项目", "E-commerce video project"), "*.cfecom"),)

    def open(self):
        source = filedialog.askopenfilename(parent=self.window, filetypes=self.project_filetypes())
        if not source or not self.allow_close():
            return
        path = Path(source)
        self.project = EcommerceProject.open(path)
        self.path, self.saved, self.info = path, deepcopy(self.project), None
        self.jobs.clear()
        self.load_form()
        self.steps.select(0)
        self.status.set(self.t("已打开电商项目。", "Ecommerce project opened."))

    def save(self):
        self.form()
        if not self.project.name:
            if not self.project.video_path:
                raise ValueError(self.t("请输入项目名或先导入视频。", "Name the project or import a video first."))
            self.project.name = Path(self.project.video_path).stem
            self.name.set(self.project.name)
        destination = self.path
        if not destination:
            filename = filedialog.asksaveasfilename(parent=self.window, defaultextension=".cfecom",
                                                    filetypes=self.project_filetypes())
            if not filename:
                return
            destination = Path(filename)
        self.project.save(destination)
        self.path, self.saved = destination, deepcopy(self.project)
        self.status.set(self.t(f"已保存 {destination.name}", f"Saved {destination.name}"))

    def require_path(self):
        if self.path is None:
            self.save()
        return self.path

    def video(self):
        path = Path(self.project.video_path)
        if not self.project.video_path or not path.is_file():
            raise ValueError(self.t("请先导入可从本机读取的参考视频。", "Import a reference video accessible on this device."))
        return path

    def refresh_video(self):
        if not self.project.video_path:
            self.video_status.set(self.t("导入本地参考视频，软件会在本机读取时长、视频尺寸和音轨信息。",
                                         "Import a local video to read duration, dimensions and audio-track information."))
            return
        width, height = self.project.video_width, self.project.video_height
        timeline = format_timestamp(self.project.duration_ms) if self.project.duration_ms is not None else "—"
        audio = self.t("有音轨", "Audio present") if self.project.video_has_audio else self.t("无音轨", "No audio track")
        dimensions = f"{width} × {height}" if width and height else "—"
        self.video_status.set(f"{Path(self.project.video_path).name}  ·  {timeline}  ·  {dimensions}  ·  {audio}")

    def import_video(self):
        selected = filedialog.askopenfilename(
            parent=self.window, filetypes=((self.t("视频文件", "Video files"), VIDEO_FILTER), ("All files", "*.*")))
        if not selected:
            return
        path = Path(selected).resolve()
        if (self.project.shots or self.project.assets) and not messagebox.askyesno(
            self.t("更换参考视频", "Replace source video"),
            self.t("使用新视频会清空原分镜和制作资产绑定。继续？", "Replacing the source clears shots and production asset links. Continue?"),
            parent=self.window,
        ):
            return

        def install(info):
            self.info = info
            self.project.video_path = str(path)
            self.project.duration_ms = info.duration_ms
            self.project.video_has_audio = info.has_audio
            self.project.video_width, self.project.video_height = info.width, info.height
            self.project.shots = []
            self.project.source_transcript = ""
            self.project.continuity = ""
            self.project.assets = {}
            self.product_reviewed.set(False)
            self.drop_group_assets()
            if not self.name.get():
                self.name.set(path.stem)
            self.refresh_video()
            self.refresh_shots()
            self.status.set(self.t("视频已导入。请核对自有产品照片。", "Video imported. Check the product photos."))

        self.background(lambda: inspect_video(path), install, "正在读取本地视频…", "Reading video…")

    def play_video(self):
        path = self.video()
        if os.name == "nt":
            os.startfile(str(path))
        else:
            Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])

    def preview_video(self, time_ms=0):
        path = self.video()
        self.background(lambda: preview_frame(path, time_ms), lambda preview: self.show_image(path.name, preview),
                        "正在读取参考帧…", "Reading a reference frame…")

    def product_edited(self):
        self.product_reviewed.set(False)
        self.project.assets.pop("product", None)
        self.clear_preview()

    def check_product_name(self, *_):
        if self.product_name.get().strip() != self.project.product_name:
            self.product_edited()

    def refresh_products(self):
        self.product_list.delete(0, "end")
        for reference in self.project.product_refs:
            self.product_list.insert("end", Path(reference).name)

    def import_products(self):
        files = filedialog.askopenfilenames(parent=self.window, filetypes=(IMAGE_FILTER,))
        if not files:
            return
        paths = list(dict.fromkeys([*self.project.product_refs, *(str(Path(path).resolve()) for path in files)]))

        def check_files():
            if len(paths) > 20:
                raise ValueError(self.t("每个电商项目最多合成 20 张产品参考图。", "Use at most 20 product reference photos."))
            for path in paths:
                read_reference(Path(path))
            return paths

        def add(checked):
            self.project.product_refs = checked
            self.product_edited()
            self.refresh_products()
            self.status.set(self.t("已导入产品照片，请检查所需角度。", "Product photos added. Confirm the required views."))

        self.background(check_files, add, "正在核对产品照片…", "Checking product photos…")

    def product_index(self):
        choice = self.product_list.curselection()
        if not choice:
            raise ValueError(self.t("请选择一张产品照片。", "Select a product photo."))
        return choice[0]

    def preview_product(self):
        self.show_file(Path(self.project.product_refs[self.product_index()]))

    def remove_product(self):
        self.project.product_refs.pop(self.product_index())
        self.product_edited()
        self.refresh_products()

    def require_source(self):
        self.form()
        path = self.video()
        self.project.check_product()
        return path

    def enter_shots(self):
        self.require_source()
        self.steps.select(1)

    def refresh_shots(self):
        active = self.shot_table.selection()
        self.shot_table.delete(*self.shot_table.get_children())
        for shot in self.project.shots:
            self.shot_table.insert("", "end", iid=shot.id, values=(shot.id, time_range(shot), shot.scene,
                                   shot.action.replace("\n", " ")[:130], shot.dialogue.replace("\n", " ")[:105]))
        if active and self.shot_table.exists(active[0]):
            self.shot_table.selection_set(active)
        self.group_status.set("")

    def install_shots(self, shots):
        self.project.shots = shots
        self.clear_preview()
        self.refresh_shots()

    def confirm_replacement(self):
        return not self.project.shots or messagebox.askyesno(
            self.t("替换当前分镜", "Replace current shots"),
            self.t("此操作会替换已录入的分镜。继续？", "This replaces the current shot list. Continue?"), parent=self.window)

    def detect_cuts(self):
        path = self.require_source()
        if not self.confirm_replacement():
            return

        def install(analysis):
            self.info = analysis.info
            self.install_shots([EcommerceShot(f"{index:02d}A", shot.start_ms, shot.end_ms)
                                for index, shot in enumerate(analysis.shots, 1)])
            self.steps.select(1)
            self.status.set(self.t(f"已列出 {len(self.project.shots)} 条候选分镜。请确认时间、场景、动作和对白。",
                                   f"{len(self.project.shots)} candidate shots. Confirm timing, scenes, action and dialogue."))

        self.background(lambda: analyze_video(path), install, "正在检测画面切点…", "Detecting visual cuts…")

    def import_transcript(self):
        self.require_source()
        source = filedialog.askopenfilename(parent=self.window, filetypes=(("UTF-8 TXT", "*.txt"),))
        if source:
            self.project.source_transcript = Path(source).read_text(encoding="utf-8-sig")
            self.clear_preview()
            self.inspect_text(self.t("原声对白（原文）", "Original dialogue"), self.project.source_transcript)

    def import_shots(self):
        self.require_source()
        source = filedialog.askopenfilename(parent=self.window, filetypes=(("JSON", "*.json"),))
        if source and self.confirm_replacement():
            self.install_shots(parse_shots(Path(source).read_text(encoding="utf-8-sig")))

    def export_shots(self):
        if not self.project.shots:
            raise ValueError(self.t("请先建立分镜。", "Create shots first."))
        filename = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json", filetypes=(("JSON", "*.json"),))
        if filename:
            atomic_text(Path(filename), render_shots(self.project.shots))

    def selected_shot(self):
        selected = self.shot_table.selection()
        if not selected:
            raise ValueError(self.t("请选择一条分镜。", "Select a shot."))
        return next(shot for shot in self.project.shots if shot.id == selected[0])

    def inspect_shot(self):
        shot = self.selected_shot()
        self.preview_video(((shot.start_ms or 0) + (shot.end_ms or shot.start_ms or 0)) // 2)

    def remove_shot(self):
        shot = self.selected_shot()
        if messagebox.askyesno(self.t("移除镜头", "Remove shot"), shot.id, parent=self.window):
            self.install_shots([item for item in self.project.shots if item.id != shot.id])

    def edit_continuity(self):
        self.require_source()
        panel = self.modal(self.t("公共连续性", "Shared continuity"))
        panel.geometry("720x425")
        ttk.Label(panel, text=self.t("记录入口、轴线、照明、人物服装和持续道具的状态。",
                                     "Record entrances, axis, lights, costumes and persistent props."),
                  padding=9).pack(anchor="w")
        editor = scrolledtext.ScrolledText(panel, height=12, wrap="word")
        editor.insert("1.0", self.project.continuity)
        editor.pack(fill="both", expand=True, padx=9)

        def commit():
            self.project.continuity = editor.get("1.0", "end-1c").strip()
            self.clear_preview()
            panel.destroy()

        ttk.Button(panel, text=self.t("保存公共连续性", "Save shared continuity"), command=commit).pack(
            anchor="e", padx=9, pady=8)

    def edit_shot(self, existing):
        self.require_source()
        shot = existing or EcommerceShot(self.next_shot_id())
        editor = self.modal(self.t("编辑电商分镜", "Edit ecommerce shot"))
        editor.geometry("950x655")
        top = ttk.Frame(editor, padding=10)
        top.pack(fill="x")
        id_value, start, end = (tk.StringVar(editor, value) for value in (
            shot.id, "" if shot.start_ms is None else str(shot.start_ms), "" if shot.end_ms is None else str(shot.end_ms),
        ))
        for label, value in (
            (self.t("镜号", "ID"), id_value), (self.t("起点毫秒", "Start ms"), start), (self.t("终点毫秒", "End ms"), end),
        ):
            ttk.Label(top, text=label).pack(side="left", padx=(0, 4))
            ttk.Entry(top, textvariable=value, width=11).pack(side="left", padx=(0, 10))
        product = tk.BooleanVar(editor, shot.contains_product)
        cut = tk.BooleanVar(editor, shot.scene_cut)
        ttk.Checkbutton(top, text=self.t("本镜有产品", "Product shown"), variable=product).pack(side="left", padx=3)
        ttk.Checkbutton(top, text=self.t("新场景起点", "Start a new scene"), variable=cut).pack(side="left")
        form = ttk.Frame(editor, padding=(10, 2))
        form.pack(fill="both", expand=True)
        form.columnconfigure((1, 3), weight=1)
        fields = {}
        for index, (key, zh, en) in enumerate(SHOT_FIELDS):
            column, row = (index % 2) * 2, index // 2
            ttk.Label(form, text=self.t(zh, en)).grid(row=row, column=column, sticky="nw", padx=(0, 5), pady=5)
            box = tk.Text(form, width=28, height=2, wrap="word")
            value = getattr(shot, key)
            box.insert("1.0", "\n".join(value) if isinstance(value, tuple) else value)
            box.grid(row=row, column=column + 1, sticky="ew", padx=(0, 10), pady=4)
            fields[key] = box
        ttk.Label(editor, text=self.t("时间来自原片。无法核准时留空，TXT 将标记「待剪辑」。",
                                     "Use verified source times. Leave unknown times empty.")).pack(anchor="w", padx=10)

        def commit():
            values = {key: box.get("1.0", "end-1c") for key, box in fields.items()}
            for key in ("characters", "props"):
                values[key] = tuple(line.strip() for line in values[key].splitlines() if line.strip())
            revised = replace(shot, id=id_value.get().strip(), start_ms=int(start.get()) if start.get().strip() else None,
                              end_ms=int(end.get()) if end.get().strip() else None, contains_product=product.get(),
                              scene_cut=cut.get(), **values)
            all_shots = ([revised if item.id == shot.id else item for item in self.project.shots]
                         if existing else [*self.project.shots, revised])
            if all(item.start_ms is not None for item in all_shots):
                all_shots.sort(key=lambda item: item.start_ms)
            self.install_shots(parse_shots(render_shots(all_shots)))
            self.shot_table.selection_set(revised.id)
            editor.destroy()

        ttk.Button(editor, text=self.t("保存本镜", "Save shot"), command=lambda: self.guard(commit)).pack(anchor="e", padx=12, pady=8)

    def next_shot_id(self):
        used = {shot.id for shot in self.project.shots}
        return next(f"{index:02d}A" for index in range(1, 1001) if f"{index:02d}A" not in used)

    def choose_provider(self, session, task):
        providers = tuple(session)
        if not providers:
            raise ValueError(self.t(f"请在 API 接入保存可用的{task}模型。",
                                    "Save a compatible model in API connections first."))
        if len(providers) == 1:
            return session[providers[0]]
        panel = self.modal(self.t("选择 API 服务商", "Choose an API provider"))
        form = ttk.Frame(panel, padding=14)
        form.pack()
        choice = ttk.Combobox(form, state="readonly", values=providers, width=36)
        choice.current(0)
        choice.pack(fill="x", pady=(0, 8))
        chosen = []

        def use():
            chosen.append(session[choice.get()])
            panel.destroy()

        ttk.Button(form, command=use, text=self.t("使用此模型", "Use model")).pack(anchor="e")
        self.window.wait_window(panel)
        return chosen[0] if chosen else None

    def ai_shots(self):
        from .ecommerce_video import VideoShot

        path = self.require_source()
        if not self.project.shots:
            raise ValueError(self.t("先检测切点或录入带时间的镜头。", "Detect cuts or enter timed shots first."))
        settings = self.choose_provider(self.vision_session, "审图")
        if settings is None:
            return
        selected = self.shot_table.selection()
        index = next((i for i, shot in enumerate(self.project.shots) if selected and shot.id == selected[0]), 0)
        batch = self.project.shots[index:index + 12]
        if any(shot.start_ms is None or shot.end_ms is None for shot in batch):
            raise ValueError(self.t("AI 看图需要本批镜头的实际起止时间。", "AI needs actual times for every shot in the batch."))
        windows = [VideoShot(shot.start_ms, shot.end_ms) for shot in batch]
        kwargs = {"product_name": self.project.product_name}

        def show(sheet):
            summary = preview_ecommerce_analysis(settings, sheet, batch, **kwargs)

            def submit():
                def use(result):
                    changes = {row["id"]: {key: value for key, value in row.items() if key != "id" and value}
                               for row in result}
                    draft = [replace(shot, **{key: value for key, value in changes.get(shot.id, {}).items()
                                              if not getattr(shot, key)}) for shot in self.project.shots]
                    self.install_shots(parse_shots(render_shots(draft)))
                    self.status.set(self.t("视觉草稿已填入空字段。请逐镜核对，原语言对白需对照原视频。",
                                           "Visual draft filled empty fields. Review shots and check original dialogue against the video."))

                self.background(lambda: draft_ecommerce_shots(settings, sheet, batch, **kwargs), use,
                                "正在请求 AI 视觉分镜草稿…", "Requesting a visual shot draft…")

            self.confirm_api(summary, submit, image=sheet)

        self.background(lambda: preview_sheet(path, windows), show, "正在提取本批画面…", "Extracting frames for this batch…")

    def drop_group_assets(self):
        self.project.assets = {key: value for key, value in self.project.assets.items()
                               if not key.startswith(("board:", "props:", "panel:"))}
        self.project.shot_approval = ""
        self.project.visual_approved = ""
        self.assets = {}
        self.refresh_assets()
        self.clear_preview()

    def approve_shots(self):
        self.require_source()
        groups = self.project.groups()
        key = self.project.shot_key()
        text = self.t(
            f"共 {len(self.project.shots)} 镜、{len(groups)} 组。确认时间、换场、原语言对白和每镜出现的产品已对照原片？",
            f"{len(self.project.shots)} shots in {len(groups)} groups. Confirm source timing, scene changes, original dialogue and product appearances?",
        )
        changed = bool(self.project.shot_approval and self.project.shot_approval != key)
        if changed and any(asset.startswith(("board:", "props:", "panel:")) for asset in self.project.assets):
            text += self.t("\n分组依据已变，确认后将清除旧组的故事板与道具图绑定。",
                           "\nGrouping inputs changed. Confirm to clear older group board and prop links.")
        if not messagebox.askyesno(self.t("确认当前分镜", "Approve current shot plan"), text, parent=self.window):
            return
        if changed:
            self.drop_group_assets()
        self.project.shot_approval = key
        self.group_status.set(self.t(f"{len(groups)} 个故事板组", f"{len(groups)} storyboard groups"))
        self.audit()
        self.steps.select(2)

    def require_approved(self):
        self.require_source()
        if not self.project.shot_approval or self.project.shot_approval != self.project.shot_key():
            raise ValueError(self.t("请在分镜分析确认本版后再制作资产。",
                                    "Approve the current shot plan before preparing assets."))
        return self.project.groups()

    def audit(self):
        self.require_approved()
        self.assets = {row.key: row for row in asset_audit(self.project)}
        self.refresh_assets()
        self.status.set(self.t(f"已核对 {len(self.assets)} 项交付资产。", f"Audited {len(self.assets)} delivery assets."))

    def refresh_assets(self):
        active = self.asset_table.selection()
        self.asset_table.delete(*self.asset_table.get_children())
        for row in self.assets.values():
            raw = self.project.assets.get(row.key, row.source)
            state = ("已合成预览", "Preview composed") if row.kind == "product" and raw else STATUSES[row.status]
            self.asset_table.insert("", "end", iid=row.key, values=(self.t(*KINDS[row.kind]), row.name, self.t(*state),
                                    Path(raw).name if raw else ""))
        if active and self.asset_table.exists(active[0]):
            self.asset_table.selection_set(active)

    def selected_asset(self):
        selected = self.asset_table.selection()
        if not selected:
            raise ValueError(self.t("请先选择一项资产。", "Select an asset first."))
        return self.assets[selected[0]]

    def preview_asset(self):
        row = self.selected_asset()
        path = self.project.assets.get(row.key, "")
        if not path:
            raise ValueError(self.t("这项资产还没有图片。", "No image is linked to this asset yet."))
        self.show_file(Path(path))

    def bind_asset(self, key, path):
        self.project.assets[key] = str(path)
        self.project.visual_approved = ""
        self.clear_preview()
        self.audit()
        if self.asset_table.exists(key):
            self.asset_table.selection_set(key)

    def import_asset(self):
        self.require_approved()
        row = self.selected_asset()
        if row.kind == "product":
            raise ValueError(self.t("产品总图必须由已确认的产品照片合成。", "Compose the product sheet from confirmed photos."))
        name = filedialog.askopenfilename(parent=self.window, filetypes=(IMAGE_FILTER,))
        if not name:
            return
        path = Path(name).resolve()

        def review(image):
            title = self.t("核对导入资产", "Inspect imported asset")
            self.show_image(title, image, confirm=lambda: self.bind_asset(row.key, path),
                            instruction=self.asset_review_text(row.kind))

        self.background(lambda: self.asset_image(path, row.kind), review,
                        "正在核对图像格式…", "Checking image format…")

    def asset_image(self, path, kind):
        _, _, image = read_reference(path)
        width, height = image.size
        if kind == "board":
            if width * 16 != height * 9 or width < 1080 or height < 1920:
                raise ValueError(self.t("故事板须为 9:16 彩色合板，至少 1080×1920。",
                                        "Use a color 9:16 composite at 1080×1920 or larger."))
        elif width * 9 != height * 16:
            raise ValueError(self.t("该资产图必须为 16:9。", "This asset requires a 16:9 sheet."))
        return image

    def asset_review_text(self, kind):
        return {
            "board": self.t("核对实际格数、标号、顺序、彩色画面、产品细节和人物连续性。",
                            "Check panel count, IDs, order, color, product details and continuity."),
            "character": self.t("核对同一新面貌的正面、侧面、背面全身与正面脸部特写。",
                                "Check the same redesigned face across front, side, back and frontal close-up."),
            "scene": self.t("核对单一场景的入口、光线、轴线和必要角度。", "Check this scene's entrances, light, axis and angles."),
            "props": self.t("核对关键道具，产品使用独立产品图。", "Check key props. Products use their own sheet."),
        }.get(kind, "")

    def output_folder(self):
        path = self.require_path()
        if not path:
            return None
        folder = path.with_suffix(".ecom-assets")
        folder.mkdir(exist_ok=True)
        return folder

    def make_product(self):
        self.require_approved()
        if "product" not in self.assets:
            self.audit()
        if "product" not in self.assets:
            raise ValueError(self.t("当前没有需要产品总图的分组。", "No group requires a product sheet."))
        folder = self.output_folder()
        if folder is None:
            return
        refs = self.project.check_product()
        key = "product"
        path = folder / f"product-{uuid4().hex}.png"

        def prepare():
            compose_product_sheet(refs, path)
            return self.asset_image(path, "product")

        def review(image):
            self.show_image(self.t("自有产品总图", "Your product contact sheet"), image,
                            confirm=lambda: self.bind_asset(key, path),
                            instruction=self.t("核对照片里的外形、颜色、包装和操作状态。", "Check shape, color, packaging and use states."))

        self.background(prepare, review, "正在合成产品照片…", "Composing product photos…")

    def image_context(self, row, groups):
        group = next((item for item in groups if row.key == f"{row.kind}:{item.id}"), None)
        include_product = bool(row.kind == "board" and group and group.contains_product)
        references = []
        if row.kind == "board":
            required = [] if not group else [f"scene:{group.scene}", *(f"character:{name}" for name in group.characters)]
            if group and group.props:
                required.append(f"props:{group.id}")
            for key in required:
                path = self.project.assets.get(key)
                if not path or not Path(path).is_file():
                    raise ValueError(self.t(f"请先完成故事板使用的资产：{key}。", f"Prepare the required board reference: {key}."))
                references.append(Path(path))
        context = {
            "board": lambda: render_group_prompt(self.project, group),
            "character": lambda: self.asset_description(row.name, [shot for shot in self.project.shots if row.name in shot.characters]),
            "scene": lambda: self.asset_description(row.name, [shot for shot in self.project.shots if row.name == shot.scene]),
            "props": lambda: self.asset_description(row.name, group.shots if group else ()),
        }[row.kind]()
        return context, references, include_product, tuple(shot.id for shot in group.shots) if row.kind == "board" else ()

    @staticmethod
    def asset_description(name, shots):
        return "\n".join([name, *(f"{shot.id} {shot.scene} {shot.action} {shot.positions} {shot.continuity}"
                                    for shot in shots[:12])])[:9900]

    def generate_asset(self):
        groups = self.require_approved()
        row = self.selected_asset()
        if row.kind == "product":
            self.make_product()
            return
        if row.key in self.jobs:
            raise ValueError(self.t("此资产已有提交的任务，请先查询。", "This asset has a pending job. Check its status first."))
        context, references, include_product, panel_ids = self.image_context(row, groups)
        settings = self.choose_provider(self.image_session, "生图")
        if settings is None:
            return
        folder = self.output_folder()
        if folder is None:
            return
        product_refs = self.project.check_product() if include_product else ()
        product_name = self.project.product_name
        approval = self.project.shot_approval

        def attach():
            inputs = []
            if include_product:
                with TemporaryDirectory(prefix="comicflow-product-") as tmp:
                    path = compose_product_sheet(product_refs, Path(tmp) / "product.png")
                    inputs.append(path.read_bytes())
            inputs.extend(read_reference(path)[0] for path in references)
            return {"references": tuple(inputs), "product_name": product_name,
                    "includes_product": include_product, "panel_ids": panel_ids}

        def confirm(kwargs):
            summary = preview_ecommerce_image(settings, row.kind, context, **kwargs)
            titles = ([self.t("自有产品总图", "Your product sheet")] if include_product else [])
            titles.extend(path.name for path in references)
            if titles:
                summary += "\n\n" + self.t("参考图发送顺序", "Reference upload order") + "\n" + "\n".join(titles)

            def submit():
                self.background(lambda: submit_ecommerce_image(settings, row.kind, context, **kwargs),
                                lambda reply: self.receive_image(row, settings, reply, folder, panel_ids, approval),
                                "正在请求候选图…", "Requesting an image candidate…")

            self.confirm_api(summary, submit)

        self.background(attach, confirm, "正在读取将要发送的已确认参考图…", "Reading approved inputs for the request…")

    def poll_asset(self):
        self.require_approved()
        row = self.selected_asset()
        pending = self.jobs.get(row.key)
        if pending is None:
            raise ValueError(self.t("当前没有这项资产的图像任务。", "There is no pending job for this asset."))
        settings, job, folder, ids, approval = pending
        self.background(lambda: query_image(settings, job),
                        lambda reply: self.receive_image(row, settings, reply, folder, ids, approval, previous_id=job),
                        "正在查询图像任务…", "Checking image job…")

    def receive_image(self, row, settings, reply, folder, panel_ids, approval, *, previous_id=""):
        if reply.status == "failed":
            self.jobs.pop(row.key, None)
            raise ValueError(self.t("服务商报告生图任务失败。", "The provider reported an image job failure."))
        if not reply.results and (reply.task_id or previous_id):
            task_id = reply.task_id or previous_id
            self.jobs[row.key] = settings, task_id, folder, panel_ids, approval
            self.status.set(self.t(f"图像暂未完成，请稍后查询任务 {task_id}。",
                                   f"The image is pending. Check job {task_id} again later."))
            return
        self.jobs.pop(row.key, None)
        if not reply.results:
            raise ValueError(self.t("服务没有返回可用图像。", "The provider returned no usable image."))
        if approval != self.project.shot_approval or approval != self.project.shot_key():
            raise ValueError(self.t("此候选图对应旧分镜，无法绑定到当前项目。", "This candidate belongs to an earlier shot plan."))
        path = folder / f"{row.kind}-{uuid4().hex}.png"

        def prepare():
            with Image.open(BytesIO(reply.results[0])) as source:
                source.load()
                image = source.copy()
            if row.kind == "board":
                with TemporaryDirectory(prefix="comicflow-board-") as tmp:
                    raw = Path(tmp) / "candidate.png"
                    image.save(raw, "PNG")
                    label_board_sheet(raw, path, panel_ids)
            else:
                image.save(path, "PNG")
            return self.asset_image(path, row.kind)

        def review(image):
            self.show_image(self.t("核对候选图", "Review candidate"), image,
                            confirm=lambda: self.bind_asset(row.key, path), instruction=self.asset_review_text(row.kind))

        self.background(prepare, review, "正在检查候选图…", "Checking the image candidate…")

    def enter_delivery(self):
        self.require_approved()
        self.steps.select(3)

    def show_prompts(self):
        groups = self.require_approved()
        text = "\n\n".join(f"=== {group.id} ===\n{render_group_prompt(self.project, group)}" for group in groups)
        self.inspect_text(self.t("Seedance 2.0 提示词", "Seedance 2.0 prompts"), text)

    def clear_preview(self):
        self.staged = None
        self.final_review.set(False)
        self.delivery_table.delete(*self.delivery_table.get_children())
        if self.stage_folder is not None:
            self.stage_folder.cleanup()
            self.stage_folder = None

    def prepare_delivery(self):
        self.require_approved()
        self.clear_preview()
        project = deepcopy(self.project)

        def stage():
            folder = TemporaryDirectory(prefix="comicflow-ecommerce-")
            try:
                preview = stage_ecommerce_delivery(project, Path(folder.name))
                return folder, preview, project.review_key()
            except Exception:
                folder.cleanup()
                raise

        def review(value):
            self.stage_folder, self.staged, self.stage_key = value
            for path in sorted(self.staged.folder.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(self.staged.folder)
                    current = relative.parts[0] if len(relative.parts) > 1 else "—"
                    self.delivery_table.insert("", "end", iid=relative.as_posix(),
                                               values=(current, "/".join(relative.parts[1:]) if current != "—" else relative.name))
            self.status.set(self.t("交付预览已准备。打开文件核对全组图像、格号和文字。",
                                   "Delivery preview is ready. Review all sheets, panel IDs and text."))

        self.background(stage, review, "正在组织分组并校验预览…", "Preparing and validating the delivery preview…")

    def open_delivery_file(self):
        selected = self.delivery_table.selection()
        if not selected or self.staged is None:
            raise ValueError(self.t("请在交付清单选择要查看的文件。", "Select a file in the delivery preview."))
        path = self.staged.folder / selected[0]
        if path.suffix.casefold() == ".txt":
            self.inspect_text(path.name, path.read_text(encoding="utf-8-sig"))
        else:
            self.show_file(path)

    def export_delivery(self):
        self.require_approved()
        if not self.staged or not self.final_review.get():
            raise ValueError(self.t("请先生成交付预览并逐项复核。", "Prepare and review the delivery preview first."))
        selection = filedialog.asksaveasfilename(
            parent=self.window, defaultextension=".zip", initialfile=f"{APP_FOLDER}-Ecommerce.zip",
            filetypes=(("ZIP", "*.zip"),),
        )
        if not selection:
            return
        destination = Path(selection)
        staged = self.staged
        view_key = self.stage_key
        snapshot = deepcopy(self.project)

        def publish():
            if snapshot.review_key() != view_key:
                raise ValueError(self.t("项目图片或分镜发生变化，请重新生成交付预览。",
                                        "Source images or shots changed. Create a fresh delivery preview."))
            return publish_ecommerce_delivery(staged, destination, visual_approval=staged.fingerprint)

        def finish(result):
            self.project.visual_approved = view_key
            self.status.set(self.t(f"已通过验收并导出：{result.output.name}", f"Validated and exported: {result.output.name}"))
            self.inspect_text(self.t("交付完成", "Delivery exported"), f"{result.output}\n\nSHA-256\n{result.sha256}")

        self.background(publish, finish, "正在验收并写入 ZIP…", "Validating and writing the ZIP…")

    def modal(self, title):
        panel = tk.Toplevel(self.window)
        panel.title(title)
        panel.transient(self.window)
        panel.grab_set()
        return panel

    def inspect_text(self, title, body):
        panel = self.modal(title)
        panel.geometry("800x640")
        self.text_widget(panel, body)
        ttk.Button(panel, text=self.t("关闭", "Close"), command=panel.destroy).pack(anchor="e", padx=10, pady=8)

    def text_widget(self, parent, body):
        box = scrolledtext.ScrolledText(parent, wrap="word", height=18)
        box.insert("1.0", body)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=9, pady=(7, 0))
        return box

    def confirm_api(self, body, submit, *, image=None):
        panel = self.modal(self.t("预览 API 请求", "Preview API request"))
        panel.geometry("900x685")
        if image is not None:
            preview = image.copy()
            preview.thumbnail((550, 345))
            picture = ttk.Label(panel)
            picture.image = ImageTk.PhotoImage(preview, master=panel)
            picture.configure(image=picture.image)
            picture.pack(pady=5)
        self.text_widget(panel, body)
        row = ttk.Frame(panel, padding=8)
        row.pack(anchor="e")
        ttk.Button(row, text=self.t("取消", "Cancel"), command=panel.destroy).pack(side="left", padx=6)

        def proceed():
            panel.destroy()
            self.guard(submit)

        ttk.Button(row, text=self.t("确认发送，使用所选 API 额度", "Confirm and use provider credits"),
                   command=proceed).pack(side="left")

    def show_file(self, path):
        self.background(lambda: read_reference(path)[2], lambda image: self.show_image(path.name, image),
                        "正在打开图像…", "Opening image…")

    def show_image(self, title, image, *, confirm=None, instruction=""):
        panel = self.modal(title)
        panel.geometry("850x710")
        panel.minsize(540, 400)
        if instruction:
            ttk.Label(panel, text=instruction, wraplength=770, padding=8).pack(anchor="w")
        row = ttk.Frame(panel, padding=8)
        row.pack(side="bottom", fill="x")
        factor = tk.BooleanVar(panel)

        canvas_frame = ttk.Frame(panel)
        canvas_frame.pack(fill="both", expand=True, padx=8)
        canvas = tk.Canvas(canvas_frame, background="#17222e", highlightthickness=0)
        vertical = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        horizontal = ttk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        canvas.pack(fill="both", expand=True)
        fitted = None

        def fit(_event=None):
            nonlocal fitted
            bounds = (canvas.winfo_width() - 8, canvas.winfo_height() - 8)
            if min(bounds) <= 1:
                return
            mode = factor.get()
            if (mode, bounds) == fitted:
                return
            display = image.copy()
            if not mode:
                display.thumbnail(bounds)
            fitted = mode, bounds
            canvas.preview = ImageTk.PhotoImage(display, master=panel)
            canvas.delete("all")
            canvas.create_image(0, 0, image=canvas.preview, anchor="nw")
            canvas.configure(scrollregion=(0, 0, display.width, display.height))

        ttk.Checkbutton(row, text=self.t("按原尺寸查看", "Full resolution"), variable=factor, command=fit).pack(side="left")
        ttk.Button(row, text=self.t("关闭", "Close"), command=panel.destroy).pack(side="right")
        if confirm is not None:
            def accept():
                panel.destroy()
                self.guard(confirm)

            ttk.Button(row, text=self.t("确认使用这张图", "Approve and use this image"), command=accept).pack(side="right", padx=5)
        canvas.bind("<Configure>", fit)
