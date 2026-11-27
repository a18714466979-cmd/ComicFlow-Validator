"""Preflight UI for approved dialogue and planned image counts."""

import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import filedialog, scrolledtext, ttk

from .production_rules import CHINESE, ENGLISH
from .storyboard_preflight import IMAGE_LIMIT, group_capacity, image_budget, plan_dialogue


def add_image_budget(window):
    budget = ttk.LabelFrame(window, text="单组九图预算", padding=10)
    budget.pack(fill="x", padx=12, pady=(12, 4))
    labels = ("主角", "配角", "道具 / HUD", "场景")
    counts = [tk.StringVar(value="0") for _ in labels]
    ttk.Label(budget, text="故事板固定 1 张").grid(row=0, column=0, padx=(0, 10))
    for index, (label, count) in enumerate(zip(labels, counts), start=1):
        ttk.Label(budget, text=label).grid(row=0, column=2 * index - 1, padx=(0, 4))
        ttk.Entry(budget, textvariable=count, width=4).grid(row=0, column=2 * index, padx=(0, 8))
    budget_result = ttk.Label(budget, wraplength=620)
    budget_result.grid(row=1, column=0, columnspan=9, sticky="w", pady=(8, 0))

    def update_budget(*_args) -> None:
        try:
            total, remaining = image_budget(*(int(count.get()) for count in counts))
        except ValueError:
            budget_result.configure(text="请填写各类计划交付的图片张数，使用非负整数。")
            return
        detail = f"还可用 {remaining} 张" if remaining >= 0 else (
            f"超出 {-remaining} 张。按道具 → 配角 → 主角 → 同类场景的顺序检查能否合图。"
        )
        budget_result.configure(text=f"总计 {total} / {IMAGE_LIMIT} 张 · {detail}")

    for count in counts:
        count.trace_add("write", update_budget)
    update_budget()


def open_preflight_dialog(parent: tk.Tk, validator: str, rules: str = ENGLISH) -> None:
    chinese = rules == CHINESE
    window = tk.Toplevel(parent)
    window.title("ComicFlow 中文对白预检" if chinese else "ComicFlow 生图前预检")
    window.geometry("840x720")
    window.minsize(660, 540)
    if not chinese:
        add_image_budget(window)

    section = ttk.LabelFrame(window, text="中文对白容量预排" if chinese else "英文对白容量预排", padding=10)
    section.pack(expand=True, fill="both", padx=12, pady=(6, 12))
    instruction = ("导入批准对白 JSON，每组至多 100 字。可用 sentence_ends 标注自然切点。"
                   if chinese else "导入批准对白 JSON，或粘贴到下方。每条记录是一句完整发声。")
    ttk.Label(section, text=instruction, wraplength=640).pack(anchor="w")
    source = scrolledtext.ScrolledText(section, height=8, wrap="word")
    source.pack(fill="both", expand=True, pady=6)
    controls = ttk.Frame(section)
    controls.pack(fill="x")
    input_status = tk.StringVar(value="无对白的中文常规组为 9 或 10 格。" if chinese else "没有对白时可只用上方的九图预算。")
    ttk.Label(section, textvariable=input_status, wraplength=640).pack(anchor="w", pady=6)
    output = scrolledtext.ScrolledText(section, height=12, state="disabled", wrap="word")
    output.pack(expand=True, fill="both")
    results: Queue[list[dict] | Exception] = Queue()

    def set_source(text: str) -> None:
        source.delete("1.0", "end")
        source.insert("1.0", text)

    def load_json() -> None:
        filename = filedialog.askopenfilename(parent=window, filetypes=(("对白 JSON", "*.json"),))
        if filename:
            try:
                set_source(Path(filename).read_text(encoding="utf-8-sig"))
                input_status.set(Path(filename).name)
            except (OSError, UnicodeError) as exc:
                input_status.set(f"无法读取对白文件：{exc}")

    def receive() -> None:
        try:
            result = results.get_nowait()
        except Empty:
            window.after(100, receive)
            return
        start.configure(state="normal")
        if isinstance(result, Exception):
            input_status.set("预排未完成。")
            report = str(result)
        else:
            input_status.set(f"{len(result)} 个对白容量候选组。请结合镜头内容与动作交接锁定最终分组。")
            lines = []
            for index, group in enumerate(result, start=1):
                lines.append(f"候选组 {index:02d} · {group_capacity(group, rules)}")
                for fragment in group["fragments"]:
                    lines.append(f"  {fragment['id']} · {fragment['speaker']} · {fragment['cue']} "
                                 f"[{fragment['start']}:{fragment['end']}]  {fragment['text']}")
                lines.append("")
            empty = "无发声对白。常规组为 9 或 10 格。" if chinese else "没有英文对白。"
            report = "\n".join(lines) if lines else empty
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", report)
        output.configure(state="disabled")

    def run_plan() -> None:
        approved = source.get("1.0", "end-1c")
        planner = Path(validator).expanduser().with_name("plan_english_dialogue.py") if validator and not chinese else None
        if not chinese and planner is None:
            input_status.set("请先在验收窗口选择故事板校验脚本。")
            return
        start.configure(state="disabled")
        input_status.set("正在本地预排…")

        def worker() -> None:
            try:
                results.put(plan_dialogue(approved, planner, rules=rules))
            except Exception as exc:
                results.put(exc)

        Thread(target=worker, daemon=True).start()
        window.after(100, receive)

    ttk.Button(controls, text="导入 JSON", command=load_json).pack(side="left")
    example = ('[\n  {"id": "D001", "speaker": "角色甲", "text": "把门扶住。"}\n]' if chinese
               else '[\n  {"id": "D001", "speaker": "角色甲", "text": "Hold the door."}\n]')
    ttk.Button(controls, text="填入示例", command=lambda: set_source(example)).pack(side="left", padx=6)
    start = ttk.Button(controls, text="预排中文对白" if chinese else "预排完整句", command=run_plan)
    start.pack(side="right")
