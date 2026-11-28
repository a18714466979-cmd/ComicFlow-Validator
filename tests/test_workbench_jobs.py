from io import BytesIO
from threading import Event
import time

from PIL import Image
import pytest

from src.image_api import ImageReply
from src.image_production_dialog import finish_registered_image
from src.production_images import candidate_path
from src.production_project import ProductionProject
from src.production_rules import CHINESE, ENGLISH
from src.production_workspace import StageEditor
from src.vision_dialog import vision_job_key
from src.workbench_jobs import JobOutcome, WorkbenchJobs, canonical_location


class CallQueue:
    def __init__(self):
        self.callbacks = []

    def after(self, delay, callback):
        self.callbacks.append(callback)

    def until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            if self.callbacks:
                self.callbacks.pop(0)()
            time.sleep(.003)
        assert predicate()


def test_plain_tk_busy_command_does_not_block_task_close():
    class PlainWidget:
        def busy(self):
            raise AssertionError("The Tk busy command should never be called by the task editor.")

    editor = StageEditor(None)
    editor.controller = PlainWidget()
    assert editor.allow_close()
    editor.controller.busy = True
    assert not editor.allow_close()


def test_pending_job_has_one_request_and_reopens_its_exact_origin(tmp_path):
    root = CallQueue()
    registry = WorkbenchJobs(root)
    release = Event()
    calls, opened, finished = [], [], []
    path = tmp_path / "组" / "SB03.cfproject"
    key = ("image", canonical_location(path), "first-job")

    def request():
        calls.append("submitted")
        assert release.wait(2)
        return "provider response"

    def finish(value):
        finished.append(value)
        return JobOutcome("ready")

    assert registry.start(key, "生图", str(path), opened.append, request, finish)
    assert registry.active == 1 and registry.image_working(path)
    assert not registry.start(key, "生图", str(path), opened.append, request, finish)
    registry.open(key)
    assert opened == [key] and registry.active == 1
    release.set()
    root.until(lambda: registry.active == 0)
    assert calls == ["submitted"] and finished == ["provider response"]
    assert registry.records[0].status == "ready"


def test_retry_uses_original_response_without_sending_again():
    root = CallQueue()
    registry = WorkbenchJobs(root)
    key = ("vision", "archive.zip", "SB03/frame.png", ENGLISH, "image hash")
    calls, attempts = [], []

    def request():
        calls.append(1)
        return "response to apply"

    def save(response):
        attempts.append(response)
        if len(attempts) == 1:
            raise PermissionError("temporarily locked")
        return JobOutcome("ready")

    assert registry.start(key, "审图", "archive.zip", lambda _: None, request, save)
    root.until(lambda: registry.get(key).status == "write_failed")
    assert not registry.start(key, "审图", "archive.zip", lambda _: None, request, save)
    registry.retry(key)
    assert calls == [1] and attempts == ["response to apply"] * 2
    assert registry.get(key).status == "ready"


def test_image_completion_targets_original_job_and_keeps_sibling_edits(tmp_path):
    first, other = tmp_path / "SB03.cfproject", tmp_path / "SB04.cfproject"
    original = {"id": "submitted", "status": "submitting", "outputs": []}
    group = ProductionProject("原组", "EP01", "SB03")
    group.image_jobs.append(original)
    group.save(first)
    ProductionProject("别组", "EP01", "SB04", rules=CHINESE).save(other)
    separate = other.read_bytes()
    newer = ProductionProject.open(first)
    newer.import_source("新增批准原文", "R1", "Approved while generation ran.")
    newer.image_jobs.append({"id": "unrelated", "status": "queued"})
    newer.save(first)
    content = BytesIO()
    Image.new("RGB", (320, 180), "blue").save(content, format="PNG")

    result = finish_registered_image(first, ("EP01", "SB03", group.rules), original,
                                     ImageReply(results=(content.getvalue(),), request_id="fake-request"))
    actual = ProductionProject.open(first)
    assert result.status == "ready"
    assert actual.sources == newer.sources and actual.image_jobs[1] == newer.image_jobs[1]
    approved_job = actual.image_jobs[0]
    assert approved_job["id"] == "submitted" and approved_job["request_id"] == "fake-request"
    output = approved_job["outputs"][0]
    assert candidate_path(first, output["received_sha256"], output["format"]).read_bytes() == content.getvalue()
    assert other.read_bytes() == separate
    with pytest.raises(ValueError, match="原生图任务记录已变化"):
        finish_registered_image(first, ("EP01", "SB03", group.rules), original, ImageReply())
    assert ProductionProject.open(first) == actual


def test_review_identifier_includes_bytes_location_and_rule_set(tmp_path):
    archive = tmp_path / "review.zip"
    origin = archive, "SB03/storyboard.png", ENGLISH
    key = vision_job_key(origin, b"first image")
    assert key == vision_job_key((archive.parent / "." / archive.name, *origin[1:]), b"first image")
    assert key != vision_job_key(origin, b"replacement image")
    assert key != vision_job_key((*origin[:2], CHINESE), b"first image")
