"""Show the selected image and destination before an optional AI request."""

from hashlib import sha256
import tkinter as tk
from queue import Empty, Queue
from threading import Thread
from tkinter import messagebox, scrolledtext, ttk
from urllib.parse import urlsplit

from .guide_links import guide_button
from .production_rules import ENGLISH
from .ui_language import translate
from .vision import PROVIDERS, VisionSettings, checked_review_focus, prepare_review_image, review_image, review_instructions
from .workbench_jobs import JobOutcome, canonical_location


def vision_job_key(origin, image):
    archive, member, rules = origin
    return "vision", canonical_location(archive), member, rules, sha256(image).hexdigest()


def open_vision_dialog(
    parent: tk.Tk, filename: str, image: bytes, session: dict[str, VisionSettings], *, rules: str = ENGLISH,
    job_registry=None, origin=None, mount=None, on_recover=None, on_open_api=None,
):
    job_key = vision_job_key(origin, image) if job_registry is not None and origin else None
    try:
        image, compressed = prepare_review_image(image)
    except (ValueError, OSError) as exc:
        messagebox.showerror(translate(parent, "图片无法分析"), str(exc), parent=parent)
        return

    if mount is not None:
        dialog = ttk.Frame(mount, name="vision_review_editor", padding=(8, 2))
        dialog.pack(fill="both", expand=True)
    else:
        dialog = tk.Toplevel(parent)
        dialog.title(translate(dialog, "AI 辅助看图"))
        dialog.transient(parent)
        dialog.grab_set()
        dialog.minsize(630, 440)
    dialog.columnconfigure(1, weight=1)
    dialog.rowconfigure(8, weight=1)

    provider = tk.StringVar(dialog, value=next(reversed(session), next(iter(PROVIDERS))))
    base_url, model, api_key = (tk.StringVar(dialog) for _ in range(3))
    focus = tk.StringVar(dialog)
    sending = "发送这张图片的压缩副本" if compressed else "发送这张图片"
    status = tk.StringVar(dialog, value=translate(dialog, sending) + " · "
                         + translate(dialog, "API Key 只在本次软件运行期间保留。"))
    pending: Queue[str | Exception] = Queue()
    ttk.Label(dialog, text=filename, wraplength=540).grid(column=0, row=0, columnspan=2, sticky="w", padx=12, pady=9)
    fields = [("服务商", provider, "vision_provider"), ("API 基础地址", base_url, "vision_base_url"),
              ("模型 ID", model, "vision_model"), ("API Key", api_key, "vision_key"),
              ("审图重点（可选）", focus, "vision_focus")]
    labels = []
    for row, (label, value, name) in enumerate(fields, start=1):
        caption = ttk.Label(dialog, text=translate(dialog, label))
        caption.grid(row=row, column=0, sticky="w", padx=12, pady=4)
        labels.append((caption, label))
        if value is provider:
            selector = ttk.Combobox(dialog, name=name, values=tuple(PROVIDERS), textvariable=value, state="readonly")
            selector.grid(row=row, column=1, sticky="ew", padx=(0, 12))
        else:
            ttk.Entry(dialog, name=name, textvariable=value, show="*" if value is api_key else "").grid(
                row=row, column=1, sticky="ew", padx=(0, 12),
            )

    output = scrolledtext.ScrolledText(dialog, name="vision_output", wrap="word", width=66, height=11, state="disabled")
    output.grid(row=8, column=0, columnspan=2, sticky="nsew", padx=12, pady=(5, 12))
    ttk.Label(dialog, textvariable=status, wraplength=580).grid(row=7, column=0, columnspan=2, sticky="w", padx=12)

    def display_rules() -> None:
        title = translate(dialog, "查看固定审图规则")
        messagebox.showinfo(title, review_instructions(rules), parent=dialog)

    def choose_provider(_event=None) -> None:
        name = provider.get()
        previous = session.get(name)
        base_url.set(previous.base_url if previous else PROVIDERS[name].base_url)
        model.set(previous.model if previous else "")
        api_key.set(previous.api_key if previous else "")

    def load_current_api() -> None:
        if session:
            provider.set(next(reversed(session)))
            choose_provider()

    connection_before = None

    def request_api_settings():
        nonlocal connection_before
        connection_before = tuple(session.items())
        on_open_api()

    def activate():
        nonlocal connection_before
        if connection_before is not None and tuple(session.items()) != connection_before:
            load_current_api()
        connection_before = None
        if job_key is not None:
            job_changed()

    def interpret(result):
        if isinstance(result, Exception):
            response = str(result) if isinstance(result, ValueError) else ""
            return JobOutcome("failed", response)
        return JobOutcome("ready", value=result)

    def show_result(outcome):
        running = outcome.status == "working"
        send.configure(state="disabled" if running else "normal")
        if running:
            status.set(translate(dialog, "审图进行中，可从后台任务返回。"))
            response = ""
        elif outcome.status == "ready":
            status.set(translate(dialog, "模型建议 · 待人工确认"))
            response = outcome.value
        else:
            status.set(translate(dialog, "调用失败"))
            response = outcome.detail or translate(dialog, "调用异常，请检查模型与网络设置。")
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", response)
        output.configure(state="disabled")

    def job_changed():
        if entry := job_registry.get(job_key):
            show_result(entry.outcome)

    def receive() -> None:
        try:
            result = pending.get_nowait()
        except Empty:
            dialog.after(100, receive)
            return
        show_result(interpret(result))

    def confirm_and_send() -> None:
        if send.instate(["disabled"]):
            return
        settings = VisionSettings(provider.get(), base_url.get().strip(), model.get().strip(), api_key.get().strip())
        if not settings.model or not settings.api_key:
            messagebox.showerror(translate(dialog, "配置未完成"), translate(dialog, "请输入视觉模型的 ID 和服务商 API Key。"), parent=dialog)
            return
        try:
            endpoint = settings.endpoint()
        except ValueError as exc:
            messagebox.showerror(translate(dialog, "地址无效"), str(exc), parent=dialog)
            return
        try:
            question = checked_review_focus(focus.get())
        except ValueError as exc:
            messagebox.showerror(translate(dialog, "审图重点（可选）"), str(exc), parent=dialog)
            return
        detail = translate(dialog, "{action}到 {host}？\n模型：{model}").format(
            action=translate(dialog, sending), host=urlsplit(endpoint).netloc, model=settings.model,
        )
        if question:
            detail += "\n" + translate(dialog, "补充审图重点会随图片发送。")
        usage = translate(dialog, "调用使用该服务的额度。")
        allowed = messagebox.askyesno(translate(dialog, "发送所选图片"), f"{detail}\n{usage}", parent=dialog)
        if not allowed:
            return
        session.pop(settings.provider, None)
        session[settings.provider] = settings
        if job_key is not None:
            job_registry.start(
                job_key, "AI 辅助看图", f"{origin[0]}  /  {filename}", on_recover,
                lambda: review_image(settings, image, focus=question, rules=rules), interpret,
            )
            return
        send.configure(state="disabled")
        status.set(f"正在调用 {settings.provider}…")

        def worker() -> None:
            try:
                pending.put(review_image(settings, image, focus=question, rules=rules))
            except Exception as exc:
                pending.put(exc)

        Thread(target=worker, daemon=True).start()
        dialog.after(100, receive)

    selector.bind("<<ComboboxSelected>>", choose_provider)
    choose_provider()
    actions = ttk.Frame(dialog)
    actions.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=9)
    buttons = [("查看固定审图规则", "vision_rules", display_rules)]
    if on_open_api is not None:
        buttons.append(("API 接入", "vision_open_api", request_api_settings))
    for caption, name, command in buttons:
        button = ttk.Button(actions, name=name, text=translate(dialog, caption), command=command)
        button.pack(side="left", padx=(0, 6))
        labels.append((button, caption))
    send = ttk.Button(actions, name="vision_send", text=translate(dialog, "发送图片并分析"), command=confirm_and_send)
    send.pack(side="right")
    labels.append((send, "发送图片并分析"))
    help_button = guide_button(actions, "review_images")
    if help_button is not None:
        help_button.pack(side="right", padx=(0, 6))

    def refresh_language():
        for widget, caption in labels:
            widget.configure(text=translate(dialog, caption))
        if job_key is not None:
            job_changed()

    dialog.load_current_api = load_current_api
    dialog.activate = activate
    dialog.refresh_language = refresh_language
    if job_key is not None:
        job_registry.listen(dialog, job_changed)
        job_changed()
    if mount is None:
        parent.wait_window(dialog)
    return dialog
