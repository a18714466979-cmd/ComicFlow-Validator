"""Host the existing storyboard tools in project-scoped workbench tabs."""

from copy import deepcopy
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .camera_preflight import camera_findings_text, project_camera_cuts
from .production_dialog import ProductionDialog, choose_project_file, project_filetypes
from .production_drafting import SD2_TASK, SHOT_TASK
from .production_flow import asset_shot_context, shot_sources
from .production_project import ProductionProject, atomic_text
from .project_editing import merge_project_edits
from .ui_language import translate

CAPTIONS = {
    "group": "单组制片",
    "script": "剧本创作", "shots": "分镜拆分", "inventory": "资产分析", "generate_assets": "资产图生成",
    "generate_board": "故事板图生成", "prompts": "提示词生成", "deliver": "故事板组打包交付",
    "assets": "批准图像", "layout": "排版与交接", "costume": "角色服装设计", "drafts": "文本制片",
}
NEXT_STAGE = {
    "shots": "inventory", "inventory": "generate_assets", "generate_assets": "generate_board",
    "assets": "generate_board", "generate_board": "prompts", "prompts": "deliver",
}


def _asset_plan_path(path):
    return path.with_suffix(".assets") / "asset-analysis.md"


class ProductionWorkspace:
    def __init__(self, root, tasks, current_path, selected_rules, validators, registry,
                 text_session, image_session, remember_project, open_action):
        self.root = root
        self.tasks = tasks
        self.current_path = current_path
        self.selected_rules = selected_rules
        self.validators, self.registry = validators, registry
        self.text_session, self.image_session = text_session, image_session
        self.remember_project = remember_project
        self.open_action = open_action
        self.pending = None

    def tr(self, caption):
        return translate(self.root, caption)

    def mount(self, page, label_text):
        self.page = page
        self.picker = ttk.Frame(page, name="production_project_picker", padding=(16, 10))
        self.title = ttk.Label(self.picker)
        self.title.pack(anchor="w", pady=(0, 6))
        bar = ttk.Frame(self.picker)
        bar.pack(fill="x")
        self.current_button = label_text(ttk.Button(bar, name="current_project", command=self.use_current),
                                         "使用当前项目")
        self.current_button.pack(side="left", padx=(0, 6))
        self.open_button = label_text(ttk.Button(bar, name="open_project", command=self.choose),
                                      "打开单组项目")
        self.open_button.pack(side="left", padx=(0, 6))
        label_text(ttk.Button(bar, name="new_project", command=self.create), "新建单组项目").pack(
            side="left", padx=(0, 6))
        self.local_button = label_text(ttk.Button(bar, name="local_source", command=self.open_local_analysis),
                                       "从本地稿件开始")
        self.cancel_button = label_text(ttk.Button(bar, name="cancel", command=self.hide), "取消")
        self.cancel_button.pack(side="left")
        self.status = tk.StringVar(self.root)
        ttk.Label(self.picker, textvariable=self.status).pack(anchor="w")

    def refresh_language(self):
        if self.picker.winfo_manager():
            self.title.configure(text=self.tr("为「{tool}」选择单组项目").format(tool=self.tr(CAPTIONS[self.picked])))

    def ask_project(self, stage):
        self.pending = None
        self.status.set("")
        self.picked = stage
        self.tasks.select(self.page)
        self.current_button.state(["!disabled"] if self.current_path() else ["disabled"])
        self.local_button.pack_forget()
        if stage == "inventory":
            self.local_button.pack(side="left", before=self.cancel_button, padx=(0, 6))
        siblings = self.page.pack_slaves()
        if not self.picker.winfo_manager():
            self.picker.pack(fill="x", **({"before": siblings[0]} if siblings else {}))
        self.refresh_language()
        self.open_button.focus_set()

    def hide(self):
        self.pending = None
        self.picker.pack_forget()
        self.status.set("")

    def use_current(self):
        if path := self.current_path():
            self.load_async(path, self.picked)

    def choose(self):
        if path := choose_project_file(self.root):
            self.load_async(path, self.picked)

    def create(self):
        if path := filedialog.asksaveasfilename(
            parent=self.root, title=self.tr("保存新建的单组项目"), filetypes=project_filetypes(self.root),
            defaultextension=".cfproject", initialfile="SB01.cfproject",
        ):
            self.load_async(path, self.picked, create=True)

    def open_local_analysis(self):
        self.hide()
        self.open("inventory")

    def show_error(self, reason):
        messagebox.showerror(self.tr("故事板制作"), self.tr(str(reason)), parent=self.root)

    def load_async(self, path, stage, *, create=False):
        path = Path(path).expanduser()
        rules = self.selected_rules()
        result = Queue()
        self.pending = result
        self.status.set(self.tr("正在打开项目…") + f" {path.name}")

        def read():
            try:
                location = path.resolve()
                if create:
                    if location.exists():
                        raise ValueError("这个项目文件已存在，请选择新文件名。")
                    project = ProductionProject(location.stem, "EP01", "SB01", rules=rules)
                    project.save(location)
                else:
                    project = ProductionProject.open(location)
                result.put((location, project))
            except (OSError, ValueError, AttributeError, TypeError) as error:
                result.put(error)

        def receive():
            if self.pending is not result:
                return
            try:
                entry = result.get_nowait()
            except Empty:
                self.root.after(40, receive)
                return
            self.pending = None
            self.status.set("")
            if isinstance(entry, Exception):
                self.show_error(entry)
                return
            location, project = entry
            try:
                self.open(stage, location, project=project)
            except (OSError, ValueError, RuntimeError, tk.TclError) as error:
                self.show_error(error)
            else:
                self.hide()

        Thread(target=read, daemon=True).start()
        self.root.after(40, receive)

    def open(self, stage, path=None, *, project=None, **options):
        if stage == "action_sequence":
            self.open_action(path)
            return None
        location = Path(path).resolve() if path else None
        if location:
            project = project or ProductionProject.open(location)
        rules = project.rules if project else self.selected_rules()
        if stage == "inventory" and project:
            sources = shot_sources(project) if project.shots else tuple(project.sources)
            sid = options.get("source_id")
            source = next((s for s in sources if s.id == sid), None)
            if source is None and len(sources) > 1:
                raise ValueError("本组有多版剧本。请从选中镜头的「分析本组资产」进入。")
            if source is None and sources:
                source = sources[0]
            options["source"] = source
        key = (os.path.normcase(str(location)) if location else "", stage,
               options.get("start_task") if stage == "drafts" else
               options["source"].id if options.get("source") else rules if not location else None)
        existing = key in self.tasks.tasks
        task = self.tasks.open(key, lambda page, changed: ProductionStageTask(
            self, page, changed, stage, location, project, rules, options,
        ))
        if location:
            self.remember_project(project, location)
        if existing and options.get("reference_id"):
            task.editor.controller.select_imported_reference(options["reference_id"], options.get("reference_kind", ""))
        if existing and options.get("source"):
            source = options["source"]
            task.editor.controller.update_linked_source(source.text, f"{source.name} · {source.version}",
                                                        asset_shot_context(project, source))
        if options.get("asset_report"):
            task.offer_asset_report(options["asset_report"])
        if options.get("source_id") and stage == "shots":
            task.select_script(options["source_id"], project)
        return task

    def save(self, path, base, edited):
        latest = ProductionProject.open(path)
        result = merge_project_edits(base, edited, latest)
        if result != latest:
            result.save(path)
        self.remember_project(result, path)
        return result

    def script_to_shots(self, rules, title, script, *, existing):
        from .script_handoff_dialog import choose_project_for_script

        choice = choose_project_for_script(self.root, title, script, rules, existing=existing)
        if not choice:
            return False
        location, project, source = choice
        self.open("shots", location, project=project, source_id=source.id)
        return True

    def use_asset_report(self, path, report):
        if path is None:
            choice = choose_project_file(self.root)
            if not choice:
                return False
            path = Path(choice).resolve()
        project = ProductionProject.open(path)
        file = _asset_plan_path(path)
        file.parent.mkdir(exist_ok=True)
        if file.is_file() and file.read_text(encoding="utf-8") != report:
            if not messagebox.askyesno(self.tr("资产分析"), self.tr("替换本组已采用的资产分析稿？"), parent=self.root):
                return False
        atomic_text(file, report)
        self.open("generate_assets", path, project=project, asset_report=report)
        return True


class StageEditor:
    """Give the shared tab bar one close/save interface for all tool panels."""

    def __init__(self, frame):
        self.frame = frame
        self.controller = None

    def dirty(self):
        check = getattr(self.controller, "dirty", None)
        return bool(check and check())

    def save(self):
        save = getattr(self.controller, "save", None)
        return save() if save else None

    def allow_close(self):
        check = getattr(self.controller, "allow_close", None)
        if check:
            return check()
        return not getattr(self.controller, "busy", False)


class TaskProject:
    """Adapt image, layout and text tools to saved snapshots of one group."""

    def __init__(self, task):
        self.task = task
        self.window = task.workspace.root
        self.path, self.rules = task.path, task.rules
        self.project = deepcopy(task.project)
        self.base = deepcopy(task.project)
        self.registry, self.validators = task.workspace.registry, task.workspace.validators
        self.image_session, self.text_session = task.workspace.image_session, task.workspace.text_session

    def latest_project(self):
        return ProductionProject.open(self.path)

    def notify_project(self, project):
        self.project = deepcopy(project)
        self.base = deepcopy(project)
        self.task.project = project
        self.task.workspace.remember_project(project, self.path)

    def save_project(self, candidate):
        saved = self.task.workspace.save(self.path, self.base, candidate)
        self.notify_project(saved)
        return saved

    def save(self):
        return self.save_project(self.project)

    def refresh(self):
        self.task.changed()

    def editor(self, parent, height=8):
        return scrolledtext.ScrolledText(parent, height=height, wrap="word")

    def buttons(self, bar, *entries):
        buttons = []
        for caption, run in entries:
            button = ttk.Button(bar, text=translate(self.window, caption), command=lambda run=run: self.task.guard(run))
            button.pack(side="left", padx=(0, 6))
            buttons.append(button)
        return buttons

    def validator_path(self):
        validator = Path(self.validators.get(self.rules, "")).expanduser()
        if not validator.is_file():
            raise ValueError("请先为当前制作规则设置可用的校验脚本。")
        return validator

    def camera_notes(self):
        return camera_findings_text(
            project_camera_cuts(self.latest_project()), english=getattr(self.window, "ui_language", "zh") == "en",
        )

    def open_assets_for_shots(self, *, owner=None, preferred_source=""):
        return self.task.navigate("inventory", source_id=preferred_source)


class ProductionStageTask:
    def __init__(self, workspace, page, changed, stage, path, project, rules, options):
        self.workspace, self.page, self.changed = workspace, page, changed
        self.stage, self.path, self.project, self.rules = stage, path, project, rules
        self.stage_variable = tk.StringVar(page, stage, name=f"{page.winfo_name()}_production_stage")
        self.confirmation = None
        bar = ttk.Frame(page, name="production_task_header", padding=(9, 4))
        bar.pack(fill="x")
        self.heading = ttk.Label(bar, style="A.Muted.TLabel")
        self.heading.pack(side="left", fill="x", expand=True)
        self.next_button = ttk.Button(bar, name="next_stage", style="Primary.Workbench.TButton",
                                      command=lambda: self.guard(self.next_stage))
        if stage in NEXT_STAGE and (project or stage != "inventory"):
            self.next_button.pack(side="right", padx=(6, 0))
        self.report_button = ttk.Button(bar, name="use_asset_report", command=lambda: self.guard(self.load_asset_report))
        if stage == "generate_assets" and path and _asset_plan_path(path).is_file():
            self.report_button.pack(side="right", padx=(4, 0))
        self.approved = ttk.Button(bar, name="open_approved_assets",
                                   command=lambda: self.guard(lambda: self.navigate("assets")))
        if stage in {"generate_assets", "generate_board"}:
            self.approved.pack(side="right", padx=(4, 0))
        body = ttk.Frame(page, name="production_task")
        body.pack(fill="both", expand=True)
        self.editor = StageEditor(body)
        self.owner = TaskProject(self) if project else None
        self.editor.controller = self.build(body, options)
        self.refresh_language()

    def tr(self, caption):
        return self.workspace.tr(caption)

    def caption(self, *, distinguish=False):
        label = self.tr(CAPTIONS[self.stage])
        if self.project:
            label = f"{self.project.group} · {label}"
            if distinguish:
                label += f" / {(self.project.name or self.path.stem)[:16]}"
        return label + (" •" if self.editor.dirty() else "")

    def full_caption(self):
        if self.project:
            return f"{self.project.name or self.path.stem} / {self.project.episode} / {self.caption()}"
        return self.caption()

    def refresh_language(self):
        self.heading.configure(text=self.full_caption())
        if self.stage in NEXT_STAGE:
            self.next_button.configure(text=self.tr("下一步 · {tool}").format(tool=self.tr(CAPTIONS[NEXT_STAGE[self.stage]])))
        self.report_button.configure(text=self.tr("带入已采用的资产清单"))
        self.approved.configure(text=self.tr("批准图像"))
        language = getattr(self.editor.controller, "refresh_language", None)
        if language:
            language()

    def activate(self):
        controller = self.editor.controller
        refresh_models = getattr(controller, "refresh_models", None)
        if refresh_models:
            refresh_models()
        if (not self.path or getattr(controller, "busy", False)
                or (self.editor.dirty() and not isinstance(self.owner, TaskProject))):
            return
        sync = getattr(controller, "sync_project", None)
        if not sync:
            return
        try:
            latest = ProductionProject.open(self.path)
            if self.project == latest:
                return
            sync(latest)
            self.project = latest
            if isinstance(self.owner, TaskProject):
                self.owner.notify_project(latest)
            self.heading.configure(text=self.full_caption())
        except (ValueError, OSError, RuntimeError, tk.TclError) as error:
            self.workspace.show_error(error)

    def guard(self, operation):
        try:
            return operation()
        except (ValueError, OSError, RuntimeError, tk.TclError) as error:
            self.workspace.show_error(error)
            return None

    def save_snapshot(self, base, draft):
        result = self.workspace.save(self.path, base, draft)
        self.project = result
        self.changed()
        return result

    def build(self, body, options):
        ws = self.workspace
        if self.stage in {"script", "inventory"}:
            from .storyboard_planning_dialog import open_storyboard_planning
            source = options.get("source")
            return open_storyboard_planning(
                body, ws.text_session, task="script" if self.stage == "script" else "assets",
                rules=self.rules, approved_script=source.text if source else None,
                approved_title=f"{source.name} · {source.version}" if source else None,
                shot_context=asset_shot_context(self.project, source) if source else None, embedded=True,
                on_change=self.changed, on_close=lambda: self.close_tab(),
                on_use_script=(lambda title, text, **opts: ws.script_to_shots(self.rules, title, text, **opts))
                if self.stage == "script" else None,
                on_use_assets=(lambda _, report: ws.use_asset_report(self.path, report))
                if self.stage == "inventory" else None,
            )
        if self.stage in {"generate_assets", "generate_board"}:
            from .image_production_dialog import ImageProductionDialog
            return ImageProductionDialog(
                self.owner, ws.image_session, mount=body,
                kind="故事板" if self.stage == "generate_board" else "角色",
                reference_id=options.get("reference_id", ""), reference_kind=options.get("reference_kind", ""),
            )
        if self.stage == "drafts":
            from .drafting_dialog import DraftingDialog
            self.owner = ProductionDialog(
                body, ws.validators, ws.registry, ws.text_session, ws.image_session, self.rules, lambda _: None,
                embedded=True, with_panel=False, destination="shots", on_save=self.save_snapshot,
                on_stage=self.navigate,
            )
            self.owner.load(deepcopy(self.project), self.path, source_id=options.get("source_id", ""))
            return DraftingDialog(self.owner, ws.text_session, start_task=options.get("start_task", SHOT_TASK), parent=body)
        if self.stage == "layout":
            from .layout_dialog import LayoutDialog
            return LayoutDialog(self.owner, mount=body)
        if self.stage == "costume":
            from .reference_tools_dialog import open_reference_tools
            open_reference_tools(
                self.workspace.root, self.project, self.path, "costume",
                lambda reference_id: self.navigate("generate_assets", reference_id=reference_id, reference_kind="costume"),
                mount=body, on_close=self.close_tab, latest_project=self.owner.latest_project,
                save_project=self.owner.save_project,
            )
            return None
        editor = ProductionDialog(
            body, ws.validators, ws.registry, ws.text_session, ws.image_session, self.rules, lambda _: None,
            embedded=True, destination=self.stage, on_save=self.save_snapshot, on_stage=self.navigate,
        )
        editor.load(deepcopy(self.project), self.path, source_id=options.get("source_id", ""))
        return editor

    def close_tab(self):
        for key, task in self.workspace.tasks.tasks.items():
            if task is self:
                self.workspace.tasks.request_close(key)
                return

    def select_script(self, source_id, project):
        editor = self.editor.controller
        if not editor.sync_project(project) and source_id not in {s.id for s in editor.project.sources}:
            editor.status.set(self.tr("请先保存或取消当前编辑，再切换到新剧本版本。"))
        if source_id in {s.id for s in editor.project.sources}:
            editor.refresh_sources(source_id)

    def offer_asset_report(self, report):
        controller = self.editor.controller
        if not controller or not hasattr(controller, "prompt"):
            return
        if not controller.prompt.get("1.0", "end-1c").strip():
            controller.prompt.insert("1.0", report)
        else:
            self.report_button.pack(side="right", padx=(4, 0))

    def load_asset_report(self):
        report = _asset_plan_path(self.path).read_text(encoding="utf-8")
        controller = self.editor.controller
        entry = controller.prompt
        if not entry.get("1.0", "end-1c").strip():
            self.offer_asset_report(report)
        elif entry.get("1.0", "end-1c").strip() == report.strip():
            return
        elif messagebox.askyesno(self.tr("资产分析"), self.tr("在当前补充需求末尾追加已采用的资产清单？"),
                                 parent=self.workspace.root):
            entry.insert("end-1c", "\n\n" + report)

    def next_stage(self):
        if self.stage == "inventory" and self.editor.controller.output.get("1.0", "end-1c").strip():
            self.editor.controller.use_assets()
            return
        options = {}
        if self.stage == "shots":
            selection = self.editor.controller.shots.selection()
            if selection:
                shot = next((item for item in self.editor.controller.project.shots if item.id == selection[0]), None)
                if shot is not None:
                    options["source_id"] = shot.source
            elif self.editor.controller.project.sources:
                options["source_id"] = self.editor.controller.current_source().id
        self.navigate(NEXT_STAGE[self.stage], **options)

    def navigate(self, stage, **options):
        if stage not in CAPTIONS and stage != "action_sequence":
            if stage == "preflight":
                from .preflight_dialog import open_preflight_dialog
                return open_preflight_dialog(self.workspace.root, self.workspace.validators[self.rules], self.rules)
            raise ValueError(f"当前工作区不支持此入口：{stage}")
        if self.stage in {"shots", "prompts", "assets"} and self.editor.dirty():
            if self.editor.save() is False:
                return None
        return self.workspace.open(stage, self.path, **options)
