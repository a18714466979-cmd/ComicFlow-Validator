"""Keep approved image and vision requests alive outside their editor tabs."""

from dataclasses import dataclass
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import messagebox, ttk

from .guide_links import guide_button
from .ui_language import translate


def canonical_location(path):
    return os.path.normcase(str(Path(path).resolve()))


@dataclass(frozen=True)
class JobOutcome:
    status: str
    detail: str = ""
    value: object = None


@dataclass
class WorkbenchJob:
    key: tuple
    label: str
    location: str
    recover: object
    outcome: JobOutcome
    retry: object = None

    @property
    def status(self):
        return self.outcome.status


_JOB_STATUS = {
    "working": ("进行中", "Running"),
    "ready": ("结果可查看", "Result available"),
    "queued": ("服务商排队中", "Queued at provider"),
    "processing": ("服务商处理中", "Processing at provider"),
    "failed": ("失败", "Failed"),
    "unknown": ("等待核对服务商", "Check provider status"),
    "write_failed": ("结果保存待重试", "Result needs saving"),
    "blocked": ("项目已经变化", "Project changed"),
}


def job_label(widget, status):
    language = int(getattr(widget._root(), "ui_language", "zh") == "en")
    return _JOB_STATUS.get(status, (status, status))[language]


class WorkbenchJobs:
    def __init__(self, root):
        self.root = root
        self._records = {}
        self._listeners = set()

    @property
    def active(self):
        return sum(entry.status == "working" for entry in self._records.values())

    @property
    def records(self):
        return tuple(reversed(self._records.values()))

    def get(self, key):
        return self._records.get(key)

    def image_working(self, path):
        location = canonical_location(path)
        return any(key[:2] == ("image", location) and entry.status == "working"
                   for key, entry in self._records.items())

    def listen(self, widget, notify):
        self._listeners.add(notify)
        widget.bind("<Destroy>", lambda event: self._listeners.discard(notify) if event.widget is widget else None, add="+")

    def changed(self):
        for notify in tuple(self._listeners):
            notify()

    def start(self, key, label, location, recover, call, complete):
        if key in self._records and self._records[key].status in {"working", "write_failed"}:
            return False
        self._records.pop(key, None)
        record = WorkbenchJob(key, label, location, recover, JobOutcome("working"))
        self._records[key] = record
        pending = Queue()

        def worker():
            try:
                pending.put(call())
            except Exception as error:
                pending.put(error)

        def finish(result):
            try:
                record.outcome = complete(result)
            except OSError as error:
                # Retain the returned result and retry its write without resubmitting it.
                record.retry = lambda: finish(result)
                record.outcome = JobOutcome("write_failed", str(error))
            except (ValueError, RuntimeError) as error:
                record.retry = None
                record.outcome = JobOutcome("blocked", str(error))
            else:
                record.retry = None
            self.changed()

        def poll():
            try:
                result = pending.get_nowait()
            except Empty:
                self.root.after(80, poll)
                return
            finish(result)

        Thread(target=worker, daemon=True).start()
        self.root.after(80, poll)
        self.changed()
        return True

    def retry(self, key):
        if entry := self.get(key):
            if entry.retry:
                entry.retry()

    def open(self, key):
        if entry := self.get(key):
            return entry.recover(key)


def build_job_center(parent, registry):
    """Mount the queue and its recovery controls in an existing workbench page."""
    frame = ttk.Frame(parent, name="jobs_center", padding=12)
    table_area = ttk.Frame(frame)
    table_area.pack(fill="both", expand=True)
    columns = ("task", "status", "source")
    table = ttk.Treeview(table_area, name="registered_jobs", show="headings", columns=columns,
                         selectmode="browse", height=8)
    bar = ttk.Scrollbar(table_area, command=table.yview)
    table.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    table.pack(side="left", fill="both", expand=True)
    for column, width in zip(columns, (180, 130, 460)):
        table.column(column, width=width, stretch=column == "source")
    footer = ttk.Frame(frame)
    footer.pack(fill="x", pady=(8, 0))
    stamp = ttk.Label(footer, wraplength=450)
    stamp.pack(side="left", fill="x", expand=True)
    help_button = guide_button(footer, "jobs")
    if help_button is not None:
        help_button.pack(side="right", padx=(6, 0))
    rows = {}

    def select():
        key = rows.get(table.selection()[0]) if table.selection() else None
        return registry.get(key)

    def command(callback):
        entry = select()
        if entry:
            try:
                callback(entry.key)
            except (OSError, ValueError, RuntimeError) as error:
                messagebox.showerror(translate(parent, "任务中心"), str(error), parent=parent.winfo_toplevel())

    reopen = ttk.Button(footer, name="resume_job", command=lambda: command(registry.open))
    reopen.pack(side="right")
    retry = ttk.Button(footer, name="retry_job_write", command=lambda: command(registry.retry))
    retry.pack(side="right", padx=(0, 6))

    def show_selection(_event=None):
        entry = select()
        reopen.state(["!disabled"] if entry else ["disabled"])
        retry.state(["!disabled"] if entry and entry.retry else ["disabled"])
        stamp.configure(text=entry.outcome.detail if entry else "")

    def refresh():
        english = getattr(frame._root(), "ui_language", "zh") == "en"
        captions = ("任务", "状态", "来源") if not english else ("Task", "Status", "Source")
        for column, caption in zip(columns, captions):
            table.heading(column, text=caption)
        reopen.configure(text="返回原任务" if not english else "Open originating task")
        retry.configure(text="重试保存" if not english else "Retry saving")
        selected = select()
        positions = table.yview()
        table.delete(*table.get_children())
        rows.clear()
        identity = None
        for i, entry in enumerate(registry.records):
            row = str(i)
            rows[row] = entry.key
            table.insert("", "end", iid=row, values=(translate(parent, entry.label), job_label(parent, entry.status),
                                                      entry.location))
            if entry is selected:
                identity = row
        if rows:
            table.selection_set(identity or "0")
            table.yview_moveto(positions[0])
        show_selection()

    registry.listen(frame, refresh)
    frame.refresh_language = refresh
    table.bind("<<TreeviewSelect>>", show_selection)
    table.bind("<Double-1>", lambda _event: command(registry.open))
    frame.bind("<Map>", lambda event: refresh() if event.widget is frame else None)
    refresh()
    return frame
