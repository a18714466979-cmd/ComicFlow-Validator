"""Create image jobs and review their candidates in the single-group workbench."""

import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import messagebox, ttk
from urllib.parse import urlsplit

from PIL import Image, ImageOps, ImageTk

from .ui_language import translate
from .image_api import EDIT, IMAGE_PROVIDERS, REFERENCE, TEXT, ImageRequestError, ImageSettings, query_image, submit_image
from .production_dialog import field, write_text
from .production_images import (
    KINDS, STATUS, approve_candidate, candidate_path, image_prompt, job_request_prompt, local_patch, pinned_assets,
    prepare_job, shot_input, storyboard_job_page, store_reply,
)
from .production_rules import CHINESE
from .shot_review import pixel_selection


class ImageProductionDialog:
    def __init__(self, production, session, *, kind="角色", reference_id="", reference_kind=""):
        self.production, self.session = production, session
        self.project, self.path = production.project, production.path
        self.busy = False
        self.reference_id = reference_id
        self.reference_kind = reference_kind
        self.window = tk.Toplevel(production.window)
        self.window.title(translate(self.window, "ComicFlow 图像制片"))
        self.window.geometry("1060x790")
        self.window.minsize(830, 635)
        self.window.transient(production.window)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        self.status = tk.StringVar(self.window, translate(self.window, "密钥只在本次软件运行期间使用。"))
        ttk.Label(self.window, textvariable=self.status, wraplength=990).pack(anchor="w", padx=10, pady=(0, 8))
        form, history = (ttk.Frame(self.tabs, padding=9) for _ in range(2))
        self.tabs.add(form, text=translate(self.tabs, "新建生图任务"))
        self.tabs.add(history, text=translate(self.tabs, "候选与任务"))
        self.setup_form(form, kind)
        self.setup_history(history)
        if reference_id:
            self.select_imported_reference()

    def close(self):
        if self.busy:
            self.status.set("正在提交或查询，请等本次请求返回。")
        else:
            self.window.destroy()

    def run(self, action):
        try:
            action()
        except Exception as exc:
            messagebox.showerror(translate(self.window, "图像制片"), translate(self.window, str(exc)), parent=self.window)

    def buttons(self, bar, *entries):
        for title, action in entries:
            ttk.Button(bar, text=translate(bar, title), command=lambda run=action: self.run(run)).pack(side="left", padx=(0, 6))

    def setup_form(self, page, kind):
        config = ttk.Frame(page)
        config.pack(fill="x")
        self.provider = tk.StringVar(self.window, next(reversed(self.session), next(iter(IMAGE_PROVIDERS))))
        self.base, self.model, self.key, self.secret_id = (tk.StringVar(self.window) for _ in range(4))
        self.modes = (TEXT,)
        self.target = tk.StringVar(self.window)
        provider = field(config, 0, "图像服务商", self.provider, tuple(IMAGE_PROVIDERS))
        provider.bind("<<ComboboxSelected>>", self.pick_provider)
        field(config, 1, "API 基础地址", self.base)
        self.model_field = field(config, 2, "图像模型 ID", self.model)
        self.key_label = ttk.Label(config, text="API Key")
        self.key_label.grid(row=3, column=0, sticky="w")
        ttk.Entry(config, textvariable=self.key, show="*").grid(row=3, column=1, sticky="ew")
        self.signing_id = field(config, 4, "腾讯云 SecretId", self.secret_id)
        self.mode_picker = field(config, 5, "生成模式", tk.StringVar(self.window), (translate(config, TEXT),))
        self.mode_picker.current(0)
        self.mode_picker.bind("<<ComboboxSelected>>", self.update_scope)
        self.kind_picker = field(config, 6, "候选用途", tk.StringVar(self.window),
                                 tuple(translate(config, kind) for kind in KINDS))
        self.kind_picker.current(KINDS.index(kind))
        self.kind_picker.bind("<<ComboboxSelected>>", self.update_scope)
        target_label = "目标镜头／故事板页" if self.project.rules == CHINESE else "净板目标镜头"
        self.shot_picker = field(config, 7, target_label, self.target, ())
        self.shot_picker["values"] = tuple(
            f"{self.project.group}-{n:02d} · {shot.scene or shot.anchor}" for n, shot in enumerate(self.project.shots, 1)
        )
        if self.project.shots:
            self.shot_picker.current(0)
        self.capability = tk.StringVar(self.window)
        ttk.Label(page, textvariable=self.capability, wraplength=960).pack(anchor="w", pady=5)
        inputs = ttk.Frame(page)
        inputs.pack(fill="both", expand=True)
        reference = ttk.LabelFrame(inputs, text=translate(inputs, "批准参考图"), padding=6)
        reference.pack(side="left", fill="both", padx=(0, 8))
        self.refs = tk.Listbox(reference, selectmode="extended", exportselection=False, width=42, height=9)
        self.refs.pack(fill="both", expand=True)
        self.refs.bind("<<ListboxSelect>>", self.update_base_choice)
        self.ref_images = []
        self.base_reference = ttk.Combobox(reference, state="disabled", width=39)
        self.base_reference.pack(fill="x", pady=4)
        self.base_reference.bind("<<ComboboxSelected>>", self.clear_box)
        reference_buttons = ttk.Frame(reference)
        reference_buttons.pack(fill="x")
        self.buttons(reference_buttons, ("查看所选参考图", self.view_reference), ("框选返修区域", self.pick_box))
        self.box_note = tk.StringVar(self.window, "")
        self.region = None
        ttk.Label(reference, textvariable=self.box_note).pack(anchor="w")
        prompts = ttk.LabelFrame(inputs, text=translate(inputs, "本次生图提示词"), padding=6)
        prompts.pack(side="left", fill="both", expand=True)
        self.prompt = self.production.editor(prompts, 11)
        self.prompt.pack(fill="both", expand=True)
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=(6, 0))
        self.buttons(bar, ("按用途载入提示模板", self.fill_prompt), ("预览本次发送", self.preview_request),
                     ("确认并提交生图", self.send))
        self.refresh_refs()
        self.pick_provider()
        self.fill_prompt()

    def select_imported_reference(self):
        if REFERENCE not in self.modes:
            alternatives = dict.fromkeys((*reversed(self.session), *IMAGE_PROVIDERS))
            provider = next(name for name in alternatives if REFERENCE in IMAGE_PROVIDERS[name].modes)
            self.provider.set(provider)
            self.pick_provider()
        self.mode_picker.current(self.modes.index(REFERENCE))
        self.update_scope()
        index = next(index for index, item in enumerate(self.ref_images) if item.id == self.reference_id)
        self.refs.selection_set(index)
        self.refs.see(index)
        self.fill_prompt()
        self.status.set(translate(self.window, "已带入设计参考。可在预览中检查参考图和提示词。"))

    def setup_history(self, page):
        top = ttk.Frame(page)
        top.pack(fill="x")
        ttk.Label(top, text=translate(top, "图像任务")).pack(side="left", padx=(0, 8))
        self.jobs = ttk.Combobox(top, state="readonly")
        self.jobs.pack(side="left", fill="x", expand=True)
        self.jobs.bind("<<ComboboxSelected>>", self.show_job)
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=7)
        self.buttons(bar, ("查询所选任务", self.query), ("带入任务连接设置", self.use_job_settings),
                     ("登记已核对后台", self.clear_unknown))
        self.details = self.production.editor(page, 9)
        self.details.pack(fill="both", expand=True)
        self.details.configure(state="disabled")
        output = ttk.Frame(page)
        output.pack(fill="x", pady=6)
        ttk.Label(output, text=translate(output, "候选输出")).pack(side="left", padx=(0, 8))
        self.outputs = ttk.Combobox(output, state="readonly")
        self.outputs.pack(side="left", fill="x", expand=True)
        review = ttk.Frame(page)
        review.pack(fill="x")
        self.buttons(review, ("查看候选与批准参考", self.view_candidate), ("生成局部合成", self.compose),
                     ("批准并加入正式交付", self.approve))
        self.refresh_jobs()

    def pick_provider(self, _event=None):
        name = self.provider.get()
        preset = IMAGE_PROVIDERS[name]
        previous = self.session.get(name)
        self.base.set(previous.base if previous else preset.base)
        self.model.set(previous.model if previous else preset.model)
        self.key.set(previous.key if previous else "")
        self.secret_id.set(previous.secret_id if previous else "")
        self.signing_id.configure(state="normal" if preset.asynchronous else "disabled")
        self.model_field.configure(state="readonly" if preset.asynchronous else "normal")
        self.key_label.configure(text="腾讯云 SecretKey" if preset.asynchronous else "API Key")
        previous_mode = self.mode()
        self.modes = preset.modes
        self.mode_picker["values"] = tuple(translate(self.window, mode) for mode in self.modes)
        self.mode_picker.current(self.modes.index(previous_mode) if previous_mode in self.modes else 0)
        queue = "异步，可凭任务号查询" if preset.asynchronous else "同步返回"
        self.capability.set(f"默认模型的接入能力 · {queue} · 批准参考图最多 {preset.references} 张。"
                            "自填模型时，以所选模型支持的模式为准。")
        if preset.adapter == "dashscope" and not self.base.get():
            self.capability.set(self.capability.get() + " 请填百炼控制台提供的区域工作空间地址，末尾到 /api/v1。")
        self.update_scope()

    def mode(self):
        return self.modes[self.mode_picker.current()]

    def kind(self):
        return KINDS[self.kind_picker.current()]

    def update_scope(self, _event=None):
        self.refs.configure(state="disabled" if self.mode() == TEXT else "normal")
        paged = (self.project.rules == CHINESE and self.kind() == "故事板"
                 and (len(self.project.shots) == 10 or self.mode() == EDIT))
        targeted = (paged or self.kind() == "净板") and self.project.shots
        self.shot_picker.configure(state="readonly" if targeted else "disabled")
        self.update_base_choice()

    def refresh_refs(self):
        self.refs.configure(state="normal")
        self.ref_images = list(self.project.images)
        self.refs.delete(0, "end")
        for item in self.ref_images:
            self.refs.insert("end", f"{item.filename} · {item.version}")
        self.update_scope()

    def update_base_choice(self, _event=None):
        selected = self.refs.curselection()
        choices = tuple(self.refs.get(index) for index in selected)
        old = self.base_reference.get()
        self.base_reference["values"] = choices
        editing = self.mode() == EDIT and bool(choices)
        self.base_reference.configure(state="readonly" if editing else "disabled")
        value = old if editing and old in choices else choices[0] if editing else ""
        self.base_reference.set(value)
        if value != old or not editing:
            self.clear_box()

    def clear_box(self, _event=None):
        self.region = None
        self.box_note.set("先选批准图，再指定返修底图。" if self.mode() == EDIT else "")

    def chosen_refs(self):
        if self.mode() == TEXT:
            return []
        selected = [self.ref_images[index] for index in self.refs.curselection()]
        if self.mode() == EDIT:
            index = self.base_reference.current()
            if index >= 0:
                selected.insert(0, selected.pop(index))
        elif self.reference_id:
            selected.sort(key=lambda item: item.id != self.reference_id)
        return selected

    def selected_shot(self):
        index = self.shot_picker.current()
        return self.project.shots[index].id if index >= 0 else ""

    def fill_prompt(self):
        mode = self.mode()
        refs = self.chosen_refs() if mode == EDIT else []
        write_text(self.prompt, image_prompt(self.project, self.kind(), self.selected_shot(), mode,
                                             refs[0] if refs else None))

    def view_reference(self):
        indices = self.refs.curselection()
        if not indices:
            raise ValueError("请选择批准参考图。")
        selected = self.ref_images[indices[0]]
        self.show_pictures(((selected.filename, self.project.checked_image(self.path, selected)),))

    def pick_box(self):
        selected = self.chosen_refs()
        if self.mode() != EDIT or not selected:
            raise ValueError("请切换局部编辑，选择批准参考图和返修底图。")
        original = self.project.checked_image(self.path, selected[0])
        box = self.select_rectangle(original, "在批准原图上标出修改范围")
        if box:
            self.region = box
            self.box_note.set(f"返修底图选区 {box}")

    def settings(self):
        return ImageSettings(self.provider.get(), self.base.get().strip(), self.model.get().strip(),
                             self.key.get().strip(), self.secret_id.get().strip())

    def prepare(self, references, *, preview=False):
        settings = self.settings()
        prompt = self.prompt.get("1.0", "end-1c")
        if self.mode() == REFERENCE and references and references[0].id == self.reference_id:
            note = ("第一张参考图仅指定服装的版型、层次、颜色和面料，保留目标角色身份。"
                    if self.reference_kind == "costume" else
                    "第一张参考图仅指定人物动作、重心、朝向和机位，按目标角色的正式资产生成。")
            prompt += "\n" + note
        job, request = prepare_job(self.project, self.path, settings, self.mode(), self.kind(),
                                   self.selected_shot(), prompt, [item.id for item in references],
                                   self.region or (), preview=preview)
        return settings, job, request

    def summary(self, job, *, request_url="", request_prompt=""):
        refs = "\n".join(f"  {n}. {item['filename']} · {item['version']} · {item['sha256']}"
                         for n, item in enumerate(job["references"], 1)) or "  无"
        _, shot = shot_input(self.project, job["shot"])
        target = f" · {shot.anchor}" if shot else ""
        lines = [
            f"{job['provider']} · {job['model']} · {translate(self.window, job['mode'])} · "
            f"{translate(self.window, job['kind'])}{target}",
            f"{translate(self.window, '接收地址')} {request_url or urlsplit(job['base']).netloc}",
        ]
        if request_url:
            lines.append(translate(self.window, "本地预览，尚未发送。提交生图时再填写 API 密钥。"))
        else:
            request_id = job.get("last_request_id") or job.get("request_id") or "无"
            lines.extend((f"状态 {STATUS.get(job['status'], '待核对')}",
                          f"任务号 {job.get('task_id') or '无'} · 请求号 {request_id}"))
        lines.append(translate(self.window, "批准参考图") + f"\n{refs}")
        if job["box"]:
            lines.append(f"批准原图选区 {job['box']}")
        if job.get("message"):
            lines.append(job["message"])
        lines.append(translate(self.window, "本次提示词") + f"\n{request_prompt or job['prompt']}")
        return "\n\n".join(lines)

    def preview_request(self):
        references = self.chosen_refs()
        _, job, request = self.prepare(references, preview=True)
        original = references[0] if job["mode"] == EDIT else None
        self.show_report("本次发送清单", self.summary(job, request_url=request.full_url,
                                                    request_prompt=job_request_prompt(job, original)))

    def show_report(self, title, content):
        dialog = tk.Toplevel(self.window)
        dialog.title(translate(dialog, title))
        dialog.geometry("830x580")
        dialog.transient(self.window)
        editor = self.production.editor(dialog)
        editor.pack(fill="both", expand=True, padx=10, pady=10)
        write_text(editor, content)
        editor.configure(state="disabled")
        self.wait(dialog)

    def wait(self, dialog):
        dialog.grab_set()
        self.window.wait_window(dialog)
        self.window.grab_set()

    def send(self):
        if self.busy:
            return
        settings, job, request = self.prepare(self.chosen_refs())
        settings_fields = ("provider", "base", "model", "mode", "kind", "shot", "prompt", "references", "box")
        if any(previous["status"] in {"submitting", "queued", "unknown"}
               and all(previous[key] == job[key] for key in settings_fields) for previous in self.project.image_jobs):
            raise ValueError("已有同内容任务待核对。请在「候选与任务」查看结果后再决定是否重试。")
        destination = urlsplit(settings.base).netloc
        details = translate(self.window, "发送提示词和 {count} 张已选参考图到 {host}？\n模型 {model}").format(
            count=len(job["references"]), host=destination, model=settings.model,
        )
        mode, kind = (translate(self.window, job[key]) for key in ("mode", "kind"))
        usage = translate(self.window, "调用使用该服务的额度。")
        if not messagebox.askyesno(translate(self.window, "提交生图"), f"{mode} · {kind}\n{details}\n{usage}",
                                   parent=self.window):
            return
        self.session.pop(settings.provider, None)
        self.session[settings.provider] = settings
        self.project.image_jobs.append(job)
        try:
            self.project.save(self.path)
        except Exception:
            self.project.image_jobs.pop()
            raise
        self.tabs.select(1)
        self.refresh_jobs(job)
        self.start(job, lambda: submit_image(settings, request))

    def refresh_jobs(self, current=None):
        self.jobs["values"] = tuple(
            f"{index:02d} · {job['kind']} · {job['provider']} · {STATUS.get(job['status'], '待核对')}"
            for index, job in enumerate(self.project.image_jobs, 1)
        )
        if self.project.image_jobs:
            index = self.project.image_jobs.index(current) if current else len(self.project.image_jobs) - 1
            self.jobs.current(index)
            self.show_job()

    def picked_job(self):
        index = self.jobs.current()
        if index < 0:
            raise ValueError("请选择一个任务。")
        return self.project.image_jobs[index]

    def show_job(self, _event=None):
        job = self.picked_job()
        self.details.configure(state="normal")
        write_text(self.details, self.summary(job))
        self.details.configure(state="disabled")
        self.outputs["values"] = tuple(f"候选 {n:02d} · {out['width']}×{out['height']}"
                                       f"{' · 已合成并复验选区外像素' if out.get('patch_sha') else ''}"
                                       for n, out in enumerate(job["outputs"], 1))
        if job["outputs"]:
            self.outputs.current(job.get("approved_output", 0))
        else:
            self.outputs.set("")

    def use_job_settings(self, *, jump=True):
        job = self.picked_job()
        self.provider.set(job["provider"])
        self.pick_provider()
        self.base.set(job["base"])
        self.model.set(job["model"])
        if jump:
            self.tabs.select(0)

    def query(self):
        if self.busy:
            return
        job = self.picked_job()
        if not job.get("task_id") or job["status"] not in {"queued", "unknown", "submitting"}:
            raise ValueError("请选择带服务商任务号的待查询任务。")
        settings = self.settings()
        if (settings.provider, settings.base.rstrip("/"), settings.model) != (job["provider"], job["base"], job["model"]):
            raise ValueError("先带入所选任务的连接设置，再填写对应账户的密钥。")
        if not settings.key or not settings.secret_id:
            raise ValueError("请在「新建生图任务」填写该账户的 SecretId 和 SecretKey。")
        self.session[settings.provider] = settings
        self.start(job, lambda: query_image(settings, job["task_id"]))

    def clear_unknown(self):
        if self.busy:
            return
        job = self.picked_job()
        if job.get("task_id") or job["status"] not in {"unknown", "submitting"}:
            raise ValueError("这个操作用于没有任务号、结果未确认的记录。")
        if messagebox.askyesno(translate(self.window, "登记已核对"), translate(self.window, "请确认已在服务商后台查看是否受理和扣费，再结束本地等待。"), parent=self.window):
            job["status"] = "closed"
            self.project.save(self.path)
            self.refresh_jobs(job)

    def start(self, job, call):
        self.busy = True
        self.status.set("正在向所选服务提交或查询…")
        pending = Queue()

        def worker():
            try:
                pending.put(call())
            except Exception as exc:
                pending.put(exc)

        def receive():
            try:
                reply = pending.get_nowait()
            except Empty:
                self.window.after(100, receive)
                return
            self.busy = False
            try:
                if isinstance(reply, Exception):
                    raise reply
                store_reply(self.path, job, reply)
                self.status.set(STATUS[job["status"]])
            except ImageRequestError as exc:
                job.update(status="unknown" if exc.uncertain or job.get("task_id") else "failed", message=str(exc))
                if exc.request_id:
                    job.setdefault("request_id", exc.request_id)
                    job["last_request_id"] = exc.request_id
                self.status.set(str(exc))
            except Exception:
                job.update(status="unknown", message="服务结果或候选文件无法登记，可按任务号继续查询。")
                self.status.set(job["message"])
            self.run(lambda: self.project.save(self.path))
            self.refresh_jobs(job)

        Thread(target=worker, daemon=True).start()
        self.window.after(100, receive)

    def picked_output(self):
        job = self.picked_job()
        index = self.outputs.current()
        if index < 0 or len(job["outputs"]) <= index:
            raise ValueError("请选择可读取的候选图片。")
        return job, index, job["outputs"][index]

    def view_candidate(self):
        job, _, out = self.picked_output()
        images = [(item.filename, path) for item, path in pinned_assets(self.project, self.path, job)]
        images = images[:1] + [("模型返回原图", candidate_path(self.path, out["received_sha256"], out["format"]))]
        if out.get("patch_sha"):
            images.append(("局部合成图", candidate_path(self.path, out["patch_sha"])))
        self.show_pictures(images)

    def compose(self):
        job, index, out = self.picked_output()
        if job["mode"] != EDIT or job["status"] != "ready":
            raise ValueError("请选择待核对的局部编辑候选。")
        path = candidate_path(self.path, out["sha256"])
        box = self.select_rectangle(path, "在模型返回图上框选与批准原图对应的局部")
        if box is None:
            return
        local_patch(self.project, self.path, job, out, box)
        self.project.save(self.path)
        self.show_job()
        self.outputs.current(index)
        detail = "局部按选区尺寸对齐。" if out["aligned"] else ""
        self.status.set(f"{detail}已重新解码合成图，实测选区外 RGB 和透明度像素一致。")
        self.view_candidate()

    def approve(self):
        if self.busy:
            return
        job, index, out = self.picked_output()
        if job["status"] != "ready":
            raise ValueError("请选择待批准的候选。")
        self.view_candidate()
        dialog = tk.Toplevel(self.window)
        dialog.title(translate(dialog, "批准候选图"))
        dialog.geometry("720x270")
        dialog.transient(self.window)
        panel = ttk.Frame(dialog, padding=10)
        panel.pack(fill="both", expand=True)
        default = self.default_name(job)
        name = tk.StringVar(dialog, default)
        version = tk.StringVar(dialog, "R1" if job["mode"] != EDIT else "")
        reason, inspection = (tk.StringVar(dialog) for _ in range(2))
        fields = (("正式文件名", name), ("版本", version), ("实际处理理由", reason), ("实际核图结果", inspection))
        for row, (caption, value) in enumerate(fields):
            field(panel, row, caption, value)
        replace = tk.BooleanVar(dialog)
        if job["mode"] == EDIT:
            ttk.Checkbutton(panel, text=translate(panel, "替换同名正式图，保留批准原图及来源链"), variable=replace).grid(
                row=4, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(panel, text=translate(panel, "核对目标画面、选区和实际尺寸后再批准。"), wraplength=660).grid(row=5, column=0, columnspan=2, sticky="w")
        bar = ttk.Frame(panel)
        bar.grid(row=6, column=0, columnspan=2, sticky="w", pady=7)

        def accept():
            try:
                asset = approve_candidate(self.project, self.path, job, index, name.get(), version.get(),
                                          reason.get(), inspection.get(), replace_original=replace.get())
            except (ValueError, OSError) as exc:
                messagebox.showerror(translate(dialog, "批准候选图"), str(exc), parent=dialog)
                return
            self.production.refresh()
            self.refresh_refs()
            self.refresh_jobs(job)
            self.status.set(f"已批准 {asset.filename}。请继续执行逐格复核。")
            dialog.destroy()

        ttk.Button(bar, text=translate(bar, "确认批准"), command=accept).pack(side="left")
        ttk.Button(bar, text=translate(bar, "取消"), command=dialog.destroy).pack(side="left", padx=6)
        self.wait(dialog)

    def default_name(self, job):
        if job["mode"] == EDIT:
            return job["references"][0]["filename"]
        if job["kind"] == "故事板":
            return storyboard_job_page(self.project, job["shot"])[2]
        if job["kind"] == "净板":
            number, shot = shot_input(self.project, job["shot"])
            if shot:
                return f"scene_{shot.scene}_details_{number:02d}_16x9.png"
        return {"角色": "other_characters_角色名_16x9.png", "道具 / HUD": "props_道具名_16x9.png",
                "场景": "scene_地点名_main_16x9.png"}.get(job["kind"], "候选_16x9.png")

    def show_pictures(self, pictures):
        panel = tk.Toplevel(self.window)
        panel.title(translate(panel, "图像核对"))
        panel.geometry("1040x710")
        panel.transient(self.window)
        tabs = ttk.Notebook(panel)
        tabs.pack(fill="both", expand=True, padx=8, pady=8)
        for title, path in pictures:
            section = ttk.Frame(tabs)
            tabs.add(section, text=translate(tabs, title))
            display_picture(section, path)
        self.wait(panel)

    def select_rectangle(self, path: Path, title: str):
        return select_image_region(self.window, path, title)


def select_image_region(parent, path, title, *, direction=False):
    panel = tk.Toplevel(parent)
    panel.title(title)
    panel.transient(parent)
    canvas, size, fitted, _ = display_picture(panel, path, zoom=False)
    selected = None
    result = []
    start = None
    controls = ttk.Frame(panel, padding=7)
    controls.pack(fill="x")
    status = tk.StringVar(panel, translate(panel, "从起点拖至终点。" if direction else "拖动框选对应的像素范围。"))
    ttk.Label(controls, textvariable=status).pack(side="left")

    def begin(event):
        nonlocal start, selected
        start, selected = (event.x, event.y), None
        canvas.delete("selection")

    def drag(event):
        if start:
            canvas.delete("selection")
            coords = (*start, event.x, event.y)
            if direction:
                canvas.create_line(*coords, arrow="last", fill="#ffd34e", width=2, tags="selection")
            else:
                canvas.create_rectangle(*coords, outline="#ffd34e", width=2, tags="selection")

    def finish(event):
        nonlocal start, selected
        if start:
            end = event.x, event.y
            if direction:
                selected = tuple((round(x * size[0] / fitted[0]), round(y * size[1] / fitted[1])) for x, y in (start, end))
            else:
                selected = pixel_selection(start, end, (0, 0, *fitted), size)
            if selected:
                status.set(f"已选 {selected}")
            start = None

    def accept():
        if selected:
            result.append(selected)
            panel.destroy()

    for event, action in (("<ButtonPress-1>", begin), ("<B1-Motion>", drag), ("<ButtonRelease-1>", finish)):
        canvas.bind(event, action)
    ttk.Button(controls, text=translate(controls, "确定选区"), command=accept).pack(side="right")
    panel.grab_set()
    parent.wait_window(panel)
    parent.grab_set()
    return result[0] if result else None


def display_picture(parent, path, *, zoom=True):
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
    fitted_image = image.copy()
    fitted_image.thumbnail((880, 525), Image.Resampling.LANCZOS)
    section = ttk.Frame(parent)
    section.pack(fill="both", expand=True)
    section.rowconfigure(0, weight=1)
    section.columnconfigure(0, weight=1)
    canvas = tk.Canvas(section, width=fitted_image.width, height=fitted_image.height, highlightthickness=0, background="#20242a")
    canvas.grid(row=0, column=0, sticky="nsew")

    def put(bitmap):
        canvas.delete("all")
        canvas.photo = ImageTk.PhotoImage(bitmap, master=canvas)
        canvas.create_image(0, 0, image=canvas.photo, anchor="nw")
        canvas.configure(scrollregion=(0, 0, bitmap.width, bitmap.height))
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

    put(fitted_image)
    if zoom:
        xbar = ttk.Scrollbar(section, orient="horizontal", command=canvas.xview)
        ybar = ttk.Scrollbar(section, orient="vertical", command=canvas.yview)
        canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        xbar.grid(row=1, column=0, sticky="ew")
        ybar.grid(row=0, column=1, sticky="ns")
        bar = ttk.Frame(parent, padding=5)
        bar.pack(fill="x")
        ttk.Label(bar, text=f"{image.width}×{image.height}").pack(side="left", padx=8)
        ttk.Button(bar, text=translate(bar, "100% 像素"), command=lambda: put(image)).pack(side="left")
        ttk.Button(bar, text=translate(bar, "适合窗口"), command=lambda: put(fitted_image)).pack(side="left", padx=6)
    return canvas, image.size, fitted_image.size, []
