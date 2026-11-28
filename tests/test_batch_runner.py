import json
from io import BytesIO
from threading import Event
from datetime import datetime

from PIL import Image
import pytest

from src import batch_runner
from src.batch_runner import BatchQueue
from src.batch_workspace import BatchWorkspace
from src.image_api import IMAGE_PROVIDERS, ImageReply, ImageSettings
from src.production_images import approve_candidate
from src.production_project import ProductionProject
from src.production_rules import ENGLISH
from src.text_api import TextReply
from src.vision import VisionSettings


TEXT_SETTINGS = VisionSettings("OpenAI", "https://api.openai.com/v1", "model", "test-key-never-stored")
PRESET = IMAGE_PROVIDERS["OpenAI GPT Image"]
IMAGE_SETTINGS = ImageSettings("OpenAI GPT Image", PRESET.base, PRESET.model, "test-key-never-stored")


@pytest.fixture
def workspace(tmp_path):
    ws = BatchWorkspace.create(tmp_path / "demo.cfbatch", "测试", ENGLISH)
    ws.add_episode("EP01", "pilot", "INT. HALL - DAY\nThe door opens.\nVera: Wait here.")
    return ws


def png():
    data = BytesIO()
    Image.new("RGB", (160, 90), "blue").save(data, format="PNG")
    return data.getvalue()


def test_confirmed_text_pipeline_keeps_stable_shot_and_budget(workspace, monkeypatch):
    q = BatchQueue(workspace)
    assert q.enqueue("EP01", ("shot", "prompt")) > 0
    assert q.enqueue("EP01", ("shot", "prompt")) == 0
    q.run(TEXT_SETTINGS, max_requests=2)
    assert q.spent() == 0 and all(row["status"] == "blocked" for row in q.jobs())
    workspace.approve_plan("EP01")

    def transport(settings, instructions, body):
        data = json.loads(body)
        line = int(next(iter(data["approved_source"]["lines"])))
        output = {"shots": [{"line_start": line, "line_end": line, "fields": {"景别": "全景"}}]}
        if "selected_shot" in data:
            output = {"prompt": {"成片动作": "门打开"}}
        return TextReply(json.dumps(output, ensure_ascii=False))

    monkeypatch.setattr(batch_runner, "request_text", transport)
    first = q.jobs()[0]
    q.run(TEXT_SETTINGS, max_requests=1)
    assert q.spent() == 1 and json.loads(q.candidate_text(first["id"]))["shots"]
    assert q._job(first["id"])["status"] == "review"
    q = BatchQueue(BatchWorkspace.open(workspace.path))
    q.run(TEXT_SETTINGS, max_requests=1)
    assert q.spent() == 1
    p = workspace.group_path("EP01", "SB01")
    before = ProductionProject.open(p)
    q.apply_text(first["id"])
    after = ProductionProject.open(p)
    assert [(s.id, s.dialogue, s.anchor) for s in after.shots] == [(s.id, s.dialogue, s.anchor) for s in before.shots]
    assert after.shots[0].fields["景别"] == "全景"
    assert datetime.fromisoformat(after.text_drafts[0]["time"])
    q.run(TEXT_SETTINGS, max_requests=2)
    assert q.spent() == 2
    assert b"test-key-never-stored" not in q.database.read_bytes()


def test_stale_text_candidate_and_uncertain_timeout_require_explicit_retry(workspace, monkeypatch):
    workspace.approve_plan("EP01")
    q = BatchQueue(workspace)
    q.enqueue("EP01", ("prompt",))

    def timeout(*args):
        raise TimeoutError()

    monkeypatch.setattr(batch_runner, "request_text", timeout)
    q.run(TEXT_SETTINGS, max_requests=1)
    row = q.jobs()[0]
    assert row["status"] == "uncertain"
    with pytest.raises(ValueError):
        q.retry(row["id"])
    q.run(TEXT_SETTINGS, max_requests=1)
    assert q.spent() == 1
    q.retry(row["id"], confirmed=True)
    monkeypatch.setattr(batch_runner, "request_text", lambda *args: TextReply('{"prompt":{"成片动作":"停步"}}'))
    q.run(TEXT_SETTINGS, max_requests=2)
    assert q._job(row["id"])["status"] == "review"
    p = workspace.group_path("EP01", "SB01")
    edited = ProductionProject.open(p)
    edited.shots[0].fields["景别"] = "近景"
    edited.save(p)
    with pytest.raises(ValueError, match="已经变化"):
        q.apply_text(row["id"])
    assert ProductionProject.open(p).shots[0].fields.get("成片动作") != "停步"


def test_async_asset_queries_existing_job_after_restart_then_normal_visual_approval(workspace, monkeypatch):
    workspace.approve_plan("EP01")
    q = BatchQueue(workspace)
    row = q.enqueue_asset("EP01", "SB01", "道具", "信号灯", "常亮", "不透明蓝色外壳")
    provider = "腾讯云混元"
    preset = IMAGE_PROVIDERS[provider]
    settings = ImageSettings(provider, preset.base, preset.model, "secret-key-value", "secret-id-value")
    monkeypatch.setattr(batch_runner, "submit_image", lambda *_: ImageReply(task_id="fake-task", status="queued"))
    q.run(image_settings=settings, max_requests=1)
    assert q._job(row)["status"] == "polling" and q.spent() == 1
    calls = []
    def poll(config, task_id):
        calls.append(task_id)
        return ImageReply((png(),), task_id=task_id)
    monkeypatch.setattr(batch_runner, "query_image", poll)
    q = BatchQueue(BatchWorkspace.open(workspace.path))
    q.run(image_settings=settings, max_requests=1)
    assert calls == ["fake-task"] and q._job(row)["status"] == "review"
    p = workspace.group_path("EP01", "SB01")
    group = ProductionProject.open(p)
    assert len(group.image_jobs) == 1 and group.image_jobs[0]["outputs"]
    assert not group.images
    approve_candidate(group, p, group.image_jobs[0], 0, "blue_lamp.png", "V1", "批准的灯具参考", "实际核对")
    q.run(image_settings=settings, max_requests=1)
    assert q._job(row)["status"] == "approved" and q.spent() == 1
    asset = workspace.asset_inventory()[0]
    assert (asset.identity, asset.state, asset.version, asset.filename) == ("信号灯", "常亮", "V1", "blue_lamp.png")


def test_interruption_pause_and_concurrent_worker_are_safe(workspace):
    workspace.approve_plan("EP01")
    q = BatchQueue(workspace)
    q.enqueue("EP01", ("prompt",))
    stop = Event()
    stop.set()
    q.run(TEXT_SETTINGS, max_requests=1, stop=stop)
    assert q.spent() == 0 and q.jobs()[0]["status"] == "queued"
    first = q.jobs()[0]
    assert q._reserve(first, 1)
    with batch_runner._worker_lock(q.lock_path), pytest.raises(ValueError, match="正在运行"):
        q.run(TEXT_SETTINGS, max_requests=1)
    q.run(TEXT_SETTINGS, max_requests=1)
    assert q.spent() == 1 and q.jobs()[0]["status"] == "uncertain"


def test_blocked_episode_allows_other_episode_and_shared_state_unblocks(workspace, tmp_path, monkeypatch):
    workspace.add_episode("EP02", "next", "INT. ROOM - DAY\nThe signal fades.")
    for episode in ("EP01", "EP02"):
        workspace.approve_plan(episode)
    workspace.require_asset("EP01", "SB01", "灯具", "亮", "R2")
    q = BatchQueue(workspace)
    for episode in ("EP01", "EP02"):
        q.enqueue(episode, ("board",))
    calls = []
    def reply(settings, request):
        calls.append(request)
        return ImageReply((png(),))
    monkeypatch.setattr(batch_runner, "submit_image", reply)
    assert q.run(image_settings=IMAGE_SETTINGS, max_requests=2) == {"blocked": 1, "review": 1}
    assert q.jobs()[0]["message"].endswith("灯具 · 亮 · R2")
    original = tmp_path / "lamp.png"
    original.write_bytes(png())
    workspace.approve_asset("灯具", "亮", "R2", original, "检查灯体和颜色")
    assert q.run(image_settings=IMAGE_SETTINGS, max_requests=2) == {"review": 2}
    assert len(calls) == q.spent() == 2
    current = ProductionProject.open(workspace.group_path("EP01", "SB01"))
    assert current.image_jobs[0]["references"][0]["id"] == current.images[0].id


def test_persisted_result_recovers_before_any_resubmission(workspace, monkeypatch):
    workspace.approve_plan("EP01")
    q = BatchQueue(workspace)
    key = q.enqueue_asset("EP01", "SB01", "角色", "Vera", "常服", "按批准版绘制")
    monkeypatch.setattr(batch_runner, "submit_image", lambda *_: ImageReply((png(),)))
    def interrupt(_row):
        raise OSError("disk busy")
    monkeypatch.setattr(q, "_sync_image", interrupt)
    q.run(image_settings=IMAGE_SETTINGS, max_requests=10)
    assert q._job(key)["status"] == "recorded"
    q = BatchQueue(BatchWorkspace.open(workspace.path))
    monkeypatch.setattr(batch_runner, "submit_image", lambda *_: pytest.fail("duplicate paid submission"))
    q.run(image_settings=IMAGE_SETTINGS, max_requests=10)
    assert q._job(key)["status"] == "review" and q.spent() == 1


def test_group_review_checks_all_source_fingerprints_before_saving(workspace, monkeypatch):
    workspace.approve_plan("EP01")
    queue = BatchQueue(workspace)
    queue.enqueue("EP01", ("prompt",))
    monkeypatch.setattr(batch_runner, "request_text", lambda *_: TextReply('{"prompt":{"成片动作":"等待信号"}}'))
    queue.run(TEXT_SETTINGS, max_requests=8)
    preview = queue.group_preview("EP01", "SB01", "prompt")
    assert preview.index("SB01-01") < preview.index("SB01-02")
    path = workspace.group_path("EP01", "SB01")
    project = ProductionProject.open(path)
    original = path.read_bytes()
    project.shots[-1].scene = "different place"
    project.save(path)
    changed = path.read_bytes()
    with pytest.raises(ValueError, match="已经变化"):
        queue.apply_group_text("EP01", "SB01", "prompt", expected=preview)
    assert path.read_bytes() == changed and all(r["status"] == "review" for r in queue.jobs())
    path.write_bytes(original)
    with pytest.raises(ValueError):
        queue.apply_group_text("EP01", "SB01", "prompt", expected=preview + "another")
    assert queue.apply_group_text("EP01", "SB01", "prompt", expected=preview) == len(project.shots)
    assert all(s.fields["成片动作"] == "等待信号" for s in ProductionProject.open(path).shots)
    assert all(r["status"] == "approved" for r in queue.jobs())


def test_rate_limit_pauses_remaining_text_requests_even_with_budget_left(workspace, monkeypatch):
    workspace.approve_plan("EP01")
    q = BatchQueue(workspace)
    q.enqueue("EP01", ("prompt",))
    def limited(*args):
        raise ValueError("文本服务返回 HTTP 429。")
    monkeypatch.setattr(batch_runner, "request_text", limited)
    q.run(TEXT_SETTINGS, max_requests=50)
    assert q.spent() == 1 and q.jobs()[0]["status"] == "failed"
    assert all(row["status"] == "blocked" for row in q.jobs()[1:])


def test_auto_polling_completes_async_image_without_resubmission(workspace, monkeypatch):
    workspace.approve_plan("EP01")
    q = BatchQueue(workspace)
    q.enqueue_asset("EP01", "SB01", "场景", "控制室", "夜景", "窗外为夜景")
    name = "腾讯云混元"
    preset = IMAGE_PROVIDERS[name]
    settings = ImageSettings(name, preset.base, preset.model, "test-key", "test-secret-id")
    monkeypatch.setattr(batch_runner, "submit_image", lambda *_: ImageReply(task_id="existing", status="queued"))
    replies = iter([ImageReply(task_id="existing", status="queued"), ImageReply((png(),), task_id="existing")])
    monkeypatch.setattr(batch_runner, "query_image", lambda *_: next(replies))
    assert q.run(image_settings=settings, max_requests=1, poll_rounds=5, poll_interval=0) == {"review": 1}
    assert q.spent() == 1


def test_request_limit_survives_reopen_separately_from_spend(workspace):
    queue = BatchQueue(workspace)
    assert queue.request_limit() == 10
    queue.run(max_requests=1)
    assert BatchQueue(BatchWorkspace.open(workspace.path)).request_limit() == 1
    assert queue.spent() == 0
    queue.run(max_requests=0)
    assert BatchQueue(workspace).request_limit() == 0


def test_short_regular_group_blocks_visual_spend_but_other_groups_and_assets_run(workspace, monkeypatch):
    shots = workspace.plan_for("EP01")["shots"]
    workspace.regroup("EP01", [[s["id"]] for s in shots])
    plan = workspace.plan_for("EP01")
    assert plan["groups"][0]["planning_note"]
    assert not plan["groups"][-1]["planning_note"]
    workspace.approve_plan("EP01")
    queue = BatchQueue(workspace)
    queue.enqueue("EP01", ("board", "plate"))
    asset = queue.enqueue_asset("EP01", "SB01", "角色", "Vera", "normal", "coat")
    monkeypatch.setattr(batch_runner, "submit_image", lambda *_: ImageReply((png(),)))
    queue.run(image_settings=IMAGE_SETTINGS, max_requests=20)
    rows = queue.jobs()
    paused = [r for r in rows if r["group_id"] == "SB01" and r["kind"] in {"board", "plate"}]
    assert len(paused) == 2
    assert all(r["status"] == "blocked" and r["attempts"] == 0 and "调整组界" in r["message"] for r in paused)
    assert queue._job(asset)["status"] == "review"
    assert any(r["group_id"] == "SB02" and r["kind"] == "board" and r["status"] == "review" for r in rows)


def test_duplicate_shot_candidates_cannot_change_project_or_approve_jobs(workspace, monkeypatch):
    workspace.approve_plan("EP01")
    queue = BatchQueue(workspace)
    jobs = queue.enqueue("EP01", ("shot",))
    assert jobs > 1

    def transport(settings, instructions, body):
        line = int(next(iter(json.loads(body)["approved_source"]["lines"])))
        return TextReply(json.dumps({"shots": [{"line_start": line, "line_end": line,
                                               "fields": {"景别": "中景", "机位/角度": "正面"}}]}))

    monkeypatch.setattr(batch_runner, "request_text", transport)
    queue.run(TEXT_SETTINGS, max_requests=jobs)
    path = workspace.group_path("EP01", "SB01")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="SB01-01 → SB01-02"):
        queue.apply_group_text("EP01", "SB01", "shot")
    assert path.read_bytes() == before
    assert all(row["status"] == "review" for row in queue.jobs())
