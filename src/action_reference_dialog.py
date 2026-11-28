"""Project-local index of official video pages and the editor's own shot notes."""

import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from .action_sequence import ActionCard
from .action_reference_library import (
    ReferenceError, filter_references, make_reference, refs_from_records, refs_to_records,
)
from .action_reference_starters import STARTER_LINKS
from .production_project import ProductionProject


class ActionReferenceDialog:
    def __init__(self, sequence):
        self.sequence = sequence
        self.t = sequence.t
        self.items = refs_from_records(sequence.owner.project.action_references)
        card_ids = sequence.table.selection()
        self.card_id = card_ids[0] if len(card_ids) == 1 else None
        self.window = tk.Toplevel(sequence.window)
        self.window.title(self.t("动作参考库", "Action reference library"))
        self.window.transient(sequence.window)
        self.window.geometry("880x640")
        self.window.minsize(690, 545)
        self.query = tk.StringVar(self.window)
        self.platforms = {
            self.t("全部平台", "All platforms"): "",
            "YouTube": "YouTube",
            self.t("优酷", "Youku"): "Youku",
            self.t("腾讯视频", "Tencent Video"): "Tencent Video",
        }
        self.source_detail = tk.StringVar(self.window)
        self.status = tk.StringVar(self.window)
        self.build()
        self.refresh()

    def button(self, parent, zh, en, command):
        return ttk.Button(parent, text=self.t(zh, en), command=lambda: self.guard(command))

    def guard(self, command, parent=None):
        try:
            command()
        except (ValueError, OSError, RuntimeError, tk.TclError) as exc:
            message = exc.english if self.sequence.language and isinstance(exc, ReferenceError) else str(exc)
            messagebox.showerror(self.window.title(), message, parent=parent or self.window)

    def build(self):
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=2)
        body.rowconfigure(6, weight=1)

        self.starters = list(STARTER_LINKS)
        if self.starters:
            samples = ttk.Frame(body)
            samples.grid(row=0, column=0, sticky="ew", pady=(0, 12))
            samples.columnconfigure(1, weight=1)
            ttk.Label(samples, text=self.t("官方片源示例", "Official video examples")).grid(row=0, column=0, padx=(0, 8))
            self.starter = ttk.Combobox(samples, name="starter", state="readonly", width=28,
                                        values=[row[self.sequence.language] for row in self.starters])
            self.starter.current(0)
            self.starter.grid(row=0, column=1, sticky="ew")
            self.button(samples, "打开示例", "Open example", self.open_starter).grid(row=0, column=2, padx=5)
            self.button(samples, "使用示例", "Use example", self.use_starter).grid(row=0, column=3)

        tools = ttk.Frame(body)
        tools.grid(row=1, column=0, sticky="ew")
        ttk.Label(tools, text=self.t("项目参考", "Project references")).pack(side="left")
        self.button(tools, "新增参考", "Add reference", self.edit_form).pack(side="right")
        self.edit_btn = self.button(tools, "编辑参考", "Edit reference", lambda: self.edit_form(self.selected()))
        self.delete_btn = self.button(tools, "删除参考", "Delete reference", self.delete)
        for button in (self.edit_btn, self.delete_btn):
            button.pack(side="right", padx=(0, 4))

        filters = ttk.Frame(body)
        filters.grid(row=2, column=0, sticky="ew", pady=6)
        filters.columnconfigure(1, weight=1)
        ttk.Label(filters, text=self.t("搜索片名或笔记", "Search title or notes")).grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(filters, name="filter", textvariable=self.query).grid(row=0, column=1, sticky="ew")
        self.platform = ttk.Combobox(filters, name="platform", state="readonly", values=tuple(self.platforms), width=16)
        self.platform.current(0)
        self.platform.grid(row=0, column=2, padx=(6, 0))
        self.platform.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        listing = ttk.Frame(body)
        listing.grid(row=3, column=0, sticky="nsew")
        self.table = ttk.Treeview(listing, name="references", columns=("title", "platform", "clip"),
                                  show="headings", height=6, selectmode="browse")
        for key, zh, en, width in (("title", "片名／片段", "Title / clip", 320),
                                   ("platform", "平台", "Platform", 110),
                                   ("clip", "参考时段", "Time range", 145)):
            self.table.heading(key, text=self.t(zh, en))
            self.table.column(key, width=width, minwidth=70, stretch=(key == "title"))
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", lambda _event: self.update_detail())
        self.table.bind("<Double-1>", lambda event: self.guard(lambda: self.edit_form(self.selected()))
                        if self.table.identify_row(event.y) else None)
        self.query.trace_add("write", lambda *_: self.refresh())

        ttk.Label(body, textvariable=self.source_detail, anchor="w").grid(row=4, column=0, sticky="ew", pady=5)
        ttk.Label(body, text=self.t("我的镜头笔记", "My shot notes")).grid(row=5, column=0, sticky="w")
        detail = ttk.Frame(body)
        detail.grid(row=6, column=0, sticky="nsew", pady=(3, 5))
        self.notes = tk.Text(detail, name="preview_notes", wrap="word", height=3, state="disabled")
        note_scroll = ttk.Scrollbar(detail, orient="vertical", command=self.notes.yview)
        note_scroll.pack(side="right", fill="y")
        self.notes.configure(yscrollcommand=note_scroll.set)
        self.notes.pack(side="left", fill="both", expand=True)

        bottom = ttk.Frame(body)
        bottom.grid(row=7, column=0, sticky="ew")
        self.open_btn = self.button(bottom, "打开播放页", "Open video page", self.open_page)
        self.open_btn.pack(side="left")
        label = ("把笔记加入动作卡", "Add notes to card") if self.card_id else ("用笔记新建动作卡", "Create card from notes")
        self.apply_btn = self.button(bottom, *label, self.apply_notes)
        self.apply_btn.pack(side="left", padx=5)
        self.button(bottom, "关闭", "Close", self.window.destroy).pack(side="right")
        ttk.Label(body, textvariable=self.status, wraplength=645, justify="left").grid(
            row=8, column=0, sticky="w", pady=(5, 0))

    def selected(self):
        selected = self.table.selection()
        return next((item for item in self.items if item.id in selected), None)

    def refresh(self, prefer=None):
        current = self.selected()
        desired = prefer or (current.id if current else "")
        matches = filter_references(self.items, self.query.get(), self.platforms[self.platform.get()])
        self.table.delete(*self.table.get_children())
        labels = {value: label for label, value in self.platforms.items()}
        for ref in matches:
            clip = ref.start or ("00:00" if ref.end else "")
            if ref.end:
                clip += " – " + ref.end
            self.table.insert("", "end", iid=ref.id, values=(ref.title, labels[ref.platform], clip))
        if matches:
            active = desired if desired and self.table.exists(desired) else matches[0].id
            self.table.selection_set(active)
            self.table.see(active)
        self.update_detail()

    def update_detail(self):
        ref = self.selected()
        for button in (self.edit_btn, self.delete_btn, self.open_btn):
            button.state(["!disabled"] if ref else ["disabled"])
        self.apply_btn.state(["!disabled"] if ref and ref.notes else ["disabled"])
        if ref:
            self.source_detail.set(ref.url)
        elif self.items:
            self.source_detail.set(self.t("没有匹配的参考。请调整搜索词或平台。",
                                          "No matching references. Change the search or platform."))
        else:
            self.source_detail.set(self.t("项目里还没有参考。可新增官方播放链接，或选一个示例。",
                                          "Add an official video page or start from an example."))
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        if ref:
            self.notes.insert("1.0", ref.notes or self.t("还没有笔记。点「编辑参考」即可填写。",
                                                         "Use Edit reference to add your notes."))
        self.notes.configure(state="disabled")
        card = next((item for item in self.sequence.cards if item.id == self.card_id), None)
        self.status.set(self.t(f"目标动作卡「{card.title}」 · 笔记将追加到“动作与反应”。",
                               f"Target card: {card.title} · Notes will be appended to Movement & reaction.")
                        if card else self.t("用笔记新建一张原创动作卡，之后可在编排里编辑。",
                                            "Create an original action card from your notes, then edit it in the sequence."))

    def open_url(self, url):
        if not webbrowser.open(url):
            raise ValueError(self.t("无法启动浏览器。请检查默认浏览器设置。", "Could not open your default browser."))

    def open_page(self):
        ref = self.selected()
        if ref:
            self.open_url(ref.playback_url())

    def starter_row(self):
        return self.starters[self.starter.current()]

    def open_starter(self):
        zh, en, url = self.starter_row()
        self.open_url(make_reference(self.t(zh, en), url).playback_url())

    def use_starter(self):
        zh, en, url = self.starter_row()
        self.edit_form(title=self.t(zh, en), url=url)

    def persist(self, items):
        owner = self.sequence.owner
        saved = ProductionProject.open(owner.path)
        if refs_from_records(saved.action_references) != self.items:
            owner.project.action_references = saved.action_references
            raise ValueError(self.t("项目里的参考已在其他窗口修改。请关闭参考库再打开，查看最新内容。",
                                    "References changed in another window. Close and reopen the library to see the current entries."))
        saved.action_references = refs_to_records(items)
        saved.save(owner.path)
        owner.project.action_references = saved.action_references
        self.items = items

    def edit_form(self, existing=None, *, title="", url=""):
        panel = tk.Toplevel(self.window, name="reference_editor")
        panel.title(self.t("编辑参考", "Edit reference") if existing else self.t("新增参考", "Add reference"))
        panel.transient(self.window)
        panel.geometry("635x440")
        panel.minsize(525, 395)
        form = ttk.Frame(panel, padding=12)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(4, weight=1)
        entries = {}
        for row, (key, zh, en, initial) in enumerate((
            ("title", "片名／片段", "Title / clip", title),
            ("url", "官方播放或分享链接", "Official video or share URL", url),
        )):
            ttk.Label(form, text=self.t(zh, en)).grid(row=row, column=0, sticky="w", padx=(0, 6), pady=4)
            entry = ttk.Entry(form, name=key)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            entry.insert(0, getattr(existing, key) if existing else initial)
            entries[key] = entry

        ttk.Label(form, text=self.t("参考时段（可选）", "Time range (optional)")).grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=4)
        times = ttk.Frame(form)
        times.grid(row=2, column=1, sticky="w")
        for key, zh, en in (("start", "起", "From"), ("end", "止", "To")):
            ttk.Label(times, text=self.t(zh, en)).pack(side="left", padx=(0, 4))
            field = ttk.Entry(times, name=key, width=9)
            field.pack(side="left", padx=(0, 8))
            field.insert(0, getattr(existing, key) if existing else "")
            entries[key] = field
        ttk.Label(times, text="MM:SS / HH:MM:SS").pack(side="left")
        ttk.Label(form, text=self.t("我的镜头笔记", "My shot notes")).grid(row=3, column=0, sticky="w", pady=6)
        ttk.Label(form, text=self.t("记录景别变化、剪辑节奏，或你想在自己镜头里怎样呈现。",
                                    "Describe the framing, edit rhythm or how you would stage your shot."),
                  wraplength=352).grid(row=3, column=1, sticky="w")
        notes_area = ttk.Frame(form)
        notes_area.grid(row=4, column=0, columnspan=2, sticky="nsew")
        notes = tk.Text(notes_area, name="notes", wrap="word", height=4)
        scroll = ttk.Scrollbar(notes_area, orient="vertical", command=notes.yview)
        notes.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        notes.pack(side="left", fill="both", expand=True)
        if existing:
            notes.insert("1.0", existing.notes)

        def fields():
            return {**{key: field.get() for key, field in entries.items()}, "notes": notes.get("1.0", "end-1c")}

        original = fields()

        def cancel():
            if fields() != original and not messagebox.askyesno(
                panel.title(), self.t("放弃尚未保存的修改？", "Discard your unsaved edits?"), parent=panel,
            ):
                return
            panel.destroy()

        def save():
            ref = make_reference(**fields(), ref_id=existing.id if existing else None)
            if existing:
                items = [ref if item.id == ref.id else item for item in self.items]
            else:
                items = [*self.items, ref]
            self.persist(items)
            panel.destroy()
            if not filter_references([ref], self.query.get(), self.platforms[self.platform.get()]):
                self.platform.current(0)
                self.query.set("")
            self.refresh(ref.id)

        buttons = ttk.Frame(form)
        buttons.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(buttons, text=self.t("保存在当前单组项目中", "Saved in this project")).pack(side="left")
        ttk.Button(buttons, text=self.t("保存参考", "Save reference"),
                   command=lambda: self.guard(save, panel)).pack(side="right")
        ttk.Button(buttons, text=self.t("取消", "Cancel"), command=cancel).pack(side="right", padx=5)
        panel.protocol("WM_DELETE_WINDOW", cancel)
        panel.bind("<Escape>", lambda _event: cancel())
        entries["title"].focus_set()
        panel.grab_set()
        self.window.wait_window(panel)
        if self.window.winfo_exists():
            self.window.grab_set()

    def delete(self):
        ref = self.selected()
        if ref and messagebox.askyesno(self.window.title(), self.t(f"从项目中删除「{ref.title}」？",
                                                                  f"Delete “{ref.title}” from this project?"),
                                       parent=self.window):
            self.persist([item for item in self.items if item.id != ref.id])
            self.refresh()

    def apply_notes(self):
        ref = self.selected()
        if not ref or not ref.notes:
            return
        if self.card_id:
            self.sequence.append_reference_notes(self.card_id, ref.notes)
        else:
            card = ActionCard(title=self.t("原创动作", "Original action"), movement=ref.notes)
            self.sequence.add([card])
            self.sequence.show_card(card.id)
        self.window.destroy()
