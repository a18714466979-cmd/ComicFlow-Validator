"""Edit the three purpose-specific API configurations for the current session."""

import tkinter as tk
from tkinter import messagebox, ttk

from .image_api import IMAGE_PROVIDERS, TEXT, ImageSettings, build_image_request
from .production_dialog import field
from .ui_language import translate
from .vision import PROVIDERS, VisionSettings


TEXT_HELP = "选择支持文本输出和 JSON 的模型，用于分镜、状态交接和 SD2 提示词。剧本写作也可使用具备相应能力的文本模型。"
VISION_HELP = "选择支持图片输入的视觉模型，用于已选图片的 AI 审图。逐格人工复核和 ZIP 规则验收在本机运行。"
IMAGE_HELP = "选择能输出图片的图像模型，用于生成资产候选、参考图生图或局部编辑。可用模式取决于服务商和模型。"


def open_api_settings(parent, text_session, vision_session, image_session):
    window = tk.Toplevel(parent)
    window.title(translate(window, "ComicFlow API 设置"))
    window.geometry("760x470")
    window.minsize(710, 435)
    window.transient(parent)
    window.grab_set()
    content = ttk.Frame(window, padding=14)
    content.pack(fill="both", expand=True)
    ttk.Label(content, text=translate(content, "按用途配置模型。设置和密钥只在本次软件运行期间使用。"),
              wraplength=690).pack(anchor="w", pady=(0, 8))
    tabs = ttk.Notebook(content)
    tabs.pack(fill="both", expand=True)
    for caption, help_text, session, other, generation in (
        ("文本创作", TEXT_HELP, text_session, vision_session, False),
        ("AI 审图", VISION_HELP, vision_session, text_session, False),
        ("图像生成", IMAGE_HELP, image_session, None, True),
    ):
        page = ttk.Frame(tabs, padding=10)
        tabs.add(page, text=translate(page, caption))
        ApiSettingsTab(page, session, help_text, other=other, generation=generation)
    ttk.Button(content, text=translate(content, "关闭"), command=window.destroy).pack(anchor="e", pady=(8, 0))


class ApiSettingsTab:
    def __init__(self, page, session, help_text, *, other, generation):
        self.page = page
        self.session = session
        self.other = other
        self.generation = generation
        self.providers = IMAGE_PROVIDERS if generation else PROVIDERS
        ttk.Label(page, text=self.tr(help_text), wraplength=650).pack(anchor="w")
        form = ttk.Frame(page)
        form.pack(fill="x", pady=8)
        self.provider = tk.StringVar(page, next(reversed(session), next(iter(self.providers))))
        self.base, self.model, self.key, self.secret_id = (tk.StringVar(page) for _ in range(4))
        field(form, 0, "服务商", self.provider, tuple(self.providers)).bind("<<ComboboxSelected>>", self.select_provider)
        field(form, 1, "API 基础地址", self.base)
        self.model_field = field(form, 2, "模型 ID", self.model)
        self.key_label = ttk.Label(form)
        self.key_label.grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.key, show="*").grid(row=3, column=1, sticky="ew", pady=3)
        if generation:
            self.signing_id = field(form, 4, "腾讯云 SecretId", self.secret_id)
            self.capabilities = ttk.Label(page, wraplength=650)
            self.capabilities.pack(anchor="w")
            tip = self.tr("如果同一服务商的 Key 具备生图权限，可在这里手动填写。")
            ttk.Label(page, text=tip, wraplength=650).pack(anchor="w", pady=(4, 0))
        else:
            text = self.tr("文本与审图可以显式复用同一服务商、同一基础地址的 Key。请为每个用途选择合适的模型 ID。")
            ttk.Label(page, text=text, wraplength=650).pack(anchor="w")
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text=self.tr("保存本次设置"), command=self.save).pack(side="left")
        if other is not None:
            ttk.Button(actions, text=self.tr("带入另一用途的 Key"), command=self.copy_key).pack(side="left", padx=8)
        self.status = tk.StringVar(page)
        ttk.Label(page, textvariable=self.status, wraplength=650).pack(anchor="w")
        self.base.trace_add("write", self.clear_credentials)
        self.select_provider()

    def clear_credentials(self, *_args):
        self.key.set("")
        self.secret_id.set("")
        self.status.set("")

    def tr(self, text):
        return translate(self.page, text)

    def select_provider(self, _event=None):
        provider = self.provider.get()
        preset = self.providers[provider]
        previous = self.session.get(provider)
        if self.generation:
            signed = preset.asynchronous
            self.base.set(previous.base if previous else preset.base)
            self.model.set(previous.model if previous else preset.model)
            self.key.set(previous.key if previous else "")
            self.secret_id.set(previous.secret_id if previous else "")
            self.model_field.configure(state="readonly" if signed else "normal")
            self.signing_id.configure(state="normal" if signed else "disabled")
            modes = " / ".join(self.tr(mode) for mode in preset.modes)
            note = self.tr("预设模式 {modes} · 最多 {count} 张参考图").format(modes=modes, count=preset.references)
            if signed:
                note += " · " + self.tr("混元生图使用 SecretId 和 SecretKey，单独配置。")
            self.capabilities.configure(text=note)
        else:
            signed = False
            self.base.set(previous.base_url if previous else preset.base_url)
            self.model.set(previous.model if previous else "")
            self.key.set(previous.api_key if previous else "")
        self.key_label.configure(text=self.tr("腾讯云 SecretKey") if signed else "API Key")
        self.status.set("")

    def copy_key(self):
        source = self.other.get(self.provider.get())
        base = self.base.get().strip().rstrip("/")
        if source and source.api_key and base and source.base_url.rstrip("/") == base:
            self.key.set(source.api_key)
            self.status.set(self.tr("已带入 Key。请检查模型 ID，然后保存本次设置。"))
        else:
            self.status.set(self.tr("另一用途须先保存同服务商、同基础地址的 Key。"))

    def settings(self):
        name, base, model, key = (var.get().strip() for var in (self.provider, self.base, self.model, self.key))
        base = base.rstrip("/")
        if not model:
            raise ValueError("请填写模型 ID。")
        if key and not all(33 <= ord(char) <= 126 for char in key):
            raise ValueError("请输入有效的 API Key 或 SecretKey。")
        if self.generation:
            secret_id = self.secret_id.get().strip()
            if self.providers[name].asynchronous and bool(secret_id) != bool(key):
                raise ValueError("混元生图请同时填写 SecretId 和 SecretKey。")
            settings = ImageSettings(name, base, model, key, secret_id)
            build_image_request(settings, TEXT, "配置预检", preview=not key)
        else:
            settings = VisionSettings(name, base, model, key)
            settings.endpoint()
        return settings

    def save(self):
        try:
            settings = self.settings()
        except ValueError as exc:
            messagebox.showerror(self.tr("API 设置"), self.tr(str(exc)), parent=self.page.winfo_toplevel())
            return
        self.session.pop(settings.provider, None)
        self.session[settings.provider] = settings
        caption = ("已保存本次设置。调用资格需以服务商返回为准。" if self.key.get().strip()
                   else "已保存接口和模型。提交任务前请填写密钥。")
        self.status.set(self.tr(caption))
