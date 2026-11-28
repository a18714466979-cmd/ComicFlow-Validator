"""Local authoring and delivery window for an SD2 storyboard group."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryDirectory
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from zipfile import ZipFile

from PIL import Image, ImageTk

from .ui_language import translate, window_title
from .asset_registry import AssetRegistry, sha256_file
from .bundled_validators import bundled_validator
from .camera_preflight import camera_findings_text, project_camera_cuts
from .guide_links import guide_button
from .production_drafting import SD2_TASK, SHOT_TASK
from .production_export import (
    chinese_text_records, preview_chinese_layout, preview_project, project_registry, publish_project,
    render_dialogue, write_chinese_layout, write_chinese_texts,
)
from .production_flow import asset_shot_context, shot_sources
from .production_project import ACTIONS, PARENT_SHOT_FIELD, PROMPT_FIELDS, SHOT_FIELDS, ProductionProject, Shot
from .production_rules import CHINESE, DELIVERY_TARGET, ENGLISH, RULE_LABELS, rule_revision
from .shot_review_dialog import open_shot_review
from .storyboard_review import ReviewResult, index_members
from .storyboard_preflight import IMAGE_LIMIT


def project_filetypes(widget):
    return ((translate(widget, "单组制作项目"), "*.cfproject"),)


def choose_project_file(parent):
    return filedialog.askopenfilename(
        parent=parent, title=translate(parent, "打开已保存的项目（.cfproject）"),
        filetypes=project_filetypes(parent),
    )


def write_text(widget, value):
    widget.delete("1.0", "end")
    widget.insert("1.0", value)


def fields_text(fields, values):
    return "\n".join(f"{key}：{values.get(key, '')}" for key in fields)


def read_fields(widget, fields):
    values = {}
    key = None
    for number, row in enumerate(widget.get("1.0", "end").splitlines(), 1):
        if not row.strip():
            continue
        label, separator, value = row.partition("：")
        if separator and label in fields and label not in values:
            key = label
            values[key] = value.strip()
        elif key and row.startswith("- "):
            values[key] += "\n" + row.strip()
        else:
            raise ValueError(f"表单第 {number} 行需使用模板字段或「- 」续行。")
    return {key: value.strip() for key, value in values.items() if value.strip()}


def caption(widget, text):
    widget._production_caption = text
    widget.configure(text=translate(widget, text))
    return widget


def refresh_captions(widget):
    for child in widget.winfo_children():
        if hasattr(child, "_production_caption"):
            child.configure(text=translate(child, child._production_caption))
        refresh_captions(child)


def field(parent, row, label, value, choices=None):
    caption(ttk.Label(parent), label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
    if choices is None:
        widget = ttk.Entry(parent, textvariable=value)
    else:
        widget = ttk.Combobox(parent, textvariable=value, values=choices, state="readonly")
    widget.grid(row=row, column=1, sticky="ew", pady=3)
    parent.columnconfigure(1, weight=1)
    return widget


class ProductionDialog:
    def __init__(self, parent, validators, registry, text_session, image_session, rules, on_rules_changed,
                 *, embedded=False, destination="group", on_save=None, on_stage=None, with_panel=True):
        self.validators = validators
        self.rules = rules
        self.on_rules_changed = on_rules_changed
        self.registry = registry
        self.text_session = text_session
        self.image_session = image_session
        self.project = None
        self.path = None
        self.previewed = None
        self.action_workspace = None
        self.embedded = embedded
        self.with_panel = with_panel
        self.destination = destination
        self.on_save = on_save
        self.on_stage = on_stage
        self.overlay = None
        self.overlay_has_form = False
        self._baseline = None
        self.source_ids = ()
        if embedded:
            self.window = parent.winfo_toplevel()
            self.frame = ttk.Frame(parent, name="production_panel")
            if with_panel:
                self.frame.pack(fill="both", expand=True)
        else:
            self.window = tk.Toplevel(parent)
            self.window.title(window_title(self.window, "单组制片"))
            self.window.geometry("1050x745")
            self.window.minsize(820, 610)
            self.window.transient(parent)
            self.window.grab_set()
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            self.frame = self.window
        self.body = ttk.Frame(self.frame)
        self.body.pack(fill="both", expand=True)
        top = ttk.Frame(self.body, padding=10)
        top.pack(fill="x")
        if embedded:
            self.file_buttons = self.buttons(top, ("保存项目", self.save))
            self.production_tools = tuple(self.build_stage_links(top))
        else:
            self.file_buttons = self.buttons(top, ("新建单组项目", self.create), ("打开单组项目", self.open),
                                             ("保存项目", self.save))
            help_button = guide_button(top, "project")
            if help_button is not None:
                help_button.pack(side="right")
            guides = ttk.Frame(self.body, padding=(10, 0, 10, 8))
            guides.pack(fill="x")
            self.production_tools = self.buttons(
                guides, ("对白与分镜起草", self.open_drafting),
                ("图像制片", self.open_image_production),
                ("排版与交接", self.open_layout),
                ("写提示词", lambda: self.open_drafting(task=SD2_TASK)),
                ("复核与打包", lambda: self.tabs.select(3)),
            )
            ttk.Label(self.body, text=translate(self.body, DELIVERY_TARGET), padding=(10, 0, 10, 5)).pack(anchor="w")
        self.status = tk.StringVar(self.window, translate(self.window, "新建或打开项目后开始。"))
        info = ttk.Frame(self.body, padding=(10, 0, 10, 6))
        info.pack(fill="x")
        self.rule_name = tk.StringVar(self.window)
        ttk.Label(info, textvariable=self.rule_name).pack(side="left")
        ttk.Label(info, textvariable=self.status).pack(side="left", padx=8)
        self.tabs = ttk.Notebook(self.body)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.setup_group(self.tab("项目与组"))
        self.setup_shots(self.tab("镜头清单"))
        self.setup_images(self.tab("批准图像"))
        self.setup_delivery(self.tab("复核与交付"))
        if self.embedded and self.destination == "prompts":
            self.setup_prompt(self.tab("提示词生成"))
        for index in range(len(self.tabs.tabs())):
            self.tabs.tab(index, state="disabled")
        self.show_rules(rules)

    def build_stage_links(self, parent):
        if self.on_stage is None:
            return ()
        links = {
            "group": (("下一步：拆分镜", "shots"),),
            "shots": (("项目与组", "group"),),
            "assets": (("制作资产图", "generate_assets"),),
            "deliver": (("批准图像", "assets"), ("排版与交接", "layout")),
        }
        return self.buttons(parent, *((label, lambda target=target: self.open_stage(target))
                                       for label, target in links.get(self.destination, ())))

    def open_stage(self, destination, **options):
        self.save()
        return self.on_stage(destination, **options)

    def guarded(self, task):
        try:
            task()
        except Exception as exc:
            messagebox.showerror(translate(self.window, "单组制片"), translate(self.window, str(exc)), parent=self.window)

    def buttons(self, bar, *buttons):
        built = []
        for title, command in buttons:
            button = caption(ttk.Button(bar, command=lambda task=command: self.guarded(task)), title)
            button.pack(side="left", padx=(0, 6))
            built.append(button)
        return built

    def show_rules(self, rules):
        self.rules = rules
        self.rule_name.set(f"{translate(self.window, RULE_LABELS[rules])} · v{rule_revision(rules)}")
        chinese = rules == CHINESE
        has_project = self.project is not None
        self.tabs.tab(3, text=translate(self.tabs, "文本与排版" if chinese else "复核与交付"))
        if not self.embedded:
            self.tabs.tab(3, state="normal" if has_project else "disabled")
        for button in self.production_tools:
            button.state(["!disabled"] if has_project else ["disabled"])
        self.english_delivery.pack_forget()
        self.chinese_delivery.pack_forget()
        (self.chinese_delivery if chinese else self.english_delivery).pack(fill="x")

    def tab(self, name):
        page = ttk.Frame(self.tabs, padding=10)
        page._production_tab_caption = name
        self.tabs.add(page, text=translate(self.tabs, name))
        return page

    def refresh_language(self):
        refresh_captions(self.frame)
        for page_id in self.tabs.tabs():
            page = self.tabs.nametowidget(page_id)
            title = page._production_tab_caption
            if title == "复核与交付" and self.rules == CHINESE:
                title = "文本与排版"
            self.tabs.tab(page_id, text=translate(self.tabs, title))
        self.rule_name.set(f"{translate(self.window, RULE_LABELS[self.rules])} · v{rule_revision(self.rules)}")
        for table in (self.shots, self.images):
            for key in table["columns"]:
                table.heading(key, text=translate(table, key))
        if self.project is not None:
            self.show_shot_source()

    def editor(self, parent, height=8, *, name=None):
        names = {"name": name} if name else {}
        return scrolledtext.ScrolledText(parent, height=height, width=55, wrap="word", undo=True, **names)

    def setup_group(self, page):
        top = ttk.Frame(page)
        top.pack(fill="x")
        self.name, self.episode, self.group = (tk.StringVar(self.window) for _ in range(3))
        for row, (label, value) in enumerate((("项目名", self.name), ("集次", self.episode), ("组号", self.group))):
            field(top, row, label, value)
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=8)
        self.buttons(bar, ("导入批准剧本", self.import_source), ("查看原文和对白 ID", self.view_source),
                     ("编辑本组批准对白 JSON", self.import_dialogue))
        self.source = ttk.Combobox(bar, state="readonly", width=30)
        self.source.pack(side="left", expand=True, fill="x")
        caption(ttk.Label(page), "制片记录 · 必填项按交付规则填写，可用「- 」追加行").pack(anchor="w")
        self.notes = self.editor(page, 18)
        self.notes.pack(fill="both", expand=True)
        if self.destination != "prompts" or not self.embedded:
            caption(ttk.Label(page), "SD2 公共说明 · 填写成片环境与约束").pack(anchor="w", pady=(8, 0))
            self.prompt = self.editor(page, 5)
            self.prompt.pack(fill="both")

    def setup_prompt(self, page):
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 8))
        self.buttons(bar, ("导入提示词 TXT / Markdown", self.import_prompt),
                     ("调用模型起草提示词", lambda: self.open_drafting(task=SD2_TASK)))
        hint = "SD2 公共说明 · 填写成片环境与约束"
        caption(ttk.Label(page), hint).pack(anchor="w", pady=(0, 5))
        self.prompt = self.editor(page, 12, name="production_prompt")
        self.prompt.pack(fill="both", expand=True)

    def import_prompt(self):
        value = filedialog.askopenfilename(parent=self.window,
                                           filetypes=((translate(self.window, "文本"), "*.txt *.md *.markdown"),))
        if not value:
            return
        content = Path(value).read_text(encoding="utf-8-sig").strip()
        if not content:
            raise ValueError("所选提示词文件为空。")
        before = self.prompt.get("1.0", "end-1c")
        if before.strip() != fields_text(PROMPT_FIELDS, {}).strip() and not messagebox.askyesno(
                translate(self.window, "提示词生成"), translate(self.window, "用导入文本替换当前 SD2 公共说明？"),
                parent=self.window):
            return
        if any(line.startswith(tuple(f"{key}：" for key in PROMPT_FIELDS)) for line in content.splitlines()):
            write_text(self.prompt, content)
        else:
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            content = f"{PROMPT_FIELDS[0]}：{lines[0]}" + "".join(f"\n- {line}" for line in lines[1:])
            write_text(self.prompt, f"{content}\n{PROMPT_FIELDS[1]}：")
        try:
            read_fields(self.prompt, PROMPT_FIELDS)
        except ValueError:
            write_text(self.prompt, before)
            raise

    def setup_shots(self, page):
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 8))
        self.buttons(bar, ("导入批准剧本", self.import_source), ("插入镜头", lambda: self.edit_shot(insert=True)), ("编辑镜头", self.edit_shot),
                     ("上移", lambda: self.move(-1)), ("下移", lambda: self.move(1)), ("删除镜头", self.remove_shot))
        flow = ttk.Frame(page)
        flow.pack(fill="x", pady=(0, 8))
        self.buttons(flow, ("AI 拆分镜", lambda: self.open_drafting(task=SHOT_TASK)),
                     ("人物动作编排", self.open_action_sequence),
                     ("景别与角度预检", self.show_camera_review),
                     ("下一步：分析资产", self.open_assets_for_shots))
        self.shot_source = tk.StringVar(page)
        ttk.Label(page, textvariable=self.shot_source, wraplength=740).pack(anchor="w", pady=(0, 6))
        self.source.bind("<<ComboboxSelected>>", lambda _event: self.show_shot_source())
        if self.embedded:
            self.shot_version = ttk.Combobox(page, name="production_shot_source", state="readonly", width=45)
            self.shot_version.pack(anchor="w", pady=(0, 8))
            self.shot_version.bind("<<ComboboxSelected>>", self.use_shot_source)
        self.shots = self.table(page, ("镜号", "源段", "净板文件", "对白 ID"), (85, 265, 240, 140))
        self.shots.bind("<Double-1>", lambda _event: self.guarded(self.edit_shot))
        ttk.Label(page, text=translate(page, "镜号和净板局部号按播放顺序生成。移动或插入后，在复核窗口重新核对故事板格与场景图的局部标签。")).pack(anchor="w", pady=(8, 0))

    def setup_images(self, page):
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 8))
        library_button, *_ = self.buttons(
            bar, ("打开素材库", self.open_media_library), ("导入批准 PNG", self.import_image),
            ("从资产登记库导入", self.pick_registered), ("打开图片", self.view_image),
            ("移除图片绑定", self.remove_image),
        )
        library_button.configure(style="Primary.Workbench.TButton")
        tip = "在素材库预览、分类图片和视频。用「导入批准 PNG」登记制片与交付所需的批准图片。"
        ttk.Label(page, text=translate(page, tip), wraplength=690).pack(anchor="w", pady=(0, 7))
        self.images = self.table(page, ("文件名", "范围", "版本", "处理方式", "尺寸"), (335, 100, 65, 135, 100))
        self.images.bind("<Double-1>", lambda _event: self.guarded(self.view_image))

    def open_media_library(self, *, selected=None, direct=False):
        from .media_gallery import open_media_gallery
        from .production_media import project_media_catalog, project_media_items

        english = getattr(self.window._root(), "ui_language", "zh") == "en"
        items = project_media_items(self.project, self.path, english=english)
        catalog = project_media_catalog(self.path)
        title = translate(self.window, "项目素材库")
        selected = self.images.selection() if selected is None else selected
        if not self.embedded:
            return open_media_gallery(self.window, items, catalog=catalog, selected=selected, allow_import=True, title=title)
        panel = self.subpanel(title, header=False)
        try:
            return open_media_gallery(self.window, items, catalog=catalog, selected=selected, allow_import=not direct,
                                      title=title, native_only=direct, open_selected=direct, mount=panel,
                                      on_close=panel.destroy)
        except Exception:
            panel.destroy()
            raise

    def setup_delivery(self, page):
        forms = ttk.Frame(page)
        forms.pack(fill="x")
        common = ttk.Frame(forms)
        common.pack(fill="x")
        self.english_delivery = ttk.Frame(forms)
        self.chinese_delivery = ttk.Frame(forms)
        form = ttk.Frame(self.english_delivery)
        form.pack(fill="x")
        self.baseline, self.exception = (tk.StringVar(self.window) for _ in range(2))
        field(common, 0, "原包比对（可选）", self.baseline)
        ttk.Button(common, text=translate(common, "浏览"), command=lambda: self.choose(self.baseline, "*.zip")).grid(row=0, column=2, padx=5)
        field(form, 0, "批准格数例外（可选）", self.exception)
        ttk.Button(form, text=translate(form, "浏览"), command=lambda: self.choose(self.exception, "*.json")).grid(row=0, column=2, padx=5)
        bar = ttk.Frame(self.english_delivery)
        bar.pack(fill="x", pady=8)
        self.buttons(bar, ("对白与图数预检", self.preflight), ("生成逐格复核预览", self.preview),
                     ("确认本版画面", self.confirm), ("验收并导出 ZIP", self.publish))
        ttk.Label(self.english_delivery, wraplength=680, text=translate(self.english_delivery,
                  "按源镜 ID 逐格对照批准分镜、实际板格和 SD2，检查景别、角度、入画人物、动作和对白。并排核对相邻格及跨板末格与首格；缺图时记下待核镜号。")).pack(anchor="w")
        text_bar = ttk.Frame(self.chinese_delivery)
        text_bar.pack(fill="x", pady=5)
        self.buttons(text_bar, ("预览两份 TXT", self.preview_chinese_text), ("导出两份 TXT", self.export_chinese_text))
        self.buttons(text_bar, ("逐格复核排版", self.review_chinese_layout), ("导出排版图与 TXT", self.export_chinese_layout))
        delivery_bar = ttk.Frame(self.chinese_delivery)
        delivery_bar.pack(fill="x", pady=(0, 5))
        self.buttons(delivery_bar, ("正式交付预览", self.preview), ("确认本版画面", self.confirm),
                     ("验收并导出 ZIP", self.publish))
        ttk.Label(self.chinese_delivery, text=translate(self.chinese_delivery, "先核对正式交付预览，再用中文版校验脚本验收并导出 ZIP。")).pack(anchor="w")
        self.report = self.editor(page, 18)
        self.report.pack(fill="both", expand=True, pady=(5, 0))

    def table(self, parent, columns, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        table = ttk.Treeview(frame, show="headings", columns=columns, selectmode="browse")
        scroll = ttk.Scrollbar(frame, command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        for title, width in zip(columns, widths):
            table.heading(title, text=translate(table, title))
            table.column(title, width=width)
        scroll.pack(side="right", fill="y")
        table.pack(fill="both", expand=True)
        return table

    def choose(self, variable, pattern):
        selected = filedialog.askopenfilename(parent=self.window, filetypes=((pattern, pattern),))
        if selected:
            variable.set(selected)

    def update_group(self):
        if self.project is None or not self.with_panel:
            return
        if not self.embedded or self.destination == "group":
            self.project.notes = read_fields(self.notes, self.group_form_fields)
            self.project.name, self.project.episode, self.project.group = (
                item.get().strip() for item in (self.name, self.episode, self.group)
            )
            self.project.group = self.project.group.upper()
        if not self.embedded or self.destination in {"group", "prompts"}:
            self.project.prompt = read_fields(self.prompt, PROMPT_FIELDS)

    def dirty(self):
        if self.project is None:
            return False
        if self.overlay is not None and self.overlay.winfo_exists() and self.overlay_has_form:
            return True
        try:
            self.update_group()
        except ValueError:
            return True
        return self.project != self._baseline

    def save(self):
        if not self.project:
            raise ValueError("请先新建或打开项目。")
        if self.overlay is not None and self.overlay.winfo_exists() and self.overlay_has_form:
            raise ValueError("请先应用或取消当前表单，再保存项目。")
        self.update_group()
        if self.on_save is not None:
            merged = self.on_save(self._baseline, self.project)
            self.adopt_project(merged)
        else:
            self.project.save(self.path)
            self._baseline = deepcopy(self.project)
        self.status.set(f"已保存 {self.path.name}")
        self.show_impacts()
        return True

    def latest_project(self):
        return ProductionProject.open(self.path)

    def adopt_project(self, project):
        # Drafting, image and layout panels keep a reference to this controller's object.
        self.project.__dict__.update(deepcopy(vars(project)))
        self._baseline = deepcopy(self.project)
        self.refresh_fields()
        self.refresh_sources(self.selected_source_id())
        self.refresh()

    def sync_project(self, project=None):
        if self.dirty():
            return False
        if project is None:
            project = self.latest_project()
        if project != self.project:
            self.adopt_project(project)
        return True

    def allow_leave(self):
        if not self.project:
            return True
        try:
            self.update_group()
            saved = ProductionProject.open(self.path)
            if saved.fingerprint() == self.project.fingerprint() and saved.structure_review == self.project.structure_review:
                return True
        except (ValueError, OSError):
            pass
        result = messagebox.askyesnocancel(translate(self.window, "尚有项目更改"), translate(self.window, "离开前保存项目？"), parent=self.window)
        if result:
            self.save()
        return result is not None

    def close(self):
        self.guarded(lambda: self.window.destroy() if self.allow_leave() else None)

    def create(self):
        if not self.allow_leave():
            return
        value = filedialog.asksaveasfilename(
            parent=self.window, title=translate(self.window, "保存新建的单组项目"),
            filetypes=project_filetypes(self.window),
            defaultextension=".cfproject",
        )
        if value:
            path = Path(value)
            if path.exists():
                raise ValueError("这个项目文件已存在，请选择新文件名。")
            project = ProductionProject(path.stem, "EP01", "SB01", rules=self.rules)
            project.save(path)
            self.load(project, path)

    def open(self):
        if not self.allow_leave():
            return
        value = choose_project_file(self.window)
        if value:
            path = Path(value)
            self.load(ProductionProject.open(path), path)

    def open_tool_project(self, path, destination):
        """Keep Tk responsive while reading a selected, possibly synced project."""
        result = Queue()
        root = self.window._root()
        self.status.set(translate(self.window, "正在打开项目…") + f" {path.name}")
        self.window.configure(cursor="watch")
        for button in self.file_buttons:
            button.state(["disabled"])

        def read():
            try:
                project = ProductionProject.open(path)
                result.put((project, project_registry(path).is_file()))
            except Exception as exc:
                result.put(exc)

        def receive():
            if not self.window.winfo_exists():
                return
            try:
                loaded = result.get_nowait()
            except Empty:
                root.after(50, receive)
                return
            self.window.configure(cursor="")
            for button in self.file_buttons:
                button.state(["!disabled"])

            def launch():
                if isinstance(loaded, Exception):
                    self.status.set(translate(self.window, "项目打开失败。"))
                    raise loaded
                project, has_registry = loaded
                self.load(project, path, has_registry=has_registry)
                self.go_to(destination)

            self.guarded(launch)

        Thread(target=read, daemon=True).start()
        root.after(50, receive)

    def load(self, project, path, *, source_id="", has_registry=None):
        self.project, self.path, self.previewed = (deepcopy(project) if self.embedded else project), path, None
        self._baseline = deepcopy(self.project)
        self.show_rules(project.rules)
        self.on_rules_changed(project.rules)
        self.refresh_fields()
        self.baseline.set("")
        self.exception.set("")
        if self.embedded:
            chosen_tab = {"group": 0, "shots": 1, "assets": 2, "deliver": 3, "prompts": 4}.get(self.destination, 0)
            self.tabs.tab(chosen_tab, state="normal")
            self.tabs.select(chosen_tab)
            for index in range(len(self.tabs.tabs())):
                if index != chosen_tab:
                    self.tabs.hide(index)
        else:
            for index in range(3):
                self.tabs.tab(index, state="normal")
            self.tabs.select(0)
        self.refresh_sources(source_id)
        self.refresh()
        registry = project_registry(path)
        if has_registry is None:
            has_registry = registry.is_file()
        if has_registry:
            self.registry.set(str(registry))
        self.status.set(path.name)

    def refresh_fields(self):
        project = self.project
        for variable, value in zip((self.name, self.episode, self.group), (project.name, project.episode, project.group)):
            variable.set(value)
        self.group_form_fields = project.group_fields
        for editor, content in ((self.notes, fields_text(self.group_form_fields, project.notes)),
                                (self.prompt, fields_text(PROMPT_FIELDS, project.prompt))):
            if editor.get("1.0", "end-1c") != content:
                write_text(editor, content)

    def selected_source_id(self):
        index = self.source.current()
        if 0 <= index < len(self.source_ids):
            return self.source_ids[index]
        return ""

    def go_to(self, destination, *, adjacent_path=None):
        if destination in {"layout", "handoff"}:
            self.tabs.select(2)
            self.open_layout(adjacent_path=adjacent_path)
        elif destination == "prompts":
            self.tabs.select(1)
            self.open_drafting(task=SD2_TASK)
        elif destination in {"generate_assets", "generate_board"}:
            self.tabs.select(2)
            self.open_image_production(kind="故事板" if destination == "generate_board" else "角色",
                                       save_project=False)
        elif destination in {"costume", "pose"}:
            self.tabs.select(2)
            self.open_reference_design(destination)
        elif destination == "action_sequence":
            self.tabs.select(1)
            self.open_action_sequence()
        elif destination == "deliver":
            self.tabs.select(3)
            script = self.validators[self.rules]
            if script and Path(script).expanduser().is_file() and not self.project.impacts():
                self.publish()
        else:
            self.tabs.select({"group": 0, "shots": 1, "assets": 2, "review": 3}[destination])

    def refresh_sources(self, preferred=""):
        sources = self.project.sources
        self.source_ids = tuple(source.id for source in sources)
        self.source["values"] = tuple(f"{source.name} · {source.version}" for source in sources)
        if sources:
            index = next((i for i, source in enumerate(sources) if source.id == preferred), len(sources) - 1)
            self.source.current(index)
        else:
            self.source.set("")
        if self.embedded:
            self.shot_version["values"] = self.source["values"]
            self.shot_version.set(self.source.get())
        self.show_shot_source()

    def use_shot_source(self, _event=None):
        self.source.current(self.shot_version.current())
        self.show_shot_source()

    def show_shot_source(self):
        caption = translate(self.window, "当前分镜源稿") if self.source.get() else translate(self.window, "分镜前请导入批准剧本。")
        self.shot_source.set(f"{caption} · {self.source.get()}" if self.source.get() else caption)

    def current_source(self):
        index = self.source.current()
        if index < 0:
            raise ValueError("请先导入并选择批准剧本。")
        return self.project.sources[index]

    def import_source(self):
        value = filedialog.askopenfilename(parent=self.window, filetypes=(("UTF-8 剧本", "*.txt *.md"),))
        if value:
            version = simpledialog.askstring(translate(self.window, "批准剧本版本"), translate(self.window, "输入版本号，例如 R5"), parent=self.window)
            if version is not None:
                path = Path(value)
                source = self.project.import_source(path.name, version, path.read_text(encoding="utf-8-sig"))
                self.refresh_sources(source.id)

    def show_text(self, title, content):
        dialog = self.subpanel(title, "760x550")
        editor = self.editor(dialog)
        editor.pack(fill="both", expand=True, padx=10, pady=10)
        write_text(editor, content)
        editor.configure(state="disabled")
        self.wait(dialog)

    def view_source(self):
        source = self.current_source()
        dialogue = "\n".join(f"{line.id}  {line.speaker}  {line.text}" for line in self.project.lines if line.source == source.id)
        self.show_text(f"{source.name} · {source.version}", f"本组批准对白\n{dialogue or '尚未导入'}\n\n批准剧本原文\n{source.text}")

    def import_dialogue(self):
        source = self.current_source()
        panel = self.subpanel(translate(self.window, "导入本组批准对白"), form=True)
        boundary = "自然停顿切点" if self.rules == CHINESE else "整句分界"
        ttk.Label(panel, text=f"粘贴或打开批准对白 JSON。可用 sentence_ends 标同一 ID 的{boundary}。").pack(padx=10, pady=6)
        editor = self.editor(panel, 12)
        editor.pack(fill="both", expand=True, padx=10)
        lines = [{"id": line.id, "speaker": line.speaker, "text": line.text}
                 for line in self.project.lines if line.source == source.id]
        by_id = {line.id: line for line in self.project.lines}
        for row in lines:
            ends = by_id[row["id"]].sentence_ends
            if ends:
                row["sentence_ends"] = list(ends)
        example = "等一下。" if self.rules == CHINESE else "Approved line."
        write_text(editor, json.dumps(lines or [{"id": "D001", "speaker": "人物名", "text": example}],
                                      ensure_ascii=False, indent=2))

        def load_file():
            chosen = filedialog.askopenfilename(parent=panel, filetypes=(("JSON 对白", "*.json"),))
            if chosen:
                write_text(editor, Path(chosen).read_text(encoding="utf-8-sig"))

        def add():
            self.project.import_dialogue(source, editor.get("1.0", "end"), replace_source_lines=True)
            self.status.set(f"本组已导入 {len(self.project.lines)} 条批准对白")
            panel.destroy()

        bar = ttk.Frame(panel, padding=10)
        bar.pack(fill="x")
        self.buttons(bar, ("打开 JSON", load_file), ("导入批准对白", add))
        self.wait(panel)

    def wait(self, dialog):
        if dialog == self.overlay:
            return
        dialog.grab_set()
        self.window.wait_window(dialog)
        if not self.embedded:
            self.window.grab_set()

    def subpanel(self, title, geometry="", *, form=False, header=True, help_topic=None):
        if not self.embedded:
            panel = tk.Toplevel(self.window)
            panel.title(title)
            if geometry:
                panel.geometry(geometry)
            panel.transient(self.window)
            return panel

        panel = ttk.Frame(self.frame, name="production_subpanel")
        if header:
            bar = ttk.Frame(panel, padding=(10, 8))
            bar.pack(fill="x")
            ttk.Label(bar, text=title).pack(side="left", padx=(0, 8))
            caption(ttk.Button(bar, command=panel.destroy), "返回").pack(side="right")
            if help_topic is not None:
                help_button = guide_button(bar, help_topic)
                if help_button is not None:
                    help_button.pack(side="right", padx=(0, 6))
        self.overlay = panel
        self.overlay_has_form = form
        self.body.pack_forget()
        panel.pack(fill="both", expand=True)

        def restore(event):
            if event.widget == panel:
                self.overlay = None
                self.overlay_has_form = False
                if self.body.winfo_exists():
                    self.body.pack(fill="both", expand=True)

        panel.bind("<Destroy>", restore, add="+")
        return panel

    def open_drafting(self, *, task=None):
        from .drafting_dialog import DraftingDialog

        if self.on_stage:
            return self.open_stage("drafts", start_task=task, source_id=self.selected_source_id())
        self.save()
        self.wait(DraftingDialog(self, self.text_session, start_task=task).window)

    def camera_notes(self):
        self.update_group()
        return camera_findings_text(project_camera_cuts(self.project),
                                    english=getattr(self.window._root(), "ui_language", "zh") == "en")

    def show_camera_review(self):
        title = translate(self.window, "景别与角度预检")
        result = self.camera_notes() or translate(self.window, "已填的景别和角度没有匹配到重复项。")
        footer = translate(self.window, "此检查依据镜头文字。请对照实际板格、机位、轴线和动作承接。")
        self.show_text(title, result + "\n\n" + footer)

    def open_assets_for_shots(self, *, owner=None, preferred_source=""):
        from .storyboard_planning_dialog import open_storyboard_planning

        if not self.project.shots:
            raise ValueError("请先插入或采纳分镜，再分析本组资产。")
        if owner is None:
            owner = self.window
            if self.shots.selection():
                preferred_source = self.project.shots[self.shots.index(self.shots.selection()[0])].source
            elif self.embedded:
                preferred_source = self.selected_source_id()
        sources = shot_sources(self.project)
        if self.on_stage:
            identities = {source.id for source in sources}
            chosen = preferred_source if preferred_source in identities else (sources[0].id if len(sources) == 1 else "")
            return self.open_stage("inventory", source_id=chosen)
        if len(sources) == 1:
            source = sources[0]
        else:
            source = self.select_asset_source(owner, sources, preferred_source)
            if source is None:
                return
        self.save()
        planner = open_storyboard_planning(owner, self.text_session, task="assets", approved_script=source.text,
                                           approved_title=f"{source.name} · {source.version}", rules=self.rules,
                                           shot_context=asset_shot_context(self.project, source))
        owner.wait_window(planner.window)
        owner.grab_set()

    def select_asset_source(self, owner, sources, preferred):
        panel = tk.Toplevel(owner)
        title = translate(panel, "选择资产分析使用的剧本版本")
        panel.title(title)
        panel.transient(owner)
        form = ttk.Frame(panel, padding=12)
        form.pack(fill="both", expand=True)
        ttk.Label(form, text=translate(panel, "本组镜头引用多个剧本版本。每次仅分析同一版本及其镜头。"),
                  wraplength=450).pack(anchor="w", pady=(0, 7))
        count_label = translate(panel, "{count} 镜")
        choices = tuple(f"{source.name} · {source.version} · " + count_label.format(
            count=sum(shot.source == source.id for shot in self.project.shots),
        ) for source in sources)
        chooser = ttk.Combobox(form, values=choices, state="readonly", width=50)
        chooser.current(next((index for index, source in enumerate(sources) if source.id == preferred), 0))
        chooser.pack(fill="x", pady=(0, 7))
        selection = []

        def accept():
            selection.append(sources[chooser.current()])
            panel.destroy()

        bar = ttk.Frame(form)
        bar.pack(fill="x")
        self.buttons(bar, ("分析所选版本", accept), ("取消", panel.destroy))
        panel.grab_set()
        owner.wait_window(panel)
        owner.grab_set()
        return selection[0] if selection else None

    def open_image_production(self, *, kind="角色", reference_id="", reference_kind="", save_project=True):
        from .image_production_dialog import ImageProductionDialog

        if self.on_stage:
            destination = "generate_board" if kind == "故事板" else "generate_assets"
            return self.open_stage(destination, reference_id=reference_id, reference_kind=reference_kind)
        if save_project:
            self.save()
        panel = ImageProductionDialog(self, self.image_session, kind=kind, reference_id=reference_id,
                                      reference_kind=reference_kind).window
        panel.lift()
        if not panel.winfo_viewable():
            panel.wait_visibility()
        panel.focus_set()
        self.wait(panel)

    def open_reference_design(self, kind):
        from .reference_tools_dialog import open_reference_tools

        if self.on_stage:
            return self.open_stage(kind)
        def use_reference(reference_id):
            self.refresh()
            self.guarded(lambda: self.open_image_production(reference_id=reference_id, reference_kind=kind))

        self.save()
        open_reference_tools(self.window, self.project, self.path, kind, use_reference)

    def open_action_sequence(self):
        from .action_sequence_dialog import ActionSequenceDialog

        if self.project is None:
            raise ValueError("请先新建或打开项目。")
        if self.on_stage:
            return self.open_stage("action_sequence")
        if self.action_workspace is not None:
            self.action_workspace()
            return
        self.wait(ActionSequenceDialog(self).window)

    def open_layout(self, *, adjacent_path=None):
        from .layout_dialog import LayoutDialog

        if self.on_stage:
            return self.open_stage("layout", adjacent_path=adjacent_path)
        self.save()
        self.wait(LayoutDialog(self, adjacent_path=adjacent_path).window)

    def refresh(self):
        selection = (self.shots.selection(), self.images.selection())
        scroll = (self.shots.yview(), self.images.yview())
        self.shots.delete(*self.shots.get_children())
        self.images.delete(*self.images.get_children())
        image_names = {image.id: image.filename for image in self.project.images}
        for number, shot in enumerate(self.project.shots, 1):
            self.shots.insert("", "end", iid=shot.id, values=(
                f"{self.project.group}-{number:02d}", shot.anchor, image_names.get(shot.plate, ""),
                "、".join(identity for identity, _, _ in shot.dialogue)))
        for image in self.project.images:
            self.images.insert("", "end", iid=image.id, values=(
                image.filename, "参考原图" if image.reference_only else "正式交付", image.version,
                image.action, f"{image.width}×{image.height}"))
        for table, items, view in zip((self.shots, self.images), selection, scroll):
            if items and table.exists(items[0]):
                table.selection_set(items[0])
            if view:
                table.yview_moveto(view[0])
        self.show_impacts()

    def index(self, table, label):
        selected = table.selection()
        if not selected:
            raise ValueError(f"请先选择{label}。")
        return table.index(selected[0])

    def select_shot(self, index):
        identity = self.project.shots[index].id
        self.shots.selection_set(identity)
        self.shots.see(identity)

    def edit_shot(self, insert=False):
        if not self.project.sources:
            raise ValueError("请先在「项目与组」导入批准剧本。")
        if insert:
            index = self.shots.index(self.shots.selection()[0]) + 1 if self.shots.selection() else len(self.project.shots)
            shot = Shot(source=self.current_source().id)
        else:
            index = self.index(self.shots, "镜头")
            shot = self.project.shots[index]
        panel = self.subpanel(f"{'插入' if insert else '编辑'}镜头 · {shot.id}", "850x690", form=True)
        form = ttk.Frame(panel, padding=10)
        form.pack(fill="x")
        variables = [tk.StringVar(panel, value) for value in ("", shot.anchor, "", shot.scene, shot.plate_note)]
        sources = self.project.sources
        plates = [image for image in self.project.images if not image.reference_only
                  and ("_details" in image.filename.lower() or "场景合辑" in image.filename
                       or "scene_九图合并_" in image.filename)]
        source = field(form, 0, "批准剧本", variables[0], [f"{s.name} · {s.version}" for s in sources])
        if any(item.id == shot.source for item in sources):
            source.current(next(i for i, item in enumerate(sources) if item.id == shot.source))
        field(form, 1, "源段位置", variables[1])
        plate = field(form, 2, "净板 PNG", variables[2], [image.filename for image in plates])
        if any(image.id == shot.plate for image in plates):
            plate.current(next(i for i, image in enumerate(plates) if image.id == shot.plate))
        field(form, 3, "地点", variables[3])
        field(form, 4, "净板机位说明", variables[4])
        parent_shot = tk.StringVar(panel, shot.fields.get(PARENT_SHOT_FIELD, ""))
        field(form, 5, "批准父镜 ID（细拆时填写）", parent_shot)
        ttk.Label(panel, text=translate(panel, "对白 · 单填 ID 使用本组已选范围。跨镜续说填写「D001 起始字符位 结束字符位」。")).pack(anchor="w", padx=10)
        dialogue = self.editor(panel, 3, name="production_shot_dialogue")
        dialogue.pack(fill="x", padx=10)
        write_text(dialogue, "\n".join(f"{identity} {start} {end}" for identity, start, end in shot.dialogue))
        ttk.Label(panel, text=translate(panel, "镜头内容 · 成片动作留空时沿用动作起止。")).pack(anchor="w", padx=10, pady=(7, 0))
        editor = self.editor(panel, 15, name="production_shot_fields")
        editor.pack(fill="both", expand=True, padx=10)
        write_text(editor, fields_text(SHOT_FIELDS, shot.fields))

        def accept():
            by_id = {line.id: line for line in self.project.lines}
            utterances = []
            for row in dialogue.get("1.0", "end").splitlines():
                parts = row.split()
                if not parts:
                    continue
                identity = parts[0]
                if identity not in by_id or len(parts) not in (1, 3):
                    raise ValueError(f"对白 ID 或区间不可用：{row}")
                span = (0, len(by_id[identity].text)) if self.project.dialogue_scope is None else self.project.dialogue_scope.get(identity)
                if span is None:
                    raise ValueError(f"{identity} 不在本组的批准对白范围内。")
                start, end = span if len(parts) == 1 else map(int, parts[1:])
                if not span[0] <= start < end <= span[1]:
                    raise ValueError(f"{identity} 的字符区间超出本组批准范围。")
                utterances.append((identity, start, end))
            edited_fields = read_fields(editor, SHOT_FIELDS)
            parent_id = parent_shot.get().strip()
            if parent_id:
                if any(char in parent_id for char in "|\r\n"):
                    raise ValueError("批准父镜 ID 请使用单行标识，不含竖线。")
                edited_fields[PARENT_SHOT_FIELD] = parent_id
            updated = replace(shot, source=sources[source.current()].id if source.current() >= 0 else "",
                              anchor=variables[1].get().strip(), plate=plates[plate.current()].id if plate.current() >= 0 else "",
                              scene=variables[3].get().strip(), plate_note=variables[4].get().strip(),
                              dialogue=utterances, fields=edited_fields)
            if insert:
                self.project.shots.insert(index, updated)
            else:
                self.project.shots[index] = updated
            self.refresh()
            self.select_shot(index)
            panel.destroy()

        bar = ttk.Frame(panel, padding=10)
        bar.pack(fill="x")
        self.buttons(bar, ("应用镜头更改", accept), ("取消", panel.destroy))
        self.wait(panel)

    def move(self, offset):
        index = self.project.move_shot(self.index(self.shots, "镜头"), offset)
        self.refresh()
        self.select_shot(index)

    def remove_shot(self):
        index = self.index(self.shots, "镜头")
        if messagebox.askyesno(translate(self.window, "删除镜头"), translate(self.window, "从当前组的镜头清单删除此镜？"), parent=self.window):
            self.project.shots.pop(index)
            self.refresh()

    def pick_registered(self):
        value = self.registry.get()
        if not value or not Path(value).is_file():
            value = filedialog.askopenfilename(parent=self.window, filetypes=(("资产登记库", "*.sqlite3 *.db"),))
        if not value:
            return
        entries = AssetRegistry(Path(value)).records()
        if not entries:
            raise ValueError("这个资产登记库没有已批准记录。")
        panel = self.subpanel(translate(self.window, "选择登记的原图"))
        form = ttk.Frame(panel, padding=10)
        form.pack(fill="x")
        selection = field(form, 0, "批准版本", tk.StringVar(panel), [
            f"{entry.identifier} · {entry.version} · {Path(entry.location).name}" for entry in entries])
        selection.current(0)
        approved = []

        def accept():
            chosen = entries[selection.current()]
            panel.destroy()
            if self.embedded:
                self.import_image(chosen)
            else:
                approved.append(chosen)

        form_footer = ttk.Frame(panel, padding=10)
        self.buttons(form_footer, ("选定原图", accept))
        form_footer.pack(fill="x")
        self.wait(panel)
        if approved:
            self.import_image(approved[0])

    def import_image(self, approved=None):
        value = approved.location if approved else filedialog.askopenfilename(
            parent=self.window, filetypes=(("PNG 图像", "*.png"),))
        if not value:
            return
        path = Path(value)
        if not path.is_file() and approved:
            value = filedialog.askopenfilename(parent=self.window, filetypes=(("定位登记的原图", "*.png"),))
            if not value:
                return
            path = Path(value)
        panel = self.subpanel(translate(self.window, "绑定批准图像"), form=True)
        form = ttk.Frame(panel, padding=10)
        form.pack(fill="x", expand=True)
        name, version, action, reason, inspection, originals = (
            tk.StringVar(panel, initial) for initial in (
                path.name, approved.version if approved else "1", ACTIONS[0], "", "", ""))
        for row, (label, variable) in enumerate((("交付文件名", name), ("批准版本", version), ("实际处理方式", action),
                                                ("处理理由", reason), ("实际核图记录", inspection), ("批准原图文件名（用 | 隔开）", originals))):
            field(form, row, label, variable, ACTIONS if variable is action else None)
        reference = tk.BooleanVar(panel, False)
        ttk.Checkbutton(form, text=translate(form, "仅用于来源比对"), variable=reference).grid(row=6, column=0, columnspan=2, sticky="w")
        self.show_thumbnail(panel, path)

        def accept():
            names = {image.filename: image.id for image in self.project.images}
            requested = [name.strip() for name in originals.get().split("|") if name.strip()]
            if any(name not in names for name in requested):
                raise ValueError("批准原图文件名有误，请使用已导入图片的文件名。")
            item = self.project.import_image(
                self.path, path, name.get(), action=action.get(), version=version.get(),
                reason=reason.get(), inspection=inspection.get(), approved=approved,
                originals=tuple(names[name] for name in requested), reference_only=reference.get(),
            )
            self.refresh()
            self.images.selection_set(item.id)
            self.images.see(item.id)
            panel.destroy()

        bar = ttk.Frame(panel, padding=10)
        bar.pack(fill="x")
        self.buttons(bar, ("绑定批准图像", accept), ("取消", panel.destroy))
        self.wait(panel)

    def show_thumbnail(self, panel, path):
        with Image.open(path) as image:
            if image.width * image.height > 32_000_000:
                panel.destroy()
                raise ValueError("图片超过内置预览分辨率。")
            image.thumbnail((640, 350), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image, master=panel)
        label = ttk.Label(panel, image=photo)
        label.photo = photo
        label.pack(padx=10, pady=5)

    def view_image(self):
        image = self.project.images[self.index(self.images, "图像")]
        if self.embedded:
            return self.open_media_library(selected=(image.id,), direct=True)
        path = self.project.checked_image(self.path, image)
        panel = self.subpanel(image.filename)
        self.show_thumbnail(panel, path)
        ttk.Label(panel, text=f"{image.width}×{image.height} · {image.inspection}").pack(padx=10, pady=5)
        self.wait(panel)

    def remove_image(self):
        image = self.project.images[self.index(self.images, "图像")]
        if any(image.id in item.originals for item in self.project.images):
            raise ValueError("其他图像正引用该批准原图。")
        self.project.images.remove(image)
        self.refresh()

    def show_impacts(self):
        impacts = self.project.impacts()
        write_text(self.report, "当前版本需复核\n" + "\n".join(impacts) if impacts else "已确认本版画面，可发起严格验收。")

    def validator_path(self):
        chosen = self.validators.get(self.rules, "")
        path = Path(chosen).expanduser() if chosen else bundled_validator(self.rules)
        if path is None or not path.is_file():
            raise ValueError(f"请在主窗口为{RULE_LABELS[self.rules]}选择对应的故事板校验脚本。")
        return path

    def preview_chinese_text(self):
        self.save()
        records = chinese_text_records(self.project)
        write_text(self.report, "\n\n".join(f"── {name} ──\n\n{text}" for name, text in records.items()))

    def export_chinese_text(self):
        self.save()
        destination = filedialog.askdirectory(parent=self.window, title="选择文字稿保存目录", initialdir=self.path.parent)
        if destination:
            path = write_chinese_texts(self.project, Path(destination))
            write_text(self.report, f"已导出文字稿\n{path}\n\n" + "\n".join(sorted(item.name for item in path.iterdir())))

    def review_chinese_layout(self):
        self.save()
        if self.embedded:
            return self.open_pack_review(preview_chinese_layout)
        with TemporaryDirectory(prefix="comicflow-cn-layout-") as directory:
            archive = preview_chinese_layout(self.project, self.path, Path(directory))
            with ZipFile(archive) as stream:
                members = index_members(stream)
            open_shot_review(self.window, ReviewResult(0, "", archive, members, []), group=self.project.group)
            self.window.grab_set()

    def export_chinese_layout(self):
        self.save()
        destination = filedialog.askdirectory(parent=self.window, title="选择排版图文保存目录", initialdir=self.path.parent)
        if destination:
            folder = Path(destination) / f"{self.project.group}_排版复核"
            write_chinese_layout(self.project, self.path, folder)
            write_text(self.report, f"已保存排版复核图文\n{folder}")

    def preview(self):
        self.save()
        if self.embedded:
            return self.open_pack_review(lambda project, path, directory: preview_project(
                project, path, self.validator_path(), directory,
            ), confirmable=True)
        with TemporaryDirectory(prefix="comicflow-review-") as temporary:
            archive = preview_project(self.project, self.path, self.validator_path(), Path(temporary))
            with ZipFile(archive) as stream:
                members = index_members(stream)
            open_shot_review(self.window, ReviewResult(0, "", archive, members, []), group=self.project.group)
            self.window.grab_set()
            self.previewed = self.project.fingerprint()
            write_text(self.report, "复核预览 ZIP 的 SHA-256\n" + sha256_file(archive) + "\n\n请确认本版画面。")
        self.registry.set(str(project_registry(self.path)))

    def open_pack_review(self, make_preview, *, confirmable=False):
        temporary = TemporaryDirectory(prefix="comicflow-review-")
        panel = None
        try:
            archive = make_preview(self.project, self.path, Path(temporary.name))
            with ZipFile(archive) as stream:
                members = index_members(stream)
            panel = self.subpanel(translate(self.window, "逐格复核"), help_topic="deliver")
            opened = open_shot_review(
                self.window, ReviewResult(0, "", archive, members, []), group=self.project.group, mount=panel,
            )
            if opened is None:
                panel.destroy()
                temporary.cleanup()
                return
            if confirmable:
                previewed = self.project.fingerprint()
                digest = sha256_file(archive)

            def close_preview(event):
                if event.widget != panel:
                    return
                temporary.cleanup()
                if confirmable and self.report.winfo_exists():
                    self.previewed = previewed
                    write_text(self.report, "复核预览 ZIP 的 SHA-256\n" + digest + "\n\n请确认本版画面。")
                    self.registry.set(str(project_registry(self.path)))

            panel.bind("<Destroy>", close_preview, add="+")
        except Exception:
            if panel is not None and panel.winfo_exists():
                panel.destroy()
            temporary.cleanup()
            raise

    def preflight(self):
        self.update_group()
        count = sum(not image.reference_only for image in self.project.images)
        if count > IMAGE_LIMIT:
            raise ValueError(f"本组正式图片 {count} 张，超过 {IMAGE_LIMIT} 张上限。")
        validator = self.validator_path()
        _, _, words = render_dialogue(self.project, validator.with_name("plan_english_dialogue.py"))
        write_text(self.report, f"本组 {len(self.project.shots)} 镜，批准对白实际发声 {words} 个英文词。\n"
                   f"正式图像 {count} / {IMAGE_LIMIT} 张。\n请继续生成逐格复核预览。")

    def confirm(self):
        self.update_group()
        if self.previewed != self.project.fingerprint():
            raise ValueError("请先打开当前版本的逐格复核预览。")
        details = translate(self.window, "是否已核对故事板格序、净板局部和镜头文字？")
        if self.rules == ENGLISH:
            details += "\n\n" + translate(
                self.window, "逐格确认实际景别与机位、角色身份和数量、动作承接、线稿可读性及实际画幅。",
            )
        if findings := self.camera_notes():
            details += "\n\n" + findings + "\n\n" + translate(
                self.window, "请核对实际画面。只有规则允许且已确认的衔接才能保留。",
            )
        if messagebox.askyesno(translate(self.window, "确认本版画面"), details, parent=self.window):
            self.project.structure_review = self.previewed
            self.save()

    def publish(self):
        self.save()
        validator = self.validator_path()
        if self.project.impacts():
            raise ValueError("请先完成逐格复核并确认本版画面。")
        value = filedialog.asksaveasfilename(parent=self.window, filetypes=(("交付 ZIP", "*.zip"),),
                                             defaultextension=".zip", initialfile=f"{self.project.group}.zip")
        if not value:
            return
        baseline = self.baseline.get().strip()
        exception = self.exception.get().strip() if self.rules == ENGLISH else ""
        self.window.configure(cursor="watch")
        self.status.set(translate(self.window, "正在严格验收交付包…"))
        self.window.update_idletasks()
        try:
            result = publish_project(self.project, self.path, validator, Path(value),
                                     Path(baseline) if baseline else None, Path(exception) if exception else None)
        except Exception:
            self.status.set("交付未导出")
            raise
        finally:
            self.window.configure(cursor="")
        self.registry.set(str(project_registry(self.path)))
        details = [result.report]
        if result.output:
            details.extend((f"已导出 {result.output}", f"ZIP SHA-256 {result.sha256}"))
            if baseline:
                for label, files in (("修改", result.changed), ("新增", result.added), ("移除", result.removed)):
                    details.append(f"{label}\n" + ("\n".join(files) or "无"))
        write_text(self.report, "\n\n".join(details))
        self.status.set(translate(self.window, "已导出并重新核验 ZIP" if result.output else "校验未通过，请查看报告"))


def open_production_dialog(parent, validators, registry, text_session, image_session, rules, on_rules_changed,
                           initial_project=None, *, initial_action=None, destination="group",
                           loaded_project=None, source_id="", adjacent_path=None):
    if initial_action == "open" and destination in {"generate_assets", "generate_board", "action_sequence"} and initial_project is None:
        try:
            selected = choose_project_file(parent)
        except tk.TclError as exc:
            messagebox.showerror(translate(parent, "单组制片"), str(exc), parent=parent)
            return None
        if not selected:
            return None
        dialog = ProductionDialog(parent, validators, registry, text_session, image_session, rules, on_rules_changed)
        dialog.open_tool_project(Path(selected), destination)
        return dialog

    dialog = ProductionDialog(parent, validators, registry, text_session, image_session, rules, on_rules_changed)

    def open_at_destination():
        if initial_project is not None:
            dialog.load(loaded_project or ProductionProject.open(initial_project), initial_project, source_id=source_id)
        elif initial_action == "new":
            dialog.create()
        elif initial_action == "open":
            dialog.open()
        if dialog.project is not None:
            if adjacent_path is None:
                dialog.go_to(destination)
            else:
                dialog.go_to(destination, adjacent_path=adjacent_path)
        elif initial_action:
            dialog.window.destroy()

    if initial_project is not None or initial_action:
        dialog.window.after_idle(lambda: dialog.guarded(open_at_destination))
    return dialog
