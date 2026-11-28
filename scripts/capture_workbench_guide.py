"""Refresh workbench guide screenshots from the real Tk application on X11.

Use an isolated desktop with Tk, Pillow, Noto Sans CJK SC, and FFmpeg.
The editor only sees disposable local examples. Captures do not call a model.
Run with python -m scripts.capture_workbench_guide from the repository root.
"""

import argparse
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from unittest.mock import patch

from PIL import Image, ImageDraw

from scripts import capture_storyboard_guide as desktop
from scripts.windows_trial import ROOT, draw_frame, make_examples
from scripts.workbench_guide_examples import build_batch_example, build_ecommerce_example, draw_bottle
from src import storyboard_guide
from src.ecommerce_delivery import label_board_sheet
from src.ecommerce_project import EcommerceProject, EcommerceShot
from src.ecommerce_video import analyze_video
from src.production_rules import ENGLISH
from src.ui_language import translate


TOPICS = (
    "general", "guide_navigation", "ecommerce_import", "ecommerce_shots", "ecommerce_assets",
    "ecommerce_delivery", "batch_import", "batch_plan", "batch_assets", "batch_queue",
    "batch_delivery", "review_zip", "review_images", "review_cuts", "review_repair", "jobs", "api",
)
DEFAULT_OUTPUT = ROOT / "assets" / "workbench_guide"
PREVIEW_NAME = "预览_信号站_相邻两组.zip"


class WorkbenchCapture(desktop.Capture):
    @property
    def examples(self):
        return self.project.parent

    def caption(self, parent, chinese, english):
        return self.wait(lambda scope: next(
            (w for w in desktop.children(scope)
             if isinstance(w, ttk.Label) and w.winfo_ismapped()
             and w.cget("text") == (chinese if self.language == "zh" else english)), None),
            chinese, parent=parent)

    def entry_beside(self, label):
        row = int(label.grid_info()["row"])
        return next(w for w in label.master.grid_slaves(row=row, column=1) if isinstance(w, ttk.Entry))

    def fill(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, str(value))
        self.root.update()

    def page(self, index):
        self.navigation().select(index)
        self.root.update()
        return self.navigation().nametowidget(self.navigation().select())

    def dialog(self):
        return self.wait(lambda scope: next(
            (w for w in desktop.children(scope) if isinstance(w, tk.Toplevel) and w.winfo_ismapped()), None),
            "local tool window")

    def capture_general(self):
        self.production_page()
        self.press("剧本创作")
        self.control("planning_source", kind=tk.Text)
        self.production_page()
        self.invoke(self.control("a_home_project_help", kind=ttk.Button))
        self.snapshot("general")

    def capture_guide_navigation(self):
        page = self.page(4)
        geometry = self.root.geometry()
        self.root.geometry("1120x970+0+0")
        # Use the new general chapter's actual capture when writing to a staging directory.
        # A guide screenshot must not display a prior capture of itself.
        general = self.output / f"general_{self.language}.webp"
        context = (patch.object(storyboard_guide, "WORKBENCH_GUIDE_IMAGES", self.output.resolve())
                   if general.is_file() else nullcontext())
        storyboard_guide.screenshot.cache_clear()
        with context:
            self.invoke(self.control("workbench_guide_open", parent=page, kind=ttk.Button))
            topics = self.control("guide_topic_list", parent=page, kind=ttk.Treeview)
            if not topics.exists("guide_navigation"):
                raise RuntimeError("The guide navigation topic has not been registered.")
            illustration = self.control("guide_screenshot", parent=page, kind=tk.Label)
            if not illustration.cget("image"):
                topics.selection_set("shots")
                topics.event_generate("<<TreeviewSelect>>")
                self.root.update()
            topics.see("guide_navigation")
            self.snapshot("guide_navigation")
        storyboard_guide.screenshot.cache_clear()
        self.root.geometry(geometry)
        self.root.update()

    def capture_ecommerce(self):
        project = self.make_ecommerce_example()
        self.navigation().select(1)
        self.root.update()
        workflow = self.control("ecommerce_workflow")
        stages = self.control("ecommerce_steps", parent=workflow)
        with patch.object(filedialog, "askopenfilename", return_value=str(project)):
            self.press("打开电商项目", parent=workflow, english="Open project")

        def current_stage():
            return stages.nametowidget(stages.select())

        def rows(table):
            return self.wait(lambda scope: next(
                (widget for widget in desktop.children(scope)
                 if isinstance(widget, ttk.Treeview) and widget.get_children()), None),
                table, parent=current_stage())

        poster = "View video cover" if self.language == "en" else "查看视频封面"
        self.wait(lambda scope: any(isinstance(widget, ttk.Button) and widget.winfo_ismapped()
                                   and widget.cget("text") == poster and widget.cget("image")
                                   for widget in desktop.children(scope)),
                  "the decoded reference poster", parent=current_stage())
        self.snapshot("ecommerce_import")
        self.press("下一步：分镜分析", parent=current_stage(), english="Next: Shot analysis")
        shots = rows("the confirmed shot list")
        shots.selection_set(shots.get_children()[0])
        self.snapshot("ecommerce_shots")
        with patch.object(messagebox, "askyesno", return_value=True):
            self.press("确认分镜并分析资产", parent=current_stage(), english="Approve shots & audit assets")
        assets = rows("delivery asset audit")
        assets.selection_set(assets.get_children()[0])
        self.snapshot("ecommerce_assets")
        self.press("下一步：提示词与交付", parent=current_stage(), english="Next: Prompts & delivery")
        self.press("生成交付预览", parent=current_stage(), english="Prepare delivery preview")
        files = rows("local delivery preview")
        board = next(item for item in files.get_children() if "storyboard_sheet" in item)
        files.selection_set(board)
        self.snapshot("ecommerce_delivery")

    def make_ecommerce_example(self):
        """Prepare disposable production state from the packaged offline practice pair."""
        folder = self.examples / "Workbench" / "Ecommerce"
        reference, product = build_ecommerce_example(folder)
        analyzed = analyze_video(reference)
        names = ("Display table", "Wide shot", "Close-up", "Product shot",
                 "The reference bottle stands on the display.", "The camera shows the bottle label.",
                 "The last angle shows the entire bottle.") if self.language == "en" else (
            "产品展示台", "全景", "近景", "产品特写",
            "参考瓶立在展示台上。", "镜头展示瓶身标签。", "最后一个角度展示完整瓶身。",
        )
        scene_file = folder / "Studio display 16x9.png"
        scene = Image.new("RGB", (640, 360), "#ead3be")
        paint = ImageDraw.Draw(scene)
        paint.rounded_rectangle((190, 40, 450, 270), radius=60, fill="#f4ebdd")
        paint.rectangle((0, 228, 639, 359), fill="#997d72")
        scene.save(scene_file)

        board_file = folder / "SB01 - storyboard.png"
        board = Image.new("RGB", (1080, 1920), "#344046")
        for index, background in enumerate(("#e8b778", "#263e55", "#cde6d7")):
            panel = Image.new("RGB", (540, 960), background)
            paint = ImageDraw.Draw(panel)
            paint.rectangle((0, 740, 540, 960), fill="#715a4f")
            draw_bottle(paint, (270, 310, 246)[index], (300, 155, 360)[index],
                        (3.7, 4.9, 3.2)[index], color="#378d79", cap="#275d54")
            row, column = divmod(index, 2)
            board.paste(panel, (column * 540, row * 960))
        board.save(board_file)

        shots = [
            EcommerceShot(str(index + 1), start_ms=timing.start_ms, end_ms=timing.end_ms,
                          scene=names[0], size=names[index + 1], angle="Eye level" if self.language == "en" else "平视",
                          camera="Static" if self.language == "en" else "固定", action=names[index + 4],
                          dialogue="none" if self.language == "en" else "无", contains_product=True)
            for index, timing in enumerate(analyzed.shots)
        ]
        labeled = folder / "SB01 - numbered storyboard.png"
        label_board_sheet(board_file, labeled, [shot.id for shot in shots])
        info = analyzed.info
        project = EcommerceProject(
            "Practice · Luma Bottle" if self.language == "en" else "练习 · Luma 水瓶",
            video_path=str(reference), duration_ms=info.duration_ms,
            video_width=info.width, video_height=info.height,
            product_name="Luma", product_refs=[str(product)], product_reviewed=True, shots=shots,
            assets={f"scene:{names[0]}": str(scene_file), "board:SB01": str(labeled)},
        )
        project.shot_approval = project.shot_key()
        path = folder / "Luma.cfecom"
        project.save(path)
        return path

    def capture_batch(self):
        self.production_page()
        self.press("批量制作中心")
        panel = self.control("batch_workspace")
        batch = self.examples / "Workbench" / "Batch" / "Signal-Station.cfbatch"
        with patch.object(filedialog, "askopenfilename", return_value=str(batch)):
            self.press("打开批次", parent=panel, english="Open batch")
        episode = self.control("episode", parent=panel, kind=ttk.Combobox)
        self.wait(lambda _: len(self.root.tk.splitlist(episode["values"])) == 2, "two practice episodes")
        episode.current(1)
        episode.event_generate("<<ComboboxSelected>>")
        self.wait(lambda _: episode.get().startswith("EP02"), "the selected second episode")
        group = self.control("batch_group", parent=panel, kind=ttk.Combobox)
        self.wait(lambda _: "SB02" in self.root.tk.splitlist(group["values"]), "the second storyboard group")
        group.set("SB02")
        group.event_generate("<<ComboboxSelected>>")
        for stage in ("import", "plan", "assets", "queue", "delivery"):
            topic = f"batch_{stage}"
            if topic not in self.requested:
                continue
            self.invoke(self.control(f"step_{stage}", parent=panel, kind=ttk.Button))
            if stage == "plan":
                trace = self.control("trace", parent=panel, kind=ttk.Treeview)
                target = self.wait(lambda _: next(
                    (item for item in trace.get_children() if str(trace.item(item, "values")[0]).startswith("SB02")),
                    None), "a shot in EP02/SB02")
                trace.selection_set(target)
                trace.see(target)
                trace.event_generate("<<TreeviewSelect>>")
            if stage == "queue":
                jobs = self.control("jobs", parent=panel, kind=ttk.Treeview)
                if not jobs.get_children():
                    self.press("本集加入队列", parent=panel, english="Queue episode")
                    self.wait(lambda _: jobs.get_children(), "locally queued jobs")
            self.snapshot(topic)

    def capture_review(self):
        review = self.page(2)
        start_caption = translate(self.root, "开始验收")
        start = self.wait(lambda scope: next(
            (w for w in desktop.children(scope)
             if isinstance(w, ttk.Button) and w.winfo_ismapped() and w.cget("text") == start_caption),
            None), start_caption, parent=review)
        archive = self.examples / PREVIEW_NAME
        form = start.master
        archive_field = next(w for w in form.grid_slaves(row=0, column=1) if isinstance(w, ttk.Entry))
        self.fill(archive_field, archive)
        self.invoke(start)
        files = self.wait(lambda scope: next(
            (w for w in desktop.children(scope) if isinstance(w, ttk.Combobox) and w.winfo_ismapped()
             and any("storyboard" in name for name in self.root.tk.splitlist(w["values"]))),
            None), "validated preview ZIP", parent=review)
        split = next(w for w in desktop.children(review) if isinstance(w, ttk.Panedwindow) and w.winfo_ismapped())
        split.sashpos(0, 115)
        self.root.update_idletasks()
        board = next(name for name in self.root.tk.splitlist(files["values"]) if "storyboard" in name)
        files.set(board)
        files.event_generate("<<ComboboxSelected>>")
        self.wait(lambda scope: next(
            (w for w in desktop.children(scope) if isinstance(w, ttk.Label) and w.winfo_ismapped()
             and bool(w.cget("image"))), None), "a real board image from the ZIP", parent=review)
        self.snapshot("review_zip")

        if "review_images" in self.requested:
            self.capture_review_image(review)
        if "review_cuts" in self.requested:
            self.press("景别机位与格间衔接", parent=review)
            window = self.dialog()
            window.geometry("1120x765+64+55")
            filter_caption = "仅跨页或跨组" if self.language == "zh" else "Across pages or groups"
            check = self.wait(lambda scope: next(
                (w for w in desktop.children(scope)
                 if isinstance(w, ttk.Checkbutton) and w.cget("text") == filter_caption), None),
                filter_caption, parent=window)
            self.invoke(check)
            self.snapshot("review_cuts", window)
            window.destroy()
        if "review_repair" in self.requested:
            self.capture_repair(review)
        if "jobs" in self.requested:
            self.invoke(self.control("workbench_jobs", parent=review, kind=ttk.Button))
            panel = self.control("jobs_center")
            table = self.control("registered_jobs", parent=panel, kind=ttk.Treeview)
            rows = self.wait(lambda _: table.get_children(), "completed local inspection job")
            table.selection_set(rows[0])
            table.event_generate("<<TreeviewSelect>>")
            self.snapshot("jobs")

    def capture_review_image(self, review):
        odd_ratio = self.examples / "Square-Reference.png"
        original = self.examples / "Wide-Reference.png"
        draw_frame(original, 1, board=False)
        with Image.open(original) as image:
            image.crop((140, 0, 500, 360)).save(odd_ratio)
        self.press("图片大小与比例", parent=review)
        window = self.dialog()
        window.geometry("980x700+120+78")
        with patch.object(filedialog, "askopenfilename", return_value=str(odd_ratio)):
            self.press("选择本地图片", parent=window, english="Choose local image")
        self.wait(lambda scope: next((w for w in desktop.children(scope)
                  if isinstance(w, tk.Canvas) and w.find_all()), None), "decoded image", parent=window)
        self.snapshot("review_images", window)
        window.destroy()

    def capture_repair(self, review):
        errors = []

        def inspect_open_dialog():
            window = None
            try:
                window = self.dialog()
                window.geometry("1060x745+95+60")
                tabs = next(w for w in desktop.children(window) if isinstance(w, ttk.Notebook))
                tabs.select(1)
                page = tabs.nametowidget(tabs.select())
                self.root.update()
                shot = self.caption(page, "完整镜号", "Full shot ID")
                self.fill(self.entry_beside(shot), "SB01-01")
                self.press("查看关联文件", parent=page)
                self.wait(lambda scope: next(
                    (w for w in desktop.children(scope) if isinstance(w, tk.Text)
                     and "SD2_prompt.txt" in w.get("1.0", "end")), None), "related archived files", parent=page)
                self.snapshot("review_repair", window)
            except Exception as error:
                errors.append(error)
            finally:
                if window is not None:
                    window.destroy()

        repair_caption = translate(self.root, "资产与返修")
        opener = self.wait(lambda scope: next(
            (w for w in desktop.children(scope)
             if isinstance(w, ttk.Button) and w.winfo_ismapped() and w.cget("text") == repair_caption), None),
            repair_caption, parent=review)
        self.root.after_idle(inspect_open_dialog)
        self.invoke(opener)
        if errors:
            raise errors[0]

    def capture_api(self):
        page = self.page(3)
        tabs = next(w for w in desktop.children(page) if isinstance(w, ttk.Notebook))
        tabs.select(2)
        self.root.update()
        self.snapshot("api")

    def run(self):
        try:
            self.capture_topics()
        finally:
            # The next locale needs its own Tk default root and variables.
            self.root.destroy()

    def capture_topics(self):
        if "general" in self.requested:
            self.capture_general()
        if "guide_navigation" in self.requested:
            self.capture_guide_navigation()
        if any(topic.startswith("ecommerce_") for topic in self.requested):
            self.capture_ecommerce()
        if any(topic.startswith("batch_") for topic in self.requested):
            self.capture_batch()
        if any(topic.startswith("review_") or topic == "jobs" for topic in self.requested):
            self.capture_review()
        if "api" in self.requested:
            self.capture_api()
        if missing := self.requested - self.saved:
            raise RuntimeError(f"Missing captures: {', '.join(sorted(missing))}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("zh", "en"))
    parser.add_argument("--topic", choices=TOPICS, action="append")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=True)
    requested = set(options.topic or TOPICS)
    languages = (options.language,) if options.language else ("zh", "en")
    for language in languages:
        with TemporaryDirectory(prefix="studio-workbench-guide-") as temp:
            examples = Path(temp) / "Examples"
            make_examples(examples, Path(temp) / "scratch", ENGLISH, PREVIEW_NAME)
            if any(topic.startswith("batch_") for topic in requested):
                build_batch_example(examples / "Workbench" / "Batch")
            with patch.object(desktop, "Capture", WorkbenchCapture):
                desktop.capture_desktop(language, examples / "SB01.cfproject", options.output, requested)


if __name__ == "__main__":
    main()
