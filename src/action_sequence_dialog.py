"""Local editor for action cards and the review boards built from them."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from PIL import Image, ImageTk

from .action_card_catalog import PRESETS
from .action_sequence import (
    ActionCard, action_continuity, cards_from_records, cards_to_records, load_action_cards,
    plan_action_handoff, rebind_action_cards, save_action_cards,
)
from .director_action_import import import_director_cards
from .reference_tools_dialog import DIRECTOR_DESK, import_reference, read_reference
from .ui_language import translate


class ActionSequenceDialog:
    def __init__(self, owner):
        self.owner = owner
        self.cards = cards_from_records(owner.project.action_cards)
        self.window = tk.Toplevel(owner.window)
        self.window.title(translate(self.window, "人物动作编排"))
        self.window.geometry("1080x745")
        self.window.minsize(830, 600)
        self.window.transient(owner.window)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.language = int(getattr(self.window._root(), "ui_language", "zh") == "en")
        self.images = list(owner.project.images)
        self.saved_cards, self.saved_images = list(self.cards), list(self.images)
        self.drag = None
        self.page = 0
        self.categories = list(PRESETS.values())
        self.category = tk.StringVar(self.window)
        self.preset = tk.StringVar(self.window)
        self.status = tk.StringVar(self.window)
        self.grid_size = tk.StringVar(self.window, "12")
        self.page_label = tk.StringVar(self.window)

        top = ttk.Frame(self.window, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        self.button(top, "保存动作编排", "Save sequence", self.save).pack(side="left", padx=3)
        self.button(top, "导入动作卡", "Import cards", self.import_cards).pack(side="left", padx=3)
        self.button(top, "导出动作卡", "Export cards", self.export_cards).pack(side="left", padx=3)
        self.button(top, "导入 3D 导演台工程", "Import 3D Director project",
                    lambda: self.import_cards(director=True)).pack(side="left", padx=3)
        self.button(top, "打开 3D 导演台", "Open 3D Director Desk",
                    lambda: webbrowser.open(DIRECTOR_DESK)).pack(side="left", padx=3)
        resources = ttk.Frame(self.window, padding=(12, 0, 12, 6))
        resources.pack(fill="x")
        self.button(resources, "动作参考库", "Action reference library", self.open_reference_library).pack(side="right")
        ttk.Label(resources, text=self.t(
            "选卡或新建 → 核对格间动作 → 带入分镜。预演可用文字或参考图。",
            "Add cards → review adjacent beats → send to shots. Preview with text or reference images.",
        ), wraplength=565, justify="left").pack(side="left")

        self.tabs = ttk.Notebook(self.window)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        editor = ttk.Frame(self.tabs, padding=8)
        board = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(editor, text=self.t("动作卡", "Cards"))
        self.tabs.add(board, text=self.t("预演格", "Preview panels"))
        self.build_editor(editor)
        self.build_board(board)
        self.tabs.bind("<<NotebookTabChanged>>", self.tab_changed)
        ttk.Label(self.window, textvariable=self.status, wraplength=790, padding=(12, 2, 12, 8)).pack(anchor="w")
        self.refresh()

    def t(self, zh, en):
        return en if self.language else zh

    def button(self, parent, zh, en, command):
        return ttk.Button(parent, text=self.t(zh, en), command=lambda: self.guard(command))

    def guard(self, command, parent=None):
        try:
            command()
        except (OSError, ValueError, tk.TclError, RuntimeError) as error:
            messagebox.showerror(translate(self.window, "人物动作编排"), str(error), parent=parent or self.window)

    def build_editor(self, parent):
        catalog = ttk.Frame(parent)
        catalog.pack(fill="x", pady=(0, 6))
        names = [name[self.language] for name in PRESETS]
        ttk.Label(catalog, text=self.t(f"预设库 · {sum(map(len, self.categories))} 张",
                                      f"Presets · {sum(map(len, self.categories))}")).pack(side="left", padx=(0, 6))
        self.category_box = ttk.Combobox(catalog, state="readonly", values=names, textvariable=self.category, width=22)
        self.category_box.pack(side="left", padx=4)
        self.category_box.bind("<<ComboboxSelected>>", lambda _event: self.update_presets())
        self.preset_box = ttk.Combobox(catalog, state="readonly", textvariable=self.preset, width=31)
        self.preset_box.pack(side="left", padx=4)
        self.button(catalog, "加入选中预设", "Add preset", self.add_preset).pack(side="left", padx=4)
        self.category_box.current(0)
        self.update_presets()

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=4)
        for zh, en, command in (
            ("新建", "New", lambda: self.edit(ActionCard())),
            ("编辑", "Edit", self.edit_selected),
            ("上移", "Move up", lambda: self.move(-1)),
            ("下移", "Move down", lambda: self.move(1)),
            ("删除", "Remove", self.remove_selected),
            ("前后格对照", "Compare adjacent panels", self.compare),
            ("带入正式分镜", "Send to formal shots", self.handoff),
        ):
            self.button(actions, zh, en, command).pack(side="left", padx=(0, 4))

        listing = ttk.Frame(parent)
        listing.pack(fill="both", expand=True, pady=(4, 0))
        columns = (
            ("number", "序号", "#", 52), ("title", "动作卡", "Card", 215),
            ("actor", "人物", "Actor", 120), ("prop", "道具", "Prop", 125),
            ("reference", "参考图", "Reference", 88), ("shot", "目标镜号", "Target shot", 95),
        )
        self.table = ttk.Treeview(listing, columns=[row[0] for row in columns], show="headings", selectmode="extended")
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        for key, zh, en, width in columns:
            self.table.heading(key, text=self.t(zh, en))
            self.table.column(key, width=width, minwidth=50, stretch=key in {"title", "actor", "prop"})
        self.table.bind("<Double-1>", lambda _event: self.guard(self.edit_selected))
        self.table.bind("<ButtonPress-1>", self.drag_start, add="+")
        self.table.bind("<ButtonRelease-1>", lambda event: self.guard(lambda: self.drag_end(event)), add="+")
        self.table.bind("<<TreeviewSelect>>", lambda _event: self.update_detail())
        self.detail = tk.StringVar(self.window)
        ttk.Label(parent, textvariable=self.detail, justify="left", wraplength=780).pack(anchor="w", pady=(6, 0))

    def build_board(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x")
        for size in ("12", "15"):
            ttk.Radiobutton(header, text=self.t(f"{size} 格", f"{size} panels"), value=size,
                            variable=self.grid_size, command=self.reset_page).pack(side="left", padx=(0, 10))
        self.button(header, "上一页", "Previous page", lambda: self.step_page(-1)).pack(side="left", padx=3)
        self.button(header, "下一页", "Next page", lambda: self.step_page(1)).pack(side="left", padx=3)
        ttk.Label(header, textvariable=self.page_label).pack(side="left", padx=8)
        self.button(header, "前后格对照", "Compare adjacent panels", self.compare).pack(side="right", padx=3)
        self.board = ttk.Frame(parent)
        self.board.pack(fill="both", expand=True, pady=(6, 0))

    def refresh(self, selection=()):
        self.table.delete(*self.table.get_children())
        shots = {shot.id: f"{self.owner.project.group}-{index:02d}"
                 for index, shot in enumerate(self.owner.project.shots, 1)}
        images = {image.id for image in self.images}
        for index, card in enumerate(self.cards, 1):
            self.table.insert("", "end", iid=card.id, values=(
                index, card.title or self.t("未命名", "Untitled"), card.actor, card.prop,
                self.t("已挂图", "Linked") if card.reference in images else "", shots.get(card.shot_id, ""),
            ))
        if selection:
            self.table.selection_set(*selection)
            self.table.see(selection[0])
        self.update_detail()
        if self.tabs.index(self.tabs.select()) == 1:
            self.render_board()

    def update_detail(self):
        selected = self.table.selection()
        card = next((item for item in self.cards if item.id in selected), None)
        if card is None:
            self.detail.set(self.t("拖动或用上移／下移排序。按住 Ctrl 可选多张卡带入分镜。",
                                   "Drag or use Move up/down to reorder. Hold Ctrl to select multiple cards."))
            return
        parts = (card.start, card.movement, card.end) if card.movement else (card.route_notes,)
        self.detail.set("  →  ".join(value[:150] for value in parts if value))

    def selection(self, *, single=False):
        ids = self.table.selection()
        if not ids or (single and len(ids) != 1):
            raise ValueError(self.t("请选择一张动作卡。" if single else "请选择要处理的动作卡。",
                                    "Select one action card." if single else "Select action cards first."))
        return ids

    def update_presets(self):
        cards = self.categories[self.category_box.current()]
        self.preset_box.configure(values=[card[0][self.language] for card in cards])
        self.preset_box.current(0)

    def add_preset(self):
        title, movement, prop = self.categories[self.category_box.current()][self.preset_box.current()]
        cards = [ActionCard(title=title[self.language], movement=movement[self.language], prop=prop[self.language])]
        self.add(cards)

    def open_reference_library(self):
        from .action_reference_dialog import ActionReferenceDialog

        self.wait(ActionReferenceDialog(self).window)

    def append_reference_notes(self, identity, notes):
        card = next(item for item in self.cards if item.id == identity)
        movement = "\n".join(part for part in (card.movement, notes) if part)
        if len(movement) > 1500:
            raise ValueError(self.t("动作与反应最多 1500 字。请缩短笔记或已有动作后再加入。",
                                    "Movement & reaction allows 1,500 characters. Shorten the notes or existing movement."))
        self.cards = [replace(item, movement=movement) if item.id == identity else item for item in self.cards]
        self.refresh((identity,))
        self.status.set(self.t(f"笔记已加入「{card.title}」。可打开预演格查看，或保存动作编排。",
                               f"Notes added to “{card.title}”. Open Preview panels or save the sequence."))

    def add(self, incoming):
        ids = {card.id for card in self.cards}
        cards = [replace(card, id=ActionCard().id) if card.id in ids else card for card in incoming]
        cards_to_records(self.cards + cards)
        self.cards.extend(cards)
        self.refresh(tuple(card.id for card in cards))
        self.status.set(self.t(f"已加入 {len(cards)} 张动作卡。", f"Added {len(cards)} action card(s)."))

    def edit_selected(self):
        (identity,) = self.selection(single=True)
        self.edit(next(card for card in self.cards if card.id == identity))

    def move(self, change):
        (identity,) = self.selection(single=True)
        source = next(index for index, card in enumerate(self.cards) if card.id == identity)
        target = min(len(self.cards) - 1, max(0, source + change))
        self.reorder(source, target)

    def reorder(self, source, target):
        if source != target:
            card = self.cards.pop(source)
            self.cards.insert(target, card)
            self.refresh((card.id,))

    def drag_start(self, event):
        identity = self.table.identify_row(event.y)
        self.drag = (identity, event.y) if identity and not event.state & 0x0005 else None

    def drag_end(self, event):
        drag, self.drag = self.drag, None
        target = self.table.identify_row(event.y)
        if drag and target and abs(drag[1] - event.y) >= 10 and self.table.exists(drag[0]):
            order = self.table.get_children()
            self.reorder(order.index(drag[0]), order.index(target))

    def remove_selected(self):
        selected = self.selection()
        if messagebox.askyesno(self.t("删除动作卡", "Remove action cards"),
                               self.t(f"移除所选 {len(selected)} 张动作卡？",
                                      f"Remove {len(selected)} selected card(s)?"), parent=self.window):
            self.cards = [card for card in self.cards if card.id not in selected]
            self.refresh()

    def edit(self, card):
        panel = tk.Toplevel(self.window)
        panel.title(self.t("编辑动作卡", "Edit action card"))
        panel.geometry("720x650")
        panel.transient(self.window)
        form = ttk.Frame(panel, padding=12)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)
        labels = (
            ("title", "卡片名称", "Title"), ("actor", "人物", "Actor"), ("scene", "空间／场景", "Scene"),
            ("prop", "手持道具", "Prop"), ("start", "起始位置／姿势", "Starting position / pose"),
            ("movement", "动作与反应", "Movement & reaction"), ("end", "结束状态", "End state"),
            ("hand_start", "起始持物手", "Starting hand"), ("hand_end", "结束持物手", "Ending hand"),
        )
        values = {}
        for row, (key, zh, en) in enumerate(labels):
            ttk.Label(form, text=self.t(zh, en)).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=3)
            if key in {"start", "movement", "end"}:
                control = tk.Text(form, height=2, width=45, wrap="word")
                control.insert("1.0", getattr(card, key))
            elif key.startswith("hand_"):
                hands = self.t(("", "左手", "右手", "双手", "无"), ("", "Left", "Right", "Both", "None"))
                control = ttk.Combobox(form, values=hands)
                control.set(getattr(card, key))
            else:
                control = ttk.Entry(form)
                control.insert(0, getattr(card, key))
            control.grid(row=row, column=1, sticky="ew", pady=3)
            values[key] = control

        shots = {"": ""}
        for index, shot in enumerate(self.owner.project.shots, 1):
            label = f"{self.owner.project.group}-{index:02d}  {shot.anchor}"
            shots[label] = shot.id
        ttk.Label(form, text=self.t("绑定已有镜头", "Link existing shot")).grid(row=9, column=0, sticky="w")
        target = ttk.Combobox(form, state="readonly", values=tuple(shots))
        target.set(next((name for name, value in shots.items() if value == card.shot_id), ""))
        target.grid(row=9, column=1, sticky="ew", pady=3)

        selected_ref = next((image for image in self.images if image.id == card.reference), None)
        local_selection = None
        label = tk.StringVar(panel, selected_ref.filename if selected_ref else self.t("待挂图", "No reference"))
        ref = ttk.Frame(form)
        ref.grid(row=10, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Label(ref, textvariable=label).pack(side="left", padx=(0, 7))
        preview = ttk.Label(form)
        preview.grid(row=11, column=1, sticky="w")
        if card.route_notes:
            route = ttk.Frame(form)
            route.grid(row=12, column=0, columnspan=2, sticky="ew", pady=3)
            ttk.Label(route, text=self.t("导演台轨迹参考 · 请填入成片动作",
                                        "Director route reference · Write a shot action above")).pack(anchor="w")
            notes = tk.Text(route, height=3, wrap="word")
            notes.insert("1.0", card.route_notes)
            notes.configure(state="disabled")
            notes.pack(fill="x")

        def choose():
            nonlocal local_selection
            selected = filedialog.askopenfilename(
                parent=panel, filetypes=((self.t("参考图", "Reference images"), "*.png *.jpg *.jpeg *.webp"),),
            )
            if selected:
                path = Path(selected)
                data, _, image = read_reference(path)
                image.thumbnail((190, 90))
                preview.photo = ImageTk.PhotoImage(image, master=panel)
                preview.configure(image=preview.photo)
                local_selection = path, sha256(data).hexdigest()
                label.set(path.name[:42])

        def unlink():
            nonlocal local_selection, selected_ref
            local_selection = selected_ref = None
            preview.configure(image="")
            preview.photo = None
            label.set(self.t("待挂图", "No reference"))

        ttk.Button(ref, text=self.t("选择本地参考图", "Choose local reference"),
                   command=lambda: self.guard(choose, panel)).pack(side="left", padx=4)
        self.button(ref, "移除参考", "Unlink reference", unlink).pack(side="left", padx=4)

        def commit():
            fields = {key: control.get("1.0", "end-1c") if isinstance(control, tk.Text) else control.get()
                      for key, control in values.items()}
            if not fields["title"].strip() or not fields["movement"].strip():
                raise ValueError(self.t("请填写卡片名称和动作内容。", "Enter a title and movement."))
            updated = replace(card, **fields, shot_id=shots[target.get()],
                              reference=selected_ref.id if selected_ref else "")
            cards = ([updated if item.id == card.id else item for item in self.cards]
                     if self.table.exists(card.id) else self.cards + [updated])
            cards = cards_from_records(cards_to_records(cards))
            if local_selection:
                local_path, digest = local_selection
                project = replace(self.owner.project, images=list(self.images))
                image = import_reference(project, self.owner.path, local_path, "pose", seen_digest=digest)
                cards = [replace(item, reference=image.id) if item.id == card.id else item for item in cards]
                self.images = project.images
            self.cards = cards
            panel.destroy()
            self.refresh((card.id,))

        ttk.Button(form, text=self.t("确认", "Confirm"), command=lambda: self.guard(commit, panel)).grid(
            row=13, column=1, sticky="e", pady=(8, 0))
        self.wait(panel)

    def wait(self, panel):
        panel.grab_set()
        self.window.wait_window(panel)
        if self.window.winfo_exists():
            self.window.grab_set()

    def tab_changed(self, _event):
        if self.tabs.index(self.tabs.select()) == 1:
            self.render_board()

    def reset_page(self):
        self.page = 0
        self.render_board()

    def step_page(self, delta):
        self.page += delta
        self.render_board()

    def render_board(self):
        for widget in self.board.winfo_children():
            widget.destroy()
        size = int(self.grid_size.get())
        columns = size // 3
        pages = max(1, (len(self.cards) + size - 1) // size)
        self.page = min(max(0, self.page), pages - 1)
        self.page_label.set(f"{self.page + 1} / {pages}")
        for column in range(5):
            self.board.columnconfigure(column, weight=int(column < columns), uniform="panel" if column < columns else "")
        for row in range(3):
            self.board.rowconfigure(row, weight=1, uniform="panel")
        start = self.page * size
        visible = self.cards[start:start + size]
        pending = []
        for offset in range(size):
            frame = tk.Frame(self.board, background="#f6f8fa", highlightthickness=1, highlightbackground="#c8d2dd")
            frame.grid(row=offset // columns, column=offset % columns, padx=3, pady=3, sticky="nsew")
            if offset < len(visible):
                card = visible[offset]
                label = self.card_panel(frame, card, start + offset + 1, compact=True)
                pending.append((label, card.reference))
                frame.bind("<Button-1>", lambda _event, identity=card.id: self.show_card(identity))
                for child in frame.winfo_children():
                    child.bind("<Button-1>", lambda _event, identity=card.id: self.show_card(identity))
            else:
                tk.Label(frame, text=f"{start + offset + 1:02d}", bg="#f6f8fa", fg="#546679").pack(anchor="nw", padx=5)
        self.thumbnails(pending, (142, 66))

    def show_card(self, identity):
        self.table.selection_set(identity)
        self.table.see(identity)
        self.tabs.select(0)

    def card_panel(self, frame, card, number, *, compact=False):
        title = f"{number:02d}  {card.title[:34]}"
        ttk.Label(frame, text=title, wraplength=145 if compact else 320).pack(anchor="w", padx=5, pady=3)
        reference = ttk.Label(frame, text=self.t("待挂图", "No reference"))
        reference.pack(anchor="center", pady=2)
        action = card.movement or card.route_notes
        text = action.replace("\n", " ")[:64] if compact else "\n\n".join(
            f"{caption}  {value}" for caption, value in (
                (self.t("人物", "Actor"), card.actor), (self.t("道具", "Prop"), card.prop),
                (self.t("起点", "Start"), card.start), (self.t("动作", "Movement"), card.movement),
                (self.t("终点", "End"), card.end), (self.t("起始持物手", "Starting hand"), card.hand_start),
                (self.t("结束持物手", "Ending hand"), card.hand_end), (self.t("轨迹参考", "Route"), card.route_notes),
            ) if value
        )
        ttk.Label(frame, text=text, justify="left", wraplength=145 if compact else 320).pack(anchor="w", padx=5, pady=3)
        return reference

    def thumbnails(self, pending, size):
        by_id = {image.id: image for image in self.images}
        work = [(label, by_id[identity]) for label, identity in pending if identity in by_id]
        if not work:
            return
        results = Queue()
        project, path = self.owner.project, self.owner.path
        root = self.window._root()

        def read():
            for order, (_, item) in enumerate(work):
                try:
                    with Image.open(project.checked_image(path, item)) as source:
                        source.thumbnail(size)
                        results.put((order, source.copy()))
                except (OSError, ValueError, RuntimeError, Image.DecompressionBombError):
                    results.put((order, None))
            results.put(None)

        def receive():
            while self.window.winfo_exists():
                try:
                    result = results.get_nowait()
                except Empty:
                    if any(label.winfo_exists() for label, _ in work):
                        root.after(75, receive)
                    return
                if result is None:
                    return
                order, preview = result
                label = work[order][0]
                if not label.winfo_exists():
                    continue
                if preview is None:
                    label.configure(text=self.t("参考图不可用", "Reference unavailable"))
                else:
                    label.preview_image = ImageTk.PhotoImage(preview, master=self.window)
                    label.configure(image=label.preview_image, text="")

        Thread(target=read, daemon=True).start()
        root.after(75, receive)

    def compare(self):
        if len(self.cards) < 2:
            raise ValueError(self.t("至少需要两张动作卡。", "Add at least two action cards."))
        selected = set(self.table.selection())
        index = next((index for index, card in enumerate(self.cards) if card.id in selected),
                     self.page * int(self.grid_size.get()))
        panel = tk.Toplevel(self.window)
        panel.title(self.t("前后格对照", "Compare adjacent panels"))
        panel.geometry("760x610")
        panel.transient(self.window)
        header = ttk.Frame(panel, padding=8)
        header.pack(fill="x")
        row = ttk.Frame(panel, padding=8)
        row.pack(fill="both", expand=True)
        findings = ttk.Label(panel, justify="left", wraplength=700, padding=8)
        findings.pack(anchor="w")
        pair = max(0, min(index, len(self.cards) - 2))

        def render(step=0):
            nonlocal pair
            pair = max(0, min(pair + step, len(self.cards) - 2))
            for child in row.winfo_children():
                child.destroy()
            a, b = self.cards[pair:pair + 2]
            pending = []
            for offset, card in enumerate((a, b)):
                frame = ttk.Frame(row, padding=5, relief="groove")
                frame.pack(side="left", fill="both", expand=True, padx=4)
                pending.append((self.card_panel(frame, card, pair + offset + 1), card.reference))
            self.thumbnails(pending, (325, 150))
            notes = [issue.english if self.language else issue.message for issue in action_continuity([a, b])]
            findings.configure(text="\n".join(notes) or self.t(
                "已填写的持物信息未触发提醒。请对照人物站位、朝向、动作起止和道具位置。",
                "The recorded holding states triggered no alerts. Review position, facing, motion and prop placement.",
            ))

        self.button(header, "上一对", "Previous pair", lambda: render(-1)).pack(side="left", padx=4)
        self.button(header, "下一对", "Next pair", lambda: render(1)).pack(side="left", padx=4)
        render()
        self.wait(panel)

    def import_cards(self, *, director=False):
        location = filedialog.askopenfilename(parent=self.window, filetypes=(("JSON", "*.json"),))
        if not location:
            return
        path = Path(location)
        if director:
            incoming = [ActionCard(title=entry["title"], actor=entry["actor"], prop=entry["prop"],
                                   route_notes="\n".join(entry[key] for key in ("start", "movement", "end")))
                        for entry in import_director_cards(path, language=self.t("zh", "en"))]
        else:
            imported = load_action_cards(path)
            incoming = rebind_action_cards(imported, replace(self.owner.project, images=self.images))
        if incoming:
            self.add(incoming)
            if director:
                self.status.set(self.t(f"已导入 {len(incoming)} 条人物或道具轨迹。",
                                       f"Imported {len(incoming)} actor or prop tracks."))
            elif imported != incoming:
                self.status.set(self.t("已导入卡片。当前项目里找不到的镜头或参考图链接需要重新绑定。",
                                       "Cards imported. Relink shot or reference IDs missing from this project."))
        else:
            self.status.set(self.t("文件中没有可编排的动作。", "The file contains no usable action cards."))

    def export_cards(self):
        if not self.cards:
            raise ValueError(self.t("先加入至少一张动作卡。", "Add at least one card first."))
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json", filetypes=(("JSON", "*.json"),))
        if path:
            save_action_cards(Path(path), self.cards)
            self.status.set(self.t("已导出动作卡 JSON，参考图片保存在原项目中。",
                                   "Action cards exported to JSON. Reference images stay in the source project."))

    def save(self, shots=None, cards=None):
        self.owner.update_group()
        cards = self.cards if cards is None else cards
        fields = {"action_cards": cards_to_records(cards), "images": list(self.images)}
        if shots is not None:
            fields["shots"] = shots
        candidate = replace(self.owner.project, **fields)
        candidate.save(self.owner.path)
        self.owner.project = candidate
        self.cards = list(cards)
        self.saved_cards, self.saved_images = list(cards), list(self.images)
        self.owner.refresh()
        self.refresh(tuple(self.table.selection()))
        self.status.set(self.t("已保存到当前项目。", "Saved to the current project."))

    def handoff(self):
        selected = self.selection()
        picks = [card for card in self.cards if card.id in selected]
        if any(card.route_notes and not card.movement for card in picks):
            raise ValueError(self.t("请先编辑导入的轨迹卡，填写实际成片动作，再带入分镜。",
                                    "Edit imported route cards and write their shot action before sending them."))
        needs_source = any(not card.shot_id for card in picks)
        if needs_source and not self.owner.project.sources:
            raise ValueError(self.t(
                "新增镜头需要批准剧本。请先保存动作卡，再使用镜头清单的「导入批准剧本」。",
                "New shots require an approved script. Save the cards, then import an approved script in the shot list.",
            ))
        panel = tk.Toplevel(self.window)
        panel.title(self.t("带入正式分镜", "Send to formal shots"))
        panel.transient(self.window)
        form = ttk.Frame(panel, padding=12)
        form.pack(fill="both", expand=True)
        ttk.Label(form, wraplength=475, justify="left", text=self.t(
            "已绑定镜头的动作文字会替换为本次选中卡片。未绑定卡片按顺序加入镜头清单末尾。请继续核对机位、对白和画面。",
            "Selected cards replace action text on linked shots. Unlinked cards append in sequence. Review camera, dialogue and images afterward.",
        )).pack(anchor="w", pady=(0, 8))
        source, anchor = None, tk.StringVar(panel)
        if needs_source:
            ttk.Label(form, text=self.t("批准剧本", "Approved script")).pack(anchor="w")
            source = ttk.Combobox(form, state="readonly", width=52,
                                  values=[f"{item.name} · {item.version}" for item in self.owner.project.sources])
            source.current(0)
            source.pack(fill="x", pady=(0, 8))
            ttk.Label(form, text=self.t("新增镜头对应的实际源段", "Actual source passage for new shots")).pack(anchor="w")
            ttk.Entry(form, width=52, textvariable=anchor).pack(fill="x")

        def confirm():
            source_id = self.owner.project.sources[source.current()].id if source is not None else ""
            shots, cards = plan_action_handoff(self.owner.project, self.cards, selected,
                                              source_id=source_id, anchor=anchor.get())
            self.save(shots, cards)
            panel.destroy()
            self.status.set(self.t(f"已将 {len(selected)} 张动作卡带入镜头清单。",
                                   f"Sent {len(selected)} card(s) to the shot list."))

        ttk.Button(form, text=self.t("确认带入", "Confirm handoff"), command=lambda: self.guard(confirm, panel)).pack(
            anchor="e", pady=(10, 0))
        self.wait(panel)

    def close(self):
        if self.cards != self.saved_cards or self.images != self.saved_images:
            answer = messagebox.askyesnocancel(self.t("尚未保存", "Unsaved changes"),
                                                self.t("离开前保存动作编排？", "Save the sequence before closing?"),
                                                parent=self.window)
            if answer is None:
                return
            if answer:
                self.guard(self.save)
                if self.cards != self.saved_cards or self.images != self.saved_images:
                    return
        self.window.destroy()
