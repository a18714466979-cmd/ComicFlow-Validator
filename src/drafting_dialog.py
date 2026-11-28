"""Reviewable text drafts and dialogue capacity in the single-group workbench."""

import copy
import tkinter as tk
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit

from .ui_language import translate, window_title
from .production_dialog import caption, field, fields_text, project_filetypes, read_fields, refresh_captions, write_text
from .production_dialogue import group_scope, plan_project_dialogue, save_scope, scope_from_shots, select_scope
from .production_drafting import (
    DRAFT_SHOT_FIELDS, HANDOFF_FIELDS, HANDOFF_TASK, SD2_FIELDS, SD2_TASK, SHOT_TASK, TASKS,
    apply_candidate, build_context, instructions_for, record_candidate, revise_candidate,
)
from .production_project import ProductionProject
from .production_rules import CHINESE, ENGLISH
from .storyboard_preflight import IMAGE_LIMIT, group_capacity, image_budget
from .text_api import build_text_request, locked_text_instructions, request_text
from .vision import PROVIDERS, VisionSettings


class DraftingDialog:
    def __init__(self, production, session, *, start_task=None, parent=None):
        self.production = production
        self.project = production.project
        self.session = session
        self.previous_context = None
        self.plan = []
        self.plan_fingerprint = ""
        self.candidate = None
        self.busy = False
        self.embedded = parent is not None
        if self.embedded:
            self.window = parent.winfo_toplevel()
            self.frame = ttk.Frame(parent, name="drafting_panel")
            self.frame.pack(fill="both", expand=True)
        else:
            self.window = tk.Toplevel(production.window)
            self.window.title(window_title(self.window, "文本制片"))
            self.window.geometry("1040x774")
            self.window.minsize(820, 665)
            self.window.transient(production.window)
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            self.frame = self.window
        self.tabs = tabs = ttk.Notebook(self.frame)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        capacity = ttk.Frame(tabs, padding=10)
        ai = ttk.Frame(tabs, padding=10)
        tabs.add(capacity, text=translate(tabs, "中文对白预排" if self.project.rules == CHINESE else "对白与九图预排"))
        tabs.add(ai, text=translate(tabs, "文本模型与历史"))
        self.setup_plan(capacity)
        self.setup_ai(ai)
        self.set_start_task(start_task)

    def set_start_task(self, start_task):
        if start_task:
            self.tabs.select(1)
            self.task_picker.current(TASKS.index(start_task))
            self.pick_task()

    def refresh_language(self):
        refresh_captions(self.frame)
        capacity = "中文对白预排" if self.project.rules == CHINESE else "对白与九图预排"
        self.tabs.tab(0, text=translate(self.tabs, capacity))
        self.tabs.tab(1, text=translate(self.tabs, "文本模型与历史"))
        current = self.task_picker.current()
        self.task_picker["values"] = tuple(translate(self.window, task) for task in TASKS)
        if current >= 0:
            self.task_picker.current(current)

    def dirty(self):
        return (self.candidate is not None and self.editor.get("1.0", "end-1c") != self.editor_record
                or (self.embedded and self.production.dirty()))

    def save(self):
        if not self.allow_close():
            return False
        if self.candidate and self.editor.get("1.0", "end-1c") != self.editor_record:
            self.save_revision()
        elif self.embedded and self.production.dirty():
            self.production.save()
        return True

    def allow_close(self):
        if self.busy:
            self.status.set(translate(self.window, "文本请求仍在处理，请等本次返回后关闭。"))
        return not self.busy

    def sync_project(self, project=None):
        if not self.embedded or self.busy or self.dirty():
            return False
        if project is None:
            project = self.production.latest_project()
        if project == self.project:
            return True
        source = self.source.current()
        selected_source = self.sources[source].id if source >= 0 else ""
        selected_shot = self.targets[self.shot.current()][1].id if self.shot.current() >= 0 else ""
        candidate = self.candidate["id"] if self.candidate else ""
        if not self.production.sync_project(project):
            return False
        self.sources = self.project.sources
        self.source["values"] = tuple(f"{item.name} · {item.version}" for item in self.sources)
        source_index = next((i for i, item in enumerate(self.sources) if item.id == selected_source), -1)
        if source_index >= 0:
            self.source.current(source_index)
            self.pick_task()
        elif self.sources:
            self.source.current(len(self.sources) - 1)
            self.pick_source()
        else:
            self.source.set("")
            self.pick_task()
        for index, (_, shot) in enumerate(self.targets):
            if shot.id == selected_shot and str(self.shot.cget("state")) == "readonly":
                self.shot.current(index)
                break
        self.refresh_history(preferred=candidate)
        self.asset_next.state(["!disabled"] if self.project.shots else ["disabled"])
        return True

    def close(self):
        if self.allow_close():
            self.frame.destroy()

    def buttons(self, bar, *entries):
        widgets = []
        for title, action in entries:
            button = caption(ttk.Button(bar, command=lambda run=action: self.run(run)), title)
            button.pack(side="left", padx=(0, 6))
            widgets.append(button)
        return widgets

    def run(self, action):
        try:
            self.sync_project()
            action()
        except Exception as exc:
            messagebox.showerror(translate(self.window, "文本制片"), translate(self.window, str(exc)), parent=self.window)

    def setup_plan(self, page):
        chinese = self.project.rules == CHINESE
        guidance = ("按实际发声预排，每组至多 100 字。默认在句末或分号处顺延。"
                    "可用 sentence_ends 指定批准的语义停顿，填写原文零起点的字符右边界。") if chinese else (
                        "按「项目与组」的批准对白顺序预排。对白 JSON 的 sentence_ends 可标同一源 ID 的多句终点，"
                        "数值为零起点的字符右边界。没有终点记录时整条按一句处理。")
        ttk.Label(page, wraplength=900, text=translate(page, guidance)).pack(anchor="w")
        if not chinese:
            budget = ttk.LabelFrame(page, text=translate(page, "计划交付图片"), padding=8)
            budget.pack(fill="x", pady=9)
            self.counts = [tk.StringVar(self.window, "0") for _ in range(4)]
            caption(ttk.Label(budget), "故事板 1 张").pack(side="left")
            for title, count in zip(("主角", "配角", "道具 / HUD", "场景"), self.counts):
                caption(ttk.Label(budget), title).pack(side="left", padx=(9, 4))
                ttk.Entry(budget, textvariable=count, width=4).pack(side="left")
                count.trace_add("write", self.show_budget)
            self.budget_status = tk.StringVar(self.window)
            ttk.Label(page, textvariable=self.budget_status).pack(anchor="w")
            self.show_budget()
        bar = ttk.Frame(page)
        bar.pack(fill="x", pady=8)
        self.buttons(bar, ("预排中文对白" if chinese else "预排批准整句", self.run_plan),
                     ("采用所选对白组", self.choose_group),
                     ("载入上一组交接", self.load_previous))
        self.group_picker = ttk.Combobox(bar, state="readonly", width=35 if chinese else 22)
        self.group_picker.pack(side="left", padx=(0, 5))
        caption(ttk.Label(bar), "上一组").pack(side="left")
        self.previous_group = tk.StringVar(self.window, self.project.previous_group)
        ttk.Entry(bar, textvariable=self.previous_group, width=8).pack(side="left", padx=5)
        if chinese:
            custom = ttk.Frame(page)
            custom.pack(fill="x", pady=(0, 6))
            self.buttons(custom, ("采用镜头当前对白范围", self.choose_shot_scope))
        self.plan_report = self.production.editor(page, 15)
        self.plan_report.pack(fill="both", expand=True)
        self.plan_report.configure(state="disabled")

    def show_budget(self, *_):
        actual = sum(not image.reference_only for image in self.project.images)
        try:
            count, remaining = image_budget(*(int(value.get()) for value in self.counts))
        except ValueError:
            self.budget_status.set("计划张数须为非负整数。")
            return
        balance = f"可用 {remaining} 张" if remaining >= 0 else f"超出 {-remaining} 张"
        self.budget_status.set(f"计划 {count} / {IMAGE_LIMIT} 张，{balance}。项目已导入正式图 {actual} 张。")

    def set_report(self, widget, content):
        widget.configure(state="normal")
        write_text(widget, content)
        widget.configure(state="disabled")

    def run_plan(self):
        self.plan = []
        self.group_picker.set("")
        self.group_picker["values"] = ()
        self.set_report(self.plan_report, "")
        planner = self.production.validator_path().with_name("plan_english_dialogue.py") if self.project.rules == ENGLISH else None
        self.plan = plan_project_dialogue(self.project, planner)
        self.plan_fingerprint = self.project.fingerprint()
        choices, lines = [], []
        for index, group in enumerate(self.plan, 1):
            name = f"候选 {index:02d} · {group_capacity(group, self.project.rules)}"
            choices.append(name)
            lines.append(name)
            for fragment in group["fragments"]:
                lines.append(f"  {fragment['id']} · {fragment['speaker']} · {fragment['cue']} "
                             f"[{fragment['start']}:{fragment['end']}]  {fragment['text']}")
            lines.append("")
        self.group_picker["values"] = choices
        if choices:
            initial = next((i for i, group in enumerate(self.plan)
                            if group_scope(group) == self.project.dialogue_scope), 0)
            self.group_picker.current(initial)
        empty = "本项目无批准对白。中文常规无对白组为 9 或 10 格。" if self.project.rules == CHINESE else "本项目无批准对白。"
        self.set_report(self.plan_report, "\n".join(lines) if lines else empty)

    def choose_group(self):
        index = self.group_picker.current()
        if index < 0 or self.plan_fingerprint != self.project.fingerprint():
            raise ValueError("请按当前项目重新预排，再选择一个对白候选组。")
        if not messagebox.askyesno(translate(self.window, "采用对白候选组"), translate(self.window, "将所选批准范围设为本组。镜头里的对白按原文区间分配。"), parent=self.window):
            return
        select_scope(self.project, self.plan[index], self.previous_group.get())
        self.production.save()
        self.plan_fingerprint = self.project.fingerprint()
        self.plan_report.configure(state="normal")
        self.plan_report.insert("end", f"\n已保存 {self.project.group} 的候选 {index + 1:02d}。")
        self.plan_report.configure(state="disabled")

    def choose_shot_scope(self):
        save_scope(self.project, scope_from_shots(self.project), self.previous_group.get())
        self.production.save()
        self.plan_fingerprint = self.project.fingerprint()
        self.set_report(self.plan_report, f"已保存 {self.project.group} 的实际对白范围。")

    def load_previous(self):
        value = filedialog.askopenfilename(parent=self.window, filetypes=project_filetypes(self.window))
        if not value:
            return
        previous = ProductionProject.open(Path(value))
        if (previous.name, previous.episode, previous.rules) != (self.project.name, self.project.episode, self.project.rules) or (
            int(previous.group[2:]) >= int(self.project.group[2:])
        ):
            raise ValueError("请选择同项目同集、规则一致且序号早于当前组的文件。")
        state = previous.notes.get("本组退出状态", "")
        if not state.strip():
            raise ValueError("上一组项目没有退出状态记录。")
        last = previous.shots[-1].fields if previous.shots else {}
        self.previous_context = {"组号": previous.group, "退出状态": state,
                                 "末镜动作": last.get("动作起止", ""), "末镜连续性": last.get("连续性", "")}
        self.previous_group.set(previous.group)
        self.set_report(self.plan_report, f"{previous.group} 项目记录的退出状态\n{state}\n\n"
                        f"{self.project.group} 当前进入状态\n{self.project.notes.get('本组进入状态') or '待填写'}")

    def setup_ai(self, page):
        config = ttk.Frame(page)
        config.pack(fill="x")
        self.provider = tk.StringVar(self.window, next(reversed(self.session), next(iter(PROVIDERS))))
        self.base_url, self.model, self.key = (tk.StringVar(self.window) for _ in range(3))
        selector = field(config, 0, "文本服务商", self.provider, tuple(PROVIDERS))
        selector.bind("<<ComboboxSelected>>", self.pick_provider)
        for row, (label, variable) in enumerate((("API 基础地址", self.base_url), ("文本模型 ID", self.model),
                                                ("API Key", self.key)), 1):
            entry = field(config, row, label, variable)
            if variable is self.key:
                entry.configure(show="*")
        self.pick_provider()
        self.task_picker = field(config, 4, "任务", tk.StringVar(self.window),
                                 tuple(translate(self.window, task) for task in TASKS))
        self.task_picker.current(0)
        self.task_picker.bind("<<ComboboxSelected>>", self.pick_task)
        self.sources = self.project.sources
        self.source = field(config, 5, "批准剧本", tk.StringVar(self.window),
                            tuple(f"{s.name} · {s.version}" for s in self.sources))
        self.source.bind("<<ComboboxSelected>>", self.pick_source)
        scope = ttk.Frame(config)
        scope.grid(row=6, column=1, sticky="w")
        caption(ttk.Label(config), "剧本行段").grid(row=6, column=0, sticky="w")
        self.start, self.end = (tk.StringVar(self.window) for _ in range(2))
        ttk.Entry(scope, textvariable=self.start, width=7).pack(side="left")
        caption(ttk.Label(scope), " 至 ").pack(side="left")
        ttk.Entry(scope, textvariable=self.end, width=7).pack(side="left")
        self.shot = field(config, 7, "目标镜头（写 SD2 时）", tk.StringVar(self.window), ())
        if self.sources:
            current = self.production.source.current()
            self.source.current(max(0, current))
            self.pick_source()
        self.pick_task()
        buttons = ttk.Frame(page)
        buttons.pack(fill="x", pady=5)
        _, self.send = self.buttons(buttons, ("查看发送内容", self.preview_payload), ("调用模型起草", self.send_request))
        self.status = tk.StringVar(self.window, translate(self.window, "查看发送内容后调用。API Key 只在本次软件运行期间保留。"))
        ttk.Label(page, textvariable=self.status, wraplength=930).pack(anchor="w")
        history = ttk.Frame(page)
        history.pack(fill="x", pady=(5, 0))
        caption(ttk.Label(history), "候选版本").pack(side="left", padx=(0, 8))
        self.history = ttk.Combobox(history, state="readonly")
        self.history.pack(side="left", fill="x", expand=True)
        self.history.bind("<<ComboboxSelected>>", lambda _event: self.show_candidate(self.history.current()))
        split = ttk.Frame(page)
        split.pack(fill="both", expand=True, pady=5)
        self.items = tk.Listbox(split, width=23, selectmode="extended", exportselection=False)
        self.items.pack(side="left", fill="y", padx=(0, 6))
        self.items.bind("<<ListboxSelect>>", lambda _event: self.show_item())
        self.editor = self.production.editor(split, 8)
        self.editor.pack(side="left", fill="both", expand=True)
        actions = ttk.Frame(page)
        actions.pack(fill="x")
        self.buttons(actions, ("保存编辑为新版本", self.save_revision), ("采纳已选建议", self.accept),
                     ("复制交接建议", self.copy_handoff))
        self.asset_next, = self.buttons(actions, ("下一步：分析资产", self.open_assets))
        if self.embedded and self.production.on_stage:
            navigation = ttk.Frame(page)
            navigation.pack(fill="x", pady=(5, 0))
            self.buttons(navigation, ("返回镜头清单", lambda: self.production.open_stage("shots")))
        if not self.project.shots:
            self.asset_next.state(["disabled"])
        self.refresh_history()

    def pick_provider(self, _event=None):
        name = self.provider.get()
        previous = self.session.get(name)
        self.base_url.set(previous.base_url if previous else PROVIDERS[name].base_url)
        self.model.set(previous.model if previous else "")
        self.key.set(previous.api_key if previous else "")

    def pick_source(self, _event=None):
        self.start.set("1")
        self.end.set(str(min(40, len(self.sources[self.source.current()].text.splitlines()))))
        self.pick_task()

    def pick_task(self, _event=None):
        index = self.source.current()
        source_id = self.sources[index].id if index >= 0 else ""
        self.targets = [(i, shot) for i, shot in enumerate(self.project.shots, 1) if shot.source == source_id]
        self.shot["values"] = tuple(f"{self.project.group}-{i:02d} · {shot.anchor}" for i, shot in self.targets)
        self.shot.set("")
        if TASKS[self.task_picker.current()] == SD2_TASK and self.targets:
            self.shot.configure(state="readonly")
            selected = self.production.shots.selection()
            default = next((i for i, (_, shot) in enumerate(self.targets)
                            if selected and shot.id == selected[0]), 0)
            self.shot.current(default)
        else:
            self.shot.configure(state="disabled")

    def payload(self):
        if self.source.current() < 0:
            raise ValueError("请先在「项目与组」导入批准剧本。")
        try:
            start, end = int(self.start.get()), int(self.end.get())
        except ValueError:
            raise ValueError("请输入有效的起始和结束行号。") from None
        shot = self.targets[self.shot.current()][1].id if self.shot.current() >= 0 else ""
        task = TASKS[self.task_picker.current()]
        context, payload = build_context(self.project, self.sources[self.source.current()], task, start, end,
                                         shot, self.previous_context)
        return task, context, instructions_for(task, self.project.rules), payload

    def preview_payload(self):
        _, _, instructions, payload = self.payload()
        if self.embedded:
            panel = ttk.Frame(self.frame, name="drafting_payload_preview")
            header = ttk.Frame(panel, padding=8)
            header.pack(fill="x")
            self.tabs.pack_forget()
            panel.pack(fill="both", expand=True)

            def restore():
                panel.destroy()
                self.tabs.pack(fill="both", expand=True, padx=10, pady=10)

            self.buttons(header, ("返回", restore))
        else:
            panel = tk.Toplevel(self.window)
            panel.title(translate(panel, "本次发送内容"))
            panel.geometry("845x650")
            panel.transient(self.window)
        preview = self.production.editor(panel)
        preview.pack(fill="both", expand=True, padx=10, pady=10)
        self.set_report(preview, f"{translate(panel, '软件锁定规则')}\n{locked_text_instructions(instructions)}\n\n"
                                 f"{translate(panel, '用户资料')}\n{payload}")
        if self.embedded:
            return
        panel.grab_set()
        self.window.wait_window(panel)
        self.window.grab_set()

    def send_request(self):
        if self.embedded and self.dirty():
            raise ValueError("请先保存文本候选，或处理其他工序的项目更新。")
        settings = VisionSettings(self.provider.get(), self.base_url.get().strip(), self.model.get().strip(),
                                  self.key.get().strip())
        task, context, instructions, payload = self.payload()
        build_text_request(settings, instructions, payload)
        host = urlsplit(settings.endpoint()).netloc
        details = translate(self.window, "将所选批准剧本、对白与相关制片状态发往 {host}？\n"
                            "模型 {model}，剧本第 {start}–{end} 行。").format(
            host=host, model=settings.model, start=context["start"], end=context["end"],
        )
        usage = translate(self.window, "调用使用该服务的额度。")
        if not messagebox.askyesno(translate(self.window, "发送文本到模型"), f"{details}\n{usage}", parent=self.window):
            return
        self.session.pop(settings.provider, None)
        self.session[settings.provider] = settings
        self.busy = True
        self.send.configure(state="disabled")
        self.status.set(f"正在调用 {settings.provider}…")
        queue = Queue()

        def worker():
            try:
                queue.put(request_text(settings, instructions, payload))
            except Exception as exc:
                queue.put(exc)

        def receive():
            if not self.frame.winfo_exists():
                return
            try:
                result = queue.get_nowait()
            except Empty:
                self.window.after(100, receive)
                return
            self.busy = False
            self.send.configure(state="normal")
            try:
                if isinstance(result, Exception):
                    raise result
                record_candidate(self.project, task, context, settings.provider, settings.model, result)
                self.production.save()
                self.refresh_history()
                self.status.set("候选已保存。核对后可编辑、查看旧版或选择采纳。")
            except (ValueError, OSError) as exc:
                self.status.set(str(exc))
            except Exception:
                self.status.set("文本请求未完成，请检查模型和服务状态。")

        Thread(target=worker, daemon=True).start()
        self.window.after(100, receive)

    def refresh_history(self, *, preferred=""):
        self.history["values"] = tuple(
            f"{i:02d} · {item['task']} · {item['provider']} · {item['model']} · "
            f"{item['context']['source_version']} · "
            f"{datetime.fromisoformat(item['time']).astimezone():%m-%d %H:%M:%S}"
            for i, item in enumerate(self.project.text_drafts, 1)
        )
        if self.project.text_drafts:
            index = next((idx for idx, item in enumerate(self.project.text_drafts) if item["id"] == preferred),
                         len(self.project.text_drafts) - 1)
            self.history.current(index)
            self.show_candidate(index)
        elif self.candidate is not None:
            self.candidate = None
            self.history.set("")
            self.items.delete(0, "end")
            write_text(self.editor, "")

    def show_candidate(self, index):
        if index < 0:
            return
        self.candidate = self.project.text_drafts[index]
        self.editor_index = -1
        self.items.delete(0, "end")
        if self.candidate["task"] == SHOT_TASK:
            for n, row in enumerate(self.candidate["output"]["shots"], 1):
                self.items.insert("end", f"候选 {n:02d} · {row['line_start']}–{row['line_end']} 行")
        else:
            self.items.insert("end", self.candidate["task"])
        self.items.selection_set(0)
        self.show_item()

    def show_item(self):
        selected = self.items.curselection()
        if not selected or not self.candidate:
            return
        if selected[0] == self.editor_index:
            return
        task, output = self.candidate["task"], self.candidate["output"]
        if task == SHOT_TASK:
            record = output["shots"][selected[0]]["fields"]
            fields = DRAFT_SHOT_FIELDS
        elif task == SD2_TASK:
            record, fields = output["prompt"], SD2_FIELDS
        else:
            record, fields = output["handoff"], HANDOFF_FIELDS
        self.editor_fields = fields
        self.editor_index = selected[0]
        self.editor_record = fields_text(fields, record)
        write_text(self.editor, self.editor_record)

    def save_revision(self):
        selected = self.items.curselection()
        if not self.candidate or len(selected) != 1 or selected[0] != self.editor_index:
            raise ValueError("请选择单条候选再编辑。")
        output = copy.deepcopy(self.candidate["output"])
        values = read_fields(self.editor, self.editor_fields)
        task = self.candidate["task"]
        if task == SHOT_TASK:
            output["shots"][selected[0]]["fields"] = values
        else:
            output["prompt" if task == SD2_TASK else "handoff"] = values
        revise_candidate(self.project, self.candidate, output)
        self.production.save()
        self.refresh_history()
        self.status.set("已保留原候选并保存新版本。")

    def accept(self):
        if self.embedded and self.production.dirty():
            raise ValueError("请先保存文本候选，或处理其他工序的项目更新。")
        if not self.candidate:
            raise ValueError("请选择要采纳的候选版本。")
        task = self.candidate["task"]
        if task == HANDOFF_TASK:
            raise ValueError("先复制交接建议，再在「项目与组」确认并录入批准状态。")
        if self.editor.get("1.0", "end-1c") != self.editor_record:
            raise ValueError("候选有未保存的编辑，请先保存为新版本。")
        selected = self.items.curselection()
        action = f"添加已选的 {len(selected)} 镜待核对分镜，之后在镜头清单确认对白、数量、连续性和净板。" if task == SHOT_TASK else (
            "采用当前候选中的成片动作或声音。请确认表演、设备状态和实际可见性与原镜头相符。"
        )
        if not messagebox.askyesno(translate(self.window, "采纳文本建议"), action, parent=self.window):
            return
        apply_candidate(self.project, self.candidate, selected)
        self.production.refresh()
        self.production.save()
        self.asset_next.state(["!disabled"])
        self.pick_task()
        self.status.set("已写入镜头记录。导出前请完成逐格复核。")

    def open_assets(self):
        if self.busy:
            return
        index = self.source.current()
        preferred = self.sources[index].id if index >= 0 else ""
        self.production.open_assets_for_shots(owner=self.window, preferred_source=preferred)

    def copy_handoff(self):
        if not self.candidate or self.candidate["task"] != HANDOFF_TASK:
            raise ValueError("请选择一份状态交接候选。")
        if self.editor.get("1.0", "end-1c") != self.editor_record:
            raise ValueError("候选有未保存的编辑，请先保存为新版本。")
        self.window.clipboard_clear()
        self.window.clipboard_append(self.editor_record)
        self.status.set("交接建议已复制，可在「项目与组」录入批准状态。")
