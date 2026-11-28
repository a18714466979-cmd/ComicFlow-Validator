"""Show the selected image and destination before an optional AI request."""

import tkinter as tk
from queue import Empty, Queue
from threading import Thread
from tkinter import messagebox, scrolledtext, ttk
from urllib.parse import urlsplit

from .production_rules import ENGLISH
from .ui_language import translate
from .vision import PROVIDERS, VisionSettings, checked_review_focus, prepare_review_image, review_image, review_instructions


def open_vision_dialog(
    parent: tk.Tk, filename: str, image: bytes, session: dict[str, VisionSettings], *, rules: str = ENGLISH,
) -> None:
    try:
        image, compressed = prepare_review_image(image)
    except (ValueError, OSError) as exc:
        messagebox.showerror(translate(parent, "图片无法分析"), str(exc), parent=parent)
        return

    dialog = tk.Toplevel(parent)
    dialog.title(translate(dialog, "AI 辅助看图"))
    dialog.transient(parent)
    dialog.grab_set()
    dialog.minsize(630, 440)
    dialog.columnconfigure(1, weight=1)
    dialog.rowconfigure(8, weight=1)

    provider = tk.StringVar(value=next(reversed(session), next(iter(PROVIDERS))))
    base_url, model, api_key = tk.StringVar(), tk.StringVar(), tk.StringVar()
    focus = tk.StringVar()
    sending = "发送这张图片的压缩副本" if compressed else "发送这张图片"
    status = tk.StringVar(value=translate(dialog, sending) + " · "
                         + translate(dialog, "API Key 只在本次软件运行期间保留。"))
    pending: Queue[str | Exception] = Queue()
    ttk.Label(dialog, text=filename, wraplength=540).grid(column=0, row=0, columnspan=2, sticky="w", padx=12, pady=9)
    fields = [("服务商", provider), ("API 基础地址", base_url), ("模型 ID", model), ("API Key", api_key),
              ("审图重点（可选）", focus)]
    for row, (label, value) in enumerate(fields, start=1):
        ttk.Label(dialog, text=translate(dialog, label)).grid(row=row, column=0, sticky="w", padx=12, pady=4)
        if value is provider:
            selector = ttk.Combobox(dialog, values=tuple(PROVIDERS), textvariable=value, state="readonly")
            selector.grid(row=row, column=1, sticky="ew", padx=(0, 12))
        else:
            ttk.Entry(dialog, textvariable=value, show="*" if value is api_key else "").grid(
                row=row, column=1, sticky="ew", padx=(0, 12),
            )

    output = scrolledtext.ScrolledText(dialog, wrap="word", width=66, height=11, state="disabled")
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

    def receive() -> None:
        try:
            result = pending.get_nowait()
        except Empty:
            dialog.after(100, receive)
            return
        if isinstance(result, Exception):
            status.set("调用失败")
            response = str(result) if isinstance(result, ValueError) else "调用异常，请检查模型与网络设置。"
        else:
            status.set("模型建议 · 待人工确认")
            response = result
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", response)
        output.configure(state="disabled")
        send.configure(state="normal")

    def confirm_and_send() -> None:
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
    ttk.Button(dialog, text=translate(dialog, "查看固定审图规则"), command=display_rules).grid(
        row=6, column=0, sticky="w", padx=12, pady=9,
    )
    send = ttk.Button(dialog, text=translate(dialog, "发送图片并分析"), command=confirm_and_send)
    send.grid(row=6, column=1, sticky="e", padx=12, pady=9)
    parent.wait_window(dialog)
