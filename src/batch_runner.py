"""Persistent candidate-generation queue for reviewed episode plans.

Only explicitly started jobs contact a provider. A process lock covers submission
and reconciliation, while SQLite commits each reservation before any HTTP call.
"""

import json
import os
import re
import sqlite3
from collections import Counter
from contextlib import closing, contextmanager
from hashlib import sha256
from threading import Event

from .batch_ai_adapter import (
    ASSET_KINDS, IMAGE_KINDS, TEXT_KINDS, apply_fields, check_neighbor_cameras, prepare_image, prepare_text, text_result,
)
from .camera_preflight import require_camera_rules
from .image_api import ImageRequestError, query_image, submit_image
from .production_images import store_reply, storyboard_job_page
from .production_project import ProductionProject
from .text_api import request_text


@contextmanager
def _worker_lock(path):
    with path.open("a+b") as stream:
        if not stream.seek(0, os.SEEK_END):
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("批量队列正在运行，请等待当前任务结束。") from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class BatchQueue:
    def __init__(self, workspace):
        self.workspace = workspace
        self.database = workspace.root / "batch-queue.sqlite3"
        self.lock_path = workspace.root / "batch-runner.lock"
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, episode TEXT NOT NULL, group_id TEXT NOT NULL, project_ref TEXT NOT NULL,
                kind TEXT NOT NULL, shot_id TEXT NOT NULL, spec TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                message TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0, candidate TEXT NOT NULL DEFAULT '{}'
            )""")
            db.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)")

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.database, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def jobs(self):
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY rowid")]

    def request_limit(self):
        with self._db() as db:
            limit = db.execute("SELECT value FROM settings WHERE name='request_limit'").fetchone()
        return int(limit[0]) if limit is not None else 10

    def spent(self):
        with self._db() as db:
            return db.execute("SELECT coalesce(sum(attempts),0) FROM jobs").fetchone()[0]

    def _set(self, identity, status, message="", candidate=None):
        with self._db() as db:
            if candidate is None:
                db.execute("UPDATE jobs SET status=?,message=? WHERE id=?", (status, message, identity))
            else:
                db.execute("UPDATE jobs SET status=?,message=?,candidate=? WHERE id=?",
                           (status, message, json.dumps(candidate, ensure_ascii=False), identity))

    def _insert(self, db, episode, group, path, kind, shot_id, spec=None):
        ref = path.relative_to(self.workspace.root).as_posix()
        payload = json.dumps(spec or {}, ensure_ascii=False, sort_keys=True)
        identity = sha256(json.dumps([episode, group, ref, kind, shot_id, payload]).encode()).hexdigest()
        added = db.execute("""INSERT OR IGNORE INTO jobs
            (id,episode,group_id,project_ref,kind,shot_id,spec) VALUES (?,?,?,?,?,?,?)""",
                           (identity, episode, group, ref, kind, shot_id, payload)).rowcount
        return identity, added

    def enqueue(self, episode_id, kinds=("shot", "prompt", "board", "plate"), *, group=None):
        if not kinds or set(kinds) - {"shot", "prompt", "board", "plate"}:
            raise ValueError("请选择分镜、提示词、故事板或净板任务。")
        paths = ([self.workspace.group_path(episode_id, group)] if group else self.workspace.group_paths(episode_id))
        added = 0
        with self._db() as db:
            for path in paths:
                project = ProductionProject.open(path)
                for kind in ("shot", "prompt", "board", "plate"):
                    if kind not in kinds:
                        continue
                    seen_pages = set()
                    for shot in project.shots:
                        if kind == "board":
                            page = storyboard_job_page(project, shot.id)
                            if page in seen_pages:
                                continue
                            seen_pages.add(page)
                        _, count = self._insert(db, episode_id, project.group, path, kind, shot.id)
                        added += count
        return added

    def enqueue_asset(self, episode_id, group, kind, title, state, brief):
        kind = {"道具": "道具 / HUD", "服装": "角色"}.get(kind, kind)
        if kind not in ASSET_KINDS or not all(value.strip() for value in (title, state, brief)):
            raise ValueError("请填写参考图类型、身份、状态和批准描述。")
        spec = {"kind": kind, "title": title.strip(), "state": state.strip(), "brief": brief.strip()}
        path = self.workspace.group_path(episode_id, group)
        with self._db() as db:
            identity, _ = self._insert(db, episode_id, group, path, "asset", "", spec)
        return identity

    def _job(self, identity):
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ValueError("找不到所选任务。")
        return dict(row)

    def _project(self, row):
        path = self.workspace.group_path(row["episode"], row["group_id"])
        if path.relative_to(self.workspace.root).as_posix() != row["project_ref"]:
            raise ValueError("分组版本已变更。请为当前分组重新加入任务。")
        return path, ProductionProject.open(path)

    def _dependencies(self, row):
        if not self.workspace.plan_approved(row["episode"]):
            raise ValueError("请确认本集分组计划，再提交模型请求。")
        if row["kind"] in {"board", "plate"}:
            plan = self.workspace.plan_for(row["episode"])
            group = next(item for item in plan["groups"] if item["group"] == row["group_id"])
            if group.get("planning_note"):
                raise ValueError(f"{row['group_id']} 暂停制图。{group['planning_note']} 请在整集规划中拆分源段或调整组界后重新加入队列。")
        if row["kind"] in {"prompt", "board"}:
            with self._db() as db:
                rows = db.execute("SELECT kind,shot_id,status FROM jobs WHERE project_ref=? AND kind IN ('shot','prompt')",
                                  (row["project_ref"],)).fetchall()
            if row["kind"] == "board":
                if any(item["status"] != "approved" for item in rows):
                    raise ValueError("请先采纳本组已排队的镜头文字，再生成故事板。")
                gaps = self.workspace.resolve_required_assets(row["episode"], row["group_id"])
                if gaps:
                    raise ValueError("本组正在等待指定的批准资产：" + "、".join(gaps))
            elif any(item["kind"] == "shot" and item["shot_id"] == row["shot_id"]
                     and item["status"] != "approved" for item in rows):
                raise ValueError("请先核对并采纳相关镜头的分镜候选。")

    def _reserve(self, row, limit):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT coalesce(sum(attempts),0) FROM jobs").fetchone()[0]
            if spent >= limit:
                return False
            db.execute("UPDATE jobs SET status='running',attempts=attempts+1,message='' WHERE id=?", (row["id"],))
        return True

    def _sync_image(self, row):
        candidate = json.loads(row["candidate"])
        path, project = self._project(row)
        job = candidate["image"]
        existing = next((item for item in project.image_jobs if item["id"] == job["id"]), None)
        if existing and existing["status"] == "approved":
            message = "单组项目已批准图像。"
            if row["kind"] == "asset":
                image = next((item for item in project.images if item.id == existing.get("approved_image")), None)
                if image is None:
                    raise ValueError("批准的图像已移除，请核对组项目。")
                spec = json.loads(row["spec"])
                self.workspace.approve_asset(spec["title"], spec["state"], image.version,
                                            project.checked_image(path, image), image.inspection, filename=image.filename)
                message = "已登记共享资产：" + " · ".join((spec["title"], spec["state"], image.version))
            self._set(row["id"], "approved", message)
            return
        if existing and existing["status"] == "closed":
            self._set(row["id"], "failed", "候选已在单组项目关闭。")
            return
        if existing is None:
            project.image_jobs.append(job)
            project.save(path)
        elif existing.get("status") == "queued" and job.get("status") != "queued":
            existing.update(job)
            project.save(path)
        elif existing.get("status") in {"ready", "failed"}:
            job = existing
        candidate["image"] = job
        status = {"queued": "polling", "ready": "review", "failed": "failed"}.get(job["status"], "uncertain")
        self._set(row["id"], status, {"polling": "已提交，可查询原服务商任务号。",
                                      "review": "请在单组生图窗口查看并批准候选。",
                                      "failed": "服务商未完成此次任务。"}.get(status, "请核对服务端结果。"), candidate)

    def _record_image(self, row, path, job, result):
        store_reply(path, job, result)
        self._set(row["id"], "recorded", candidate={"image": job})
        self._sync_image(self._job(row["id"]))

    def _submit(self, row, text_settings, image_settings, limit):
        # Resolve explicit shared-asset requirements first, then reopen the
        # group to build requests against its newly bound local references.
        self._project(row)
        self._dependencies(row)
        path, project = self._project(row)
        is_text = row["kind"] in TEXT_KINDS
        settings = text_settings if is_text else image_settings
        if settings is None:
            raise ValueError("请在 API 接入页保存本次文本／生图设置。")
        if is_text:
            plan = self.workspace.plan_for(row["episode"])
            task, context, instructions, body = prepare_text(project, plan, row, settings)
        else:
            job, request = prepare_image(self.workspace, project, path, row, settings, json.loads(row["spec"]))
        if not self._reserve(row, limit):
            self._set(row["id"], "blocked", "已到本批累计 API 请求上限。")
            return
        try:
            if is_text:
                reply = request_text(settings, instructions, body)
                try:
                    candidate = text_result(task, context, reply, settings)
                except ValueError as error:
                    self._set(row["id"], "failed", str(error))
                    return
                self._set(row["id"], "review", "请预览并采纳候选。", candidate)
            else:
                reply = submit_image(settings, request)
                self._record_image(row, path, job, reply)
        except (OSError, ValueError, RuntimeError) as error:
            if self._job(row["id"])["status"] == "recorded":
                return  # The response is durable; a later run can finish the local write.
            hint = str(error) if isinstance(error, ValueError) else type(error).__name__
            response = re.search(r"HTTP (\d{3})", hint)
            rejected = bool(response and response[1] in {"400", "401", "403", "404", "413", "429"})
            certain = rejected or (isinstance(error, ImageRequestError) and not error.uncertain)
            request_id = getattr(error, "request_id", "")
            self._set(row["id"], "failed" if certain else "uncertain", hint, {"request_id": request_id})
            return (not certain or bool(response and response[1] in {"401", "403", "429"}))

    def _poll(self, row, settings):
        candidate = json.loads(row["candidate"])
        job = candidate["image"]
        if not settings or (settings.provider, settings.base.rstrip("/"), settings.model) != (
                job["provider"], job["base"], job["model"]):
            self._set(row["id"], "polling", "查询需使用原服务商、地址和模型。")
            return
        path, _ = self._project(row)
        result = query_image(settings, job["task_id"])
        self._record_image(row, path, job, result)

    def run(self, text_settings=None, image_settings=None, *, max_requests, stop=None,
            poll_rounds=0, poll_interval=5):
        if type(max_requests) is not int or max_requests < 0:
            raise ValueError("请求上限必须是非负整数。")
        stop = stop if stop is not None else Event()
        paused_connections = set()
        with _worker_lock(self.lock_path):
            with self._db() as db:
                db.execute("INSERT OR REPLACE INTO settings (name,value) VALUES ('request_limit',?)", (str(max_requests),))
                db.execute("""UPDATE jobs SET status='uncertain',message='上次提交被中断，请先核对服务商用量。'
                           WHERE status='running'""")
            # Reconcile visual approvals before checking dependencies in other groups.
            snapshot = self.jobs()
            snapshot.sort(key=lambda row: row["status"] in {"queued", "blocked"})
            for row in snapshot:
                if stop.is_set():
                    break
                status = row["status"]
                try:
                    if row["kind"] in IMAGE_KINDS and status in {"recorded", "review", "polling"}:
                        self._sync_image(row)
                        if status == "polling" and self._job(row["id"])["status"] == "polling":
                            self._poll(row, image_settings)
                    elif status in {"queued", "blocked"}:
                        connection = "text" if row["kind"] in TEXT_KINDS else "image"
                        if connection in paused_connections:
                            self._set(row["id"], "blocked", "本轮同类 API 已暂停，请核对服务商状态后继续。")
                        elif self._submit(row, text_settings, image_settings, max_requests):
                            paused_connections.add(connection)
                except (OSError, ValueError, RuntimeError) as error:
                    # No remote submit outside _submit's reservation. Polling the same
                    # provider task can safely be repeated even if a query timed out.
                    current = self._job(row["id"])["status"]
                    self._set(row["id"], "blocked" if current in ("queued", "blocked") else current, str(error))
            if image_settings is not None:
                for _ in range(poll_rounds):
                    pending = [row for row in self.jobs() if row["status"] == "polling"]
                    if not pending or stop.wait(poll_interval):
                        break
                    for row in pending:
                        if stop.is_set():
                            break
                        try:
                            self._poll(row, image_settings)
                        except (OSError, ValueError, RuntimeError) as error:
                            current = self._job(row["id"])["status"]
                            self._set(row["id"], current, str(error))
        return dict(Counter(row["status"] for row in self.jobs()))

    def retry(self, job_id, *, confirmed=False):
        with _worker_lock(self.lock_path):
            row = self._job(job_id)
            if row["status"] not in {"failed", "uncertain", "blocked", "review"}:
                raise ValueError("此任务当前不可重新提交。")
            if row["status"] in {"uncertain", "review"} and not confirmed:
                raise ValueError("请先核对服务商用量并明确确认再次提交。")
            self._project(row)
            self._set(job_id, "queued", candidate={})

    def candidate_text(self, job_id):
        row = self._job(job_id)
        candidate = json.loads(row["candidate"])
        return json.dumps(candidate.get("output", {}), ensure_ascii=False, indent=2) if "output" in candidate else ""

    def _group_candidates(self, episode, group, kind):
        if kind not in TEXT_KINDS:
            raise ValueError("请选择分镜或提示词候选。")
        path = self.workspace.group_path(episode, group)
        project = ProductionProject.open(path)
        ref = path.relative_to(self.workspace.root).as_posix()
        with self._db() as db:
            rows = db.execute("""SELECT * FROM jobs WHERE project_ref=? AND kind=? AND status='review'""",
                              (ref, kind))
            by_shot = {row["shot_id"]: dict(row) for row in rows}
        return project, path, [by_shot[shot.id] for shot in project.shots if shot.id in by_shot]

    @staticmethod
    def _preview(project, rows):
        slot = {shot.id: index for index, shot in enumerate(project.shots, 1)}
        blocks = []
        for row in rows:
            cand = json.loads(row["candidate"])
            fields = cand["output"]["prompt"] if row["kind"] == "prompt" else cand["output"]["shots"][0]["fields"]
            heading = f"{row['episode']} · {row['group_id']}-{slot[row['shot_id']]:02d}"
            blocks.append(heading + "\n" + "\n".join(f"{key} · {value}" for key, value in fields.items()))
        return "\n\n".join(blocks)

    def group_preview(self, episode_id, group_id, kind):
        project, _, rows = self._group_candidates(episode_id, group_id, kind)
        return self._preview(project, rows)

    def _adopt(self, project, path, rows):
        plan = self.workspace.plan_for(rows[0]["episode"])
        adopted = {item["id"] for item in project.text_drafts}
        updates = []
        for row in rows:
            candidate = json.loads(row["candidate"])
            if candidate["id"] in adopted:
                continue
            _, context, _, _ = prepare_text(project, plan, row, None,
                                            include_neighbors=candidate["context"].get("camera_neighbors", False))
            if candidate["context"]["fingerprint"] != context["fingerprint"]:
                raise ValueError(f"源段或镜头已经变化，请核对后重新生成 {row['group_id']} 候选。")
            updates.append((row, candidate))
        for row, candidate in updates:
            apply_fields(project, row, candidate)
            project.text_drafts.append({**candidate, "batch": True})
        if updates:
            if rows[0]["kind"] == "shot":
                require_camera_rules(project)
                check_neighbor_cameras(self.workspace, rows[0]["episode"], project)
            project.save(path)
        with self._db() as db:
            db.executemany("UPDATE jobs SET status='approved',message='已将候选采纳到原镜头。' WHERE id=?",
                           ((row["id"],) for row in rows))
        return len(rows)

    def apply_group_text(self, episode_id, group_id, kind, *, expected=None):
        with _worker_lock(self.lock_path):
            project, path, rows = self._group_candidates(episode_id, group_id, kind)
            if not rows or expected is not None and self._preview(project, rows) != expected:
                raise ValueError("候选已变化或尚无待审文字，请重新预览。")
            return self._adopt(project, path, rows)

    def apply_text(self, job_id):
        with _worker_lock(self.lock_path):
            row = self._job(job_id)
            if row["kind"] not in TEXT_KINDS or row["status"] != "review":
                raise ValueError("请选择待采纳的文本候选。")
            path, project = self._project(row)
            self._adopt(project, path, [row])
