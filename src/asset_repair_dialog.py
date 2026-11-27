"""Local asset registry and repair packaging controls."""

import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .asset_registry import AssetRegistry
from .repair_package import affected_files, pack_repair
from .storyboard_review import ReviewResult


def open_asset_repair(
    parent: tk.Tk, registry_path: tk.StringVar, validator: str, baseline: ReviewResult | None,
) -> None:
    window = tk.Toplevel(parent)
    window.title("ComicFlow 资产与返修")
    window.geometry("940x720")
    window.minsize(650, 550)
    window.transient(parent)
    window.grab_set()
    tabs = ttk.Notebook(window)
    tabs.pack(fill="both", expand=True, padx=10, pady=10)
    assets, repair = ttk.Frame(tabs, padding=8), ttk.Frame(tabs, padding=8)
    tabs.add(assets, text="资产登记")
    tabs.add(repair, text="返修打包")
    for tab in (assets, repair):
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(8, weight=1)

    controls = []
    busy = False

    def field(tab, row, label, variable, browse=None) -> None:
        ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(tab, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=4)
        if browse:
            control = ttk.Button(tab, text="浏览", command=browse)
            control.grid(row=row, column=2, padx=6)
            controls.append(control)

    def choose(variable, picker, **kwargs) -> None:
        selected = picker(parent=window, **kwargs)
        if selected:
            variable.set(selected)

    def report_area(tab):
        widget = scrolledtext.ScrolledText(tab, height=11, wrap="word", state="disabled")
        widget.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        return widget

    def show(widget, message: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", message)
        widget.configure(state="disabled")

    def button(tab, row, column, label, command) -> None:
        control = ttk.Button(tab, text=label, command=command)
        control.grid(row=row, column=column, sticky="w", padx=4, pady=5)
        controls.append(control)

    def run_task(widget, operation, *args) -> None:
        nonlocal busy
        busy = True
        for control in controls:
            control.configure(state="disabled")
        show(widget, "正在本机处理…")
        pending: Queue[str] = Queue()

        def work() -> None:
            try:
                pending.put(operation(*args))
            except Exception as exc:
                pending.put(f"操作未完成：{exc}")

        def receive() -> None:
            nonlocal busy
            try:
                message = pending.get_nowait()
            except Empty:
                window.after(100, receive)
                return
            busy = False
            for control in controls:
                control.configure(state="normal")
            show(widget, message)

        Thread(target=work, daemon=True).start()
        window.after(100, receive)

    asset_file, key, version, origin, search = (tk.StringVar() for _ in range(5))
    field(assets, 0, "资产登记库", registry_path, lambda: choose(
        registry_path, filedialog.asksaveasfilename, defaultextension=".sqlite3", title="选择或新建本地资产登记库",
        filetypes=(("资产登记库", "*.sqlite3"),), confirmoverwrite=False,
    ))
    field(assets, 1, "批准原图", asset_file, lambda: choose(asset_file, filedialog.askopenfilename))
    field(assets, 2, "资产 ID", key)
    field(assets, 3, "批准版本", version)
    field(assets, 4, "原引用（可选）", origin)
    field(assets, 6, "迁移后的目录", search, lambda: choose(search, filedialog.askdirectory))
    asset_report = report_area(assets)

    def register(db: str, path: str, identifier: str, revision: str, reference: str) -> str:
        if not db or not path:
            raise ValueError("请选择登记库与批准原图。")
        entry = AssetRegistry(Path(db), create=True).register(Path(path), identifier, revision, reference)
        return f"已登记 asset:{entry.identifier}@{entry.version}\n批准来源：{entry.origin}\nSHA-256：{entry.sha256}"

    def recover(db: str, folder: str) -> str:
        if not db or not folder:
            raise ValueError("请选择登记库与迁移后的目录。")
        registry = AssetRegistry(Path(db))
        matches = registry.recover(Path(folder))
        lines = [f"已找回 {len(matches)} / {len(registry.records())} 个批准版本。"]
        lines.extend(f"{asset.identifier}@{asset.version} → {path}" for asset, path in matches.items())
        return "\n".join(lines)

    button(assets, 5, 1, "登记批准版本", lambda: run_task(
        asset_report, register, registry_path.get().strip(), asset_file.get(), key.get(), version.get(), origin.get(),
    ))
    button(assets, 7, 1, "按 SHA-256 找回", lambda: run_task(asset_report, recover, registry_path.get().strip(), search.get()))

    shot, folder, output, problem, fix = (tk.StringVar() for _ in range(5))
    field(repair, 0, "完整镜号", shot)
    field(repair, 2, "返修后交付目录", folder, lambda: choose(folder, filedialog.askdirectory))
    field(repair, 3, "新 ZIP", output, lambda: choose(
        output, filedialog.asksaveasfilename, defaultextension=".zip", filetypes=(("ZIP 交付包", "*.zip"),),
    ))
    field(repair, 4, "问题（可选）", problem)
    field(repair, 5, "实际修复（可选）", fix)
    repair_report = report_area(repair)

    def locate(identity: str) -> str:
        if baseline is None:
            raise ValueError("先在主窗口验收原交付 ZIP，再按镜号查看关联文件。")
        return "关联文件，按实际改动复核：\n" + "\n".join(affected_files(baseline, "", identity.upper()))

    def repack(directory: str, destination: str, db: str, identity: str, issue: str, action: str) -> str:
        if not directory or not destination or not validator:
            raise ValueError("请在主窗口选择校验脚本，再填写返修目录和新 ZIP。")
        related = locate(identity) if identity and baseline else ""
        result = pack_repair(Path(directory), Path(destination), Path(validator),
                             baseline.archive if baseline else None, Path(db) if db else None)
        lines = [f"问题：{issue or '未填写'}", f"位置：{identity or '整包'}", f"修复：{action or '未填写'}", related,
                 f"复验：{'已发布 ' + str(result.output) if result.output else '未发布新 ZIP'}"]
        if result.output:
            lines.append(f"ZIP SHA-256：{result.sha256}")
            for label, members in (("修改", result.changed), ("新增", result.added), ("删除", result.removed)):
                if members:
                    lines.append(label + "：\n" + "\n".join(members))
        return "\n".join([*lines, "", result.report])

    def save_report() -> None:
        filename = filedialog.asksaveasfilename(parent=window, defaultextension=".txt")
        if filename:
            try:
                Path(filename).write_text(repair_report.get("1.0", "end-1c"), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("报告未保存", str(exc), parent=window)

    button(repair, 1, 1, "查看关联文件", lambda: run_task(repair_report, locate, shot.get().strip()))
    button(repair, 6, 1, "复验并打包", lambda: run_task(
        repair_report, repack, folder.get(), output.get(), registry_path.get().strip(), shot.get().strip(),
        problem.get().strip(), fix.get().strip(),
    ))
    button(repair, 6, 2, "保存报告", save_report)

    def close() -> None:
        if busy:
            messagebox.showinfo("正在处理", "请等待当前操作完成。", parent=window)
        else:
            window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)
    parent.wait_window(window)
