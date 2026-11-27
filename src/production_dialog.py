"""Local authoring and delivery window for an SD2 storyboard group."""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from zipfile import ZipFile

from PIL import Image, ImageTk

from .asset_registry import AssetRegistry, sha256_file
from .production_export import preview_project, project_registry, publish_project, render_dialogue
from .production_project import ACTIONS, GROUP_FIELDS, PROMPT_FIELDS, SHOT_FIELDS, ProductionProject, Shot
from .shot_review_dialog import open_shot_review
from .storyboard_review import ReviewResult, index_members
from .storyboard_preflight import IMAGE_LIMIT


PROJECT_FILES = (("ComicFlow 单组项目", "*.cfproject"),)


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


def field(parent, row, label, value, choices=None):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
    if choices is None:
        widget = ttk.Entry(parent, textvariable=value)
    else:
        widget = ttk.Combobox(parent, textvariable=value, values=choices, state="readonly")
    widget.grid(row=row, column=1, sticky="ew", pady=3)
    parent.columnconfigure(1, weight=1)
    return widget


class ProductionDialog:
    def __init__(self, parent, validator, registry, text_session, image_session):
        self.validator = validator
        self.registry = registry
        self.text_session = text_session
        self.image_session = image_session
        self.project = None
        self.path = None
        self.previewed = None
        self.window = tk.Toplevel(parent)
        self.window.title("ComicFlow 单组制片")
        self.window.geometry("1050x745")
        self.window.minsize(820, 610)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        top = ttk.Frame(self.window, padding=10)
        top.pack(fill="x")
        self.buttons(top, ("新建单组项目", self.create), ("打开单组项目", self.open), ("保存项目", self.save))
        self.buttons(top, ("文本制片", self.open_drafting))
        self.buttons(top, ("图像制片", self.open_image_production))
        self.status = tk.StringVar(self.window, "新建或打开项目后开始。")
        ttk.Label(top, textvariable=self.status).pack(side="left", padx=8)
        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.setup_group(self.tab("项目与组"))
        self.setup_shots(self.tab("镜头清单"))
        self.setup_images(self.tab("批准图像"))
        self.setup_delivery(self.tab("复核与交付"))
        for index in range(4):
            self.tabs.tab(index, state="disabled")

    def guarded(self, task):
        try:
            task()
        except Exception as exc:
            messagebox.showerror("单组制片", str(exc), parent=self.window)

    def buttons(self, bar, *buttons):
        for title, command in buttons:
            ttk.Button(bar, text=title, command=lambda task=command: self.guarded(task)).pack(side="left", padx=(0, 6))

    def tab(self, name):
        page = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(page, text=name)
        return page

    def editor(self, parent, height=8):
        return scrolledtext.ScrolledText(parent, height=height, width=55, wrap="word", undo=True)

    def setup_group(self, page):
        top = ttk.Frame(page)
        top.pack(fill="x")
        self.name, self.episode, self.group = (tk.StringVar(self.window) for _ in range(3))
        for row, (caption, value) in enumerate((("项目名", self.name), ("集次", self.episode), ("组号", self.group))):
            field(top, row, caption, value)
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=8)
        self.buttons(bar, ("导入批准剧本", self.import_source), ("查看原文和对白 ID", self.view_source),
                     ("编辑本组批准对白 JSON", self.import_dialogue))
        self.source = ttk.Combobox(bar, state="readonly", width=30)
        self.source.pack(side="left", expand=True, fill="x")
        ttk.Label(page, text="制片记录 · 必填项按交付规则填写，可用「- 」追加行").pack(anchor="w")
        self.notes = self.editor(page, 18)
        self.notes.pack(fill="both", expand=True)
        ttk.Label(page, text="SD2 公共说明 · 填写成片环境与约束").pack(anchor="w", pady=(8, 0))
        self.prompt = self.editor(page, 5)
        self.prompt.pack(fill="both")

    def setup_shots(self, page):
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 8))
        self.buttons(bar, ("插入镜头", lambda: self.edit_shot(insert=True)), ("编辑镜头", self.edit_shot),
                     ("上移", lambda: self.move(-1)), ("下移", lambda: self.move(1)), ("删除镜头", self.remove_shot))
        self.shots = self.table(page, ("镜号", "源段", "净板文件", "对白 ID"), (85, 265, 240, 140))
        self.shots.bind("<Double-1>", lambda _event: self.guarded(self.edit_shot))
        ttk.Label(page, text="镜号和净板局部号按播放顺序生成。移动或插入后，在复核窗口重新核对故事板格与场景图的局部标签。").pack(anchor="w", pady=(8, 0))

    def setup_images(self, page):
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(0, 8))
        self.buttons(bar, ("导入批准 PNG", self.import_image), ("从资产登记库导入", self.pick_registered),
                     ("打开图片", self.view_image), ("移除图片绑定", self.remove_image))
        self.images = self.table(page, ("文件名", "范围", "版本", "处理方式", "尺寸"), (335, 100, 65, 135, 100))
        self.images.bind("<Double-1>", lambda _event: self.guarded(self.view_image))

    def setup_delivery(self, page):
        form = ttk.Frame(page)
        form.pack(fill="x")
        self.baseline, self.exception = (tk.StringVar(self.window) for _ in range(2))
        for row, (caption, value, pattern) in enumerate((("原包比对（可选）", self.baseline, "*.zip"),
                                                         ("批准格数例外（可选）", self.exception, "*.json"))):
            field(form, row, caption, value)
            ttk.Button(form, text="浏览", command=lambda v=value, p=pattern: self.choose(v, p)).grid(row=row, column=2, padx=5)
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=8)
        self.buttons(bar, ("对白与图数预检", self.preflight), ("生成逐格复核预览", self.preview),
                     ("确认本版画面", self.confirm), ("验收并导出 ZIP", self.publish))
        ttk.Label(page, text="核对故事板格号、净板局部、对白与画面后再确认。报告显示交付包校验结果。").pack(anchor="w")
        self.report = self.editor(page, 18)
        self.report.pack(fill="both", expand=True, pady=(5, 0))

    def table(self, parent, columns, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        table = ttk.Treeview(frame, show="headings", columns=columns, selectmode="browse")
        scroll = ttk.Scrollbar(frame, command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        for title, width in zip(columns, widths):
            table.heading(title, text=title)
            table.column(title, width=width)
        scroll.pack(side="right", fill="y")
        table.pack(fill="both", expand=True)
        return table

    def choose(self, variable, pattern):
        selected = filedialog.askopenfilename(parent=self.window, filetypes=((pattern, pattern),))
        if selected:
            variable.set(selected)

    def update_group(self):
        if self.project:
            self.project.notes = read_fields(self.notes, GROUP_FIELDS)
            self.project.prompt = read_fields(self.prompt, PROMPT_FIELDS)
            self.project.name, self.project.episode, self.project.group = (
                item.get().strip() for item in (self.name, self.episode, self.group)
            )
            self.project.group = self.project.group.upper()

    def save(self):
        if not self.project:
            raise ValueError("请先新建或打开项目。")
        self.update_group()
        self.project.save(self.path)
        self.status.set(f"已保存 {self.path.name}")
        self.show_impacts()

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
        result = messagebox.askyesnocancel("尚有项目更改", "离开前保存项目？", parent=self.window)
        if result:
            self.save()
        return result is not None

    def close(self):
        self.guarded(lambda: self.window.destroy() if self.allow_leave() else None)

    def create(self):
        if not self.allow_leave():
            return
        value = filedialog.asksaveasfilename(parent=self.window, filetypes=PROJECT_FILES, defaultextension=".cfproject")
        if value:
            path = Path(value)
            if path.exists():
                raise ValueError("这个项目文件已存在，请选择新文件名。")
            project = ProductionProject(path.stem, "EP01", "SB01")
            project.save(path)
            self.load(project, path)

    def open(self):
        if not self.allow_leave():
            return
        value = filedialog.askopenfilename(parent=self.window, filetypes=PROJECT_FILES)
        if value:
            path = Path(value)
            self.load(ProductionProject.open(path), path)

    def load(self, project, path):
        self.project, self.path, self.previewed = project, path, None
        for variable, value in zip((self.name, self.episode, self.group), (project.name, project.episode, project.group)):
            variable.set(value)
        write_text(self.notes, fields_text(GROUP_FIELDS, project.notes))
        write_text(self.prompt, fields_text(PROMPT_FIELDS, project.prompt))
        self.baseline.set("")
        self.exception.set("")
        for index in range(4):
            self.tabs.tab(index, state="normal")
        self.tabs.select(0)
        self.refresh_sources()
        self.refresh()
        if project_registry(path).is_file():
            self.registry.set(str(project_registry(path)))
        self.status.set(path.name)

    def refresh_sources(self):
        self.source["values"] = tuple(f"{source.name} · {source.version}" for source in self.project.sources)
        if self.project.sources:
            self.source.current(len(self.project.sources) - 1)
        else:
            self.source.set("")

    def current_source(self):
        index = self.source.current()
        if index < 0:
            raise ValueError("请先导入并选择批准剧本。")
        return self.project.sources[index]

    def import_source(self):
        value = filedialog.askopenfilename(parent=self.window, filetypes=(("UTF-8 剧本", "*.txt *.md"),))
        if value:
            version = simpledialog.askstring("批准剧本版本", "输入版本号，例如 R5", parent=self.window)
            if version is not None:
                path = Path(value)
                source = self.project.import_source(path.name, version, path.read_text(encoding="utf-8-sig"))
                self.refresh_sources()
                self.source.current(self.project.sources.index(source))

    def show_text(self, title, content):
        dialog = tk.Toplevel(self.window)
        dialog.title(title)
        dialog.geometry("760x550")
        dialog.transient(self.window)
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
        panel = tk.Toplevel(self.window)
        panel.title("导入本组批准对白")
        panel.transient(self.window)
        ttk.Label(panel, text="粘贴或打开批准对白 JSON。可用 sentence_ends 标同一 ID 的整句分界。").pack(padx=10, pady=6)
        editor = self.editor(panel, 12)
        editor.pack(fill="both", expand=True, padx=10)
        lines = [{"id": line.id, "speaker": line.speaker, "text": line.text}
                 for line in self.project.lines if line.source == source.id]
        by_id = {line.id: line for line in self.project.lines}
        for row in lines:
            ends = by_id[row["id"]].sentence_ends
            if ends:
                row["sentence_ends"] = list(ends)
        write_text(editor, json.dumps(lines or [{"id": "D001", "speaker": "人物名", "text": "Approved line."}],
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
        dialog.grab_set()
        self.window.wait_window(dialog)
        self.window.grab_set()

    def open_drafting(self):
        from .drafting_dialog import DraftingDialog

        self.save()
        self.wait(DraftingDialog(self, self.text_session).window)

    def open_image_production(self):
        from .image_production_dialog import ImageProductionDialog

        self.save()
        self.wait(ImageProductionDialog(self, self.image_session).window)

    def refresh(self):
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
        panel = tk.Toplevel(self.window)
        panel.title(f"{'插入' if insert else '编辑'}镜头 · {shot.id}")
        panel.geometry("850x690")
        panel.transient(self.window)
        form = ttk.Frame(panel, padding=10)
        form.pack(fill="x")
        variables = [tk.StringVar(panel, value) for value in ("", shot.anchor, "", shot.scene, shot.plate_note)]
        sources = self.project.sources
        plates = [image for image in self.project.images if not image.reference_only
                  and ("_details" in image.filename.lower() or "场景合辑" in image.filename)]
        source = field(form, 0, "批准剧本", variables[0], [f"{s.name} · {s.version}" for s in sources])
        if any(item.id == shot.source for item in sources):
            source.current(next(i for i, item in enumerate(sources) if item.id == shot.source))
        field(form, 1, "源段位置", variables[1])
        plate = field(form, 2, "净板 PNG", variables[2], [image.filename for image in plates])
        if any(image.id == shot.plate for image in plates):
            plate.current(next(i for i, image in enumerate(plates) if image.id == shot.plate))
        field(form, 3, "地点", variables[3])
        field(form, 4, "净板机位说明", variables[4])
        ttk.Label(panel, text="对白 · 单填 ID 使用本组已选范围。跨镜续说填写「D001 起始字符位 结束字符位」。").pack(anchor="w", padx=10)
        dialogue = self.editor(panel, 3)
        dialogue.pack(fill="x", padx=10)
        write_text(dialogue, "\n".join(f"{identity} {start} {end}" for identity, start, end in shot.dialogue))
        ttk.Label(panel, text="镜头内容 · 成片动作留空时沿用动作起止。").pack(anchor="w", padx=10, pady=(7, 0))
        editor = self.editor(panel, 15)
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
            updated = replace(shot, source=sources[source.current()].id if source.current() >= 0 else "",
                              anchor=variables[1].get().strip(), plate=plates[plate.current()].id if plate.current() >= 0 else "",
                              scene=variables[3].get().strip(), plate_note=variables[4].get().strip(),
                              dialogue=utterances, fields=read_fields(editor, SHOT_FIELDS))
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
        if messagebox.askyesno("删除镜头", "从当前组的镜头清单删除此镜？", parent=self.window):
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
        panel = tk.Toplevel(self.window)
        panel.title("选择登记的原图")
        panel.transient(self.window)
        form = ttk.Frame(panel, padding=10)
        form.pack(fill="x")
        selection = field(form, 0, "批准版本", tk.StringVar(panel), [
            f"{entry.identifier} · {entry.version} · {Path(entry.location).name}" for entry in entries])
        selection.current(0)
        approved = []

        def accept():
            approved.append(entries[selection.current()])
            panel.destroy()

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
        panel = tk.Toplevel(self.window)
        panel.title("绑定批准图像")
        panel.transient(self.window)
        form = ttk.Frame(panel, padding=10)
        form.pack(fill="x", expand=True)
        name, version, action, reason, inspection, originals = (
            tk.StringVar(panel, initial) for initial in (
                path.name, approved.version if approved else "1", ACTIONS[0], "", "", ""))
        for row, (label, variable) in enumerate((("交付文件名", name), ("批准版本", version), ("实际处理方式", action),
                                                ("处理理由", reason), ("实际核图记录", inspection), ("批准原图文件名（用 | 隔开）", originals))):
            field(form, row, label, variable, ACTIONS if variable is action else None)
        reference = tk.BooleanVar(panel, False)
        ttk.Checkbutton(form, text="仅用于来源比对", variable=reference).grid(row=6, column=0, columnspan=2, sticky="w")
        self.show_thumbnail(panel, path)

        def accept():
            names = {image.filename: image.id for image in self.project.images}
            requested = [name.strip() for name in originals.get().split("|") if name.strip()]
            if any(name not in names for name in requested):
                raise ValueError("批准原图文件名有误，请使用已导入图片的文件名。")
            self.project.import_image(self.path, path, name.get(), action=action.get(), version=version.get(),
                                      reason=reason.get(), inspection=inspection.get(), approved=approved,
                                      originals=tuple(names[name] for name in requested), reference_only=reference.get())
            self.refresh()
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
        path = self.project.checked_image(self.path, image)
        panel = tk.Toplevel(self.window)
        panel.title(image.filename)
        panel.transient(self.window)
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
        path = Path(self.validator).expanduser()
        if not path.is_file():
            raise ValueError("请在主窗口选择当前故事板校验脚本。")
        return path

    def preview(self):
        self.save()
        with TemporaryDirectory(prefix="comicflow-review-") as temporary:
            archive = preview_project(self.project, self.path, self.validator_path(), Path(temporary))
            with ZipFile(archive) as stream:
                members = index_members(stream)
            open_shot_review(self.window, ReviewResult(0, "", archive, members, []), group=self.project.group)
            self.window.grab_set()
            self.previewed = self.project.fingerprint()
            write_text(self.report, "复核预览 ZIP 的 SHA-256\n" + sha256_file(archive) + "\n\n请确认本版画面。")
        self.registry.set(str(project_registry(self.path)))

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
        if messagebox.askyesno("确认本版画面", "是否已核对故事板格序、净板局部和镜头文字？", parent=self.window):
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
        exception = self.exception.get().strip()
        self.window.configure(cursor="watch")
        self.status.set("正在严格验收交付包…")
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
        self.status.set("已导出并重新核验 ZIP" if result.output else "校验未通过，请查看报告")


def open_production_dialog(parent, validator, registry, text_session, image_session):
    ProductionDialog(parent, validator, registry, text_session, image_session)
