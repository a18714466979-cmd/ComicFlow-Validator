"""Portable episode plans, editable group projects, and approved shared image states."""

import json
import re
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from shutil import copyfile, rmtree
from tempfile import NamedTemporaryFile
from uuid import uuid4

from PIL import Image

from . import batch_planning
from .asset_registry import sha256_file
from .production_project import ProductionProject, checked_name
from .production_rules import RULE_LABELS


FORMAT = "comicflow-production-batch"
VERSION = 1


@dataclass(frozen=True)
class BatchEpisode:
    id: str
    title: str


@dataclass(frozen=True)
class BatchAsset:
    identity: str
    state: str
    version: str
    digest: str
    filename: str
    inspection: str
    id: str



@dataclass(frozen=True)
class AssetRequirement:
    identity: str
    state: str
    version: str
    deliver: bool

def _label(value, kind):
    if not isinstance(value, str) or not value.strip() or any(ch in value for ch in "|\r\n\x00"):
        raise ValueError(f"请填写单行{kind}。")
    return value.strip()


def _episode_id(value):
    match = re.fullmatch(r"(?:EP)?([0-9]+)", str(value).strip(), re.I)
    if not match or len(match[1]) > 8 or int(match[1]) < 1:
        raise ValueError("请使用 EP01、EP02 这类集号。")
    return f"EP{int(match[1]):02d}"


def _filename_id(stem):
    match = re.search(r"(?<![A-Za-z0-9])EP(?:ISODE)?[ _-]*([0-9]+)(?![0-9])", stem, re.I)
    if match:
        return _episode_id(match[1])
    match = re.search(r"第\s*([0-9]+|[零〇一二两三四五六七八九十百千]+)\s*集", stem)
    if not match:
        return ""
    number = match[1]
    if number.isascii():
        return _episode_id(number)
    digits = dict(zip("零一二三四五六七八九", range(10)), 〇=0, 两=2)
    units = {"十": 10, "百": 100, "千": 1000}
    if not any(char in units for char in number):
        return _episode_id("".join(str(digits[char]) for char in number))
    total = current = 0
    for char in number:
        if char in units:
            total += (current or 1) * units[char]
            current = 0
        else:
            current = digits[char]
    return _episode_id(total + current)


def _row(db, episode):
    row = db.execute("SELECT * FROM episodes WHERE id=?", (_episode_id(episode),)).fetchone()
    if row is None:
        raise ValueError(f"批次中没有该集：{episode}")
    return row


class BatchWorkspace:
    def __init__(self, path, title, rules):
        self.path = Path(path).resolve()
        self.root = self.path.with_suffix(".batch")
        self.title = title
        self.rules = rules

    @classmethod
    def create(cls, path, title, rules):
        path = Path(path)
        if path.suffix.lower() != ".cfbatch":
            raise ValueError("请选择 .cfbatch 批量项目文件。")
        if rules not in RULE_LABELS:
            raise ValueError("请选择中文影片制作或英文影片制作。")
        workspace = cls(path, _label(title, "批次名称"), rules)
        if workspace.path.exists() or workspace.root.exists():
            raise ValueError("此批量项目或同名数据目录已存在，请打开已有项目或更换名称。")
        workspace.root.mkdir()
        batch_id = uuid4().hex
        try:
            with closing(sqlite3.connect(workspace.root / "index.sqlite3")) as db, db:
                db.executescript("""
                    CREATE TABLE batch (id TEXT PRIMARY KEY, title TEXT NOT NULL, rules TEXT NOT NULL);
                    CREATE TABLE episodes (
                        id TEXT PRIMARY KEY, title TEXT NOT NULL, position INTEGER UNIQUE NOT NULL,
                        plan TEXT NOT NULL, generation TEXT NOT NULL, originals TEXT NOT NULL, approved INTEGER NOT NULL);
                    CREATE TABLE requirements (
                        episode TEXT NOT NULL, generation TEXT NOT NULL, grp TEXT NOT NULL,
                        identity TEXT NOT NULL, state TEXT NOT NULL, version TEXT NOT NULL, deliver INTEGER NOT NULL,
                        PRIMARY KEY(episode, generation, grp, identity, state, version));
                    CREATE TABLE assets (
                        identity TEXT NOT NULL, state TEXT NOT NULL, version TEXT NOT NULL,
                        digest TEXT NOT NULL, filename TEXT NOT NULL, inspection TEXT NOT NULL, id TEXT UNIQUE NOT NULL,
                        PRIMARY KEY(identity, state, version));
                """)
                db.execute("INSERT INTO batch VALUES (?, ?, ?)", (batch_id, workspace.title, rules))
            (workspace.root / "episodes").mkdir()
            (workspace.root / "images").mkdir()
            payload = json.dumps({"format": FORMAT, "version": VERSION, "id": batch_id}, indent=2)
            with workspace.path.open("x", encoding="utf-8") as stream:
                stream.write(payload + "\n")
        except BaseException:
            rmtree(workspace.root, ignore_errors=True)
            raise
        return workspace

    @classmethod
    def open(cls, path):
        path = Path(path).resolve()
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if (not isinstance(payload, dict) or payload.get("format") != FORMAT or payload.get("version") != VERSION
                or not re.fullmatch("[0-9a-f]{32}", str(payload.get("id", "")))):
            raise ValueError("不支持的批量项目格式。")
        root = path.with_suffix(".batch")
        with closing(cls.connect(root)) as db:
            row = db.execute("SELECT * FROM batch WHERE id=?", (payload["id"],)).fetchone()
        if row is None or row["rules"] not in RULE_LABELS:
            raise ValueError("批量项目与同名数据目录不匹配。")
        return cls(path, row["title"], row["rules"])

    @staticmethod
    def connect(root):
        database = root / "index.sqlite3"
        if not database.is_file():
            raise ValueError("找不到批量项目数据，请让 .cfbatch 文件与同名 .batch 文件夹放在一起。")
        db = sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def writing(self):
        # SQLite releases this writer lock if the app exits mid-operation.
        with closing(self.connect(self.root)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    @property
    def episodes(self):
        with closing(self.connect(self.root)) as db:
            return [BatchEpisode(*row) for row in db.execute("SELECT id, title FROM episodes ORDER BY position")]

    def plan_for(self, episode):
        with closing(self.connect(self.root)) as db:
            return json.loads(_row(db, episode)["plan"])

    def source_text(self, episode):
        return self.plan_for(episode)["source_text"]

    def plan_approved(self, episode):
        with closing(self.connect(self.root)) as db:
            return bool(_row(db, episode)["approved"])

    def approve_plan(self, episode):
        with self.writing() as db:
            row = _row(db, episode)
            issues = json.loads(row["plan"])["issues"]
            if issues:
                raise ValueError("\n".join(issues))
            db.execute("UPDATE episodes SET approved=1 WHERE id=?", (row["id"],))

    def _folder(self, episode, generation):
        if not re.fullmatch("[0-9a-f]{32}", generation):
            raise ValueError("分组项目目录记录无效。")
        return self.root / "episodes" / _episode_id(episode) / generation

    def _paths(self, row):
        folder = self._folder(row["id"], row["generation"])
        paths = []
        for group in json.loads(row["plan"])["groups"]:
            name = group["group"]
            if not re.fullmatch(r"SB[0-9]{2,}", name):
                raise ValueError("分组编号无效。")
            paths.append(folder / f"{name}.cfproject")
        return paths

    def group_paths(self, episode):
        with closing(self.connect(self.root)) as db:
            return self._paths(_row(db, episode))

    def group_path(self, episode, group):
        for path in self.group_paths(episode):
            if group == path.stem:
                return path
        raise ValueError(f"此集没有分组 {group}。")

    def _materialize(self, db, episode, title, plan, position):
        generation = uuid4().hex
        folder = self._folder(episode, generation)
        folder.mkdir(parents=True)
        originals = {}
        try:
            for group in plan["groups"]:
                name = group["group"]
                if not re.fullmatch(r"SB[0-9]{2,}", name):
                    raise ValueError("分组编号无效。")
                path = folder / f"{name}.cfproject"
                batch_planning.materialize_group(plan, name).save(path)
                originals[name] = sha256_file(path)
            db.execute("""
                INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET plan=excluded.plan, generation=excluded.generation,
                    originals=excluded.originals, approved=0
                """, (episode, title, position, json.dumps(plan, ensure_ascii=False), generation, json.dumps(originals)))
        except BaseException:
            rmtree(folder, ignore_errors=True)
            raise
        return folder

    def _add(self, db, episode, title, text, position, created, source_name):
        episode = _episode_id(episode)
        title = _label(title, "集标题")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{title} 的剧本没有正文。")
        if db.execute("SELECT 1 FROM episodes WHERE id=?", (episode,)).fetchone():
            raise ValueError(f"{episode} 已存在；请选择新的集号。")
        plan = batch_planning.plan_episode(self.title, episode, source_name, text, self.rules)
        created.append(self._materialize(db, episode, title, plan, position))
        return BatchEpisode(episode, title)

    def add_episode(self, episode_id, title, script_text):
        with self.writing() as db:
            position = db.execute("SELECT COALESCE(MAX(position),0)+1 FROM episodes").fetchone()[0]
            return self._add(db, episode_id, title, script_text, position, [], title)

    def add_scripts(self, paths):
        scripts = []
        for filename in paths:
            path = Path(filename)
            if path.suffix.lower() not in (".txt", ".md"):
                raise ValueError("请选择 UTF-8 TXT 或 Markdown 剧本。")
            try:
                text = path.read_bytes().decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError(f"请把 {path.name} 另存为 UTF-8 文本后再导入。") from exc
            scripts.append((path, text))
        if not scripts:
            return []
        created = []
        try:
            with self.writing() as db:
                used = {row[0] for row in db.execute("SELECT id FROM episodes")}
                position = db.execute("SELECT COALESCE(MAX(position),0) FROM episodes").fetchone()[0]
                cursor = max((int(episode[2:]) for episode in used), default=0) + 1
                requested = []
                for path, _ in scripts:
                    explicit = _filename_id(path.stem)
                    if explicit and (explicit in used or explicit in requested):
                        raise ValueError(f"{path.name} 的集号 {explicit} 已使用，请核对文件名。")
                    requested.append(explicit)
                used.update(requested)
                episodes = []
                for index, ((path, text), explicit) in enumerate(zip(scripts, requested), 1):
                    while _episode_id(cursor) in used:
                        cursor += 1
                    episode = explicit or _episode_id(cursor)
                    used.add(episode)
                    episodes.append(self._add(db, episode, path.stem, text, position+index, created, path.name))
            return episodes
        except BaseException:
            for folder in created:
                rmtree(folder, ignore_errors=True)
            raise

    def regroup(self, episode, groups):
        self._replan(episode, lambda plan: batch_planning.regroup(plan, groups))

    def split_passage(self, episode, passage_id, offsets):
        self._replan(episode, lambda plan: batch_planning.split_passage(plan, passage_id, offsets))

    def _replan(self, episode, change):
        with self.writing() as db:
            row = _row(db, episode)
            plan = json.loads(row["plan"])
            revised = change(plan)
            if revised == plan:
                return
            originals = json.loads(row["originals"])
            for path in self._paths(row):
                if not path.is_file() or sha256_file(path) != originals.get(path.stem):
                    raise ValueError(f"{path.stem} 已修改或缺失，已保留现有分组项目。")
            requirements = db.execute("""SELECT grp,identity,state,version,deliver FROM requirements
                                         WHERE episode=? AND generation=?""", (row["id"], row["generation"])).fetchall()
            old_groups = {g["group"]: tuple(g["shot_ids"]) for g in plan["groups"]}
            new_groups = {tuple(g["shot_ids"]): g["group"] for g in revised["groups"]}
            if any(old_groups[item["grp"]] not in new_groups for item in requirements):
                raise ValueError("需要重分的组已有指定资产依赖，请先核对并移除该组依赖，再重新划分。")
            # Switch all group paths together. Open editors may still hold the prior revision.
            folder = self._materialize(db, row["id"], row["title"], revised, row["position"])
            for item in requirements:
                target = new_groups[old_groups[item["grp"]]]
                db.execute("INSERT INTO requirements VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (row["id"], folder.name, target, item["identity"], item["state"], item["version"], item["deliver"]))

    def asset_inventory(self):
        with closing(self.connect(self.root)) as db:
            return [BatchAsset(*row) for row in db.execute("SELECT * FROM assets ORDER BY identity, state, version")]

    def approve_asset(self, identity, state, version, image_path, inspection, *, filename=None):
        identity, state = _label(identity, "资产身份"), _label(state, "资产状态")
        version, inspection = _label(version, "资产版本"), _label(inspection, "实际画面复核说明")
        if not re.fullmatch(r"[^@|；;\s]+", version):
            raise ValueError("资产版本请使用 R1、V2 等无空格标记。")
        image_path = Path(image_path)
        filename = checked_name(filename or image_path.name)
        if Path(filename).suffix.lower() != ".png" or image_path.suffix.lower() != ".png":
            raise ValueError("资产库接收经确认的 PNG 原图。")
        folder = self.root / "images"
        with NamedTemporaryFile(dir=folder, delete=False) as stream:
            staged = Path(stream.name)
        try:
            copyfile(image_path, staged)
            with Image.open(staged) as image:
                if image.format != "PNG" or image.width * image.height > 32_000_000:
                    raise ValueError("公共资产需要不超过 3200 万像素的 PNG 原图。")
                image.verify()
            with Image.open(staged) as image:
                image.load()
            digest = sha256_file(staged)
            if digest != sha256_file(image_path):
                raise ValueError("登记过程中原图发生变化，请重试。")
            with self.writing() as db:
                row = db.execute("SELECT * FROM assets WHERE identity=? AND state=? AND version=?",
                                 (identity, state, version)).fetchone()
                if row and row["digest"] != digest:
                    raise ValueError("该身份、状态和版本已经批准过另一张图。请使用新版本。")
                stored = folder / (digest + ".png")
                if not stored.exists() or sha256_file(stored) != digest:
                    staged.replace(stored)
                if row:
                    return BatchAsset(*row)
                asset = BatchAsset(identity, state, version, digest, filename, inspection, uuid4().hex)
                db.execute("INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (identity, state, version, digest, filename, inspection, asset.id))
                return asset
        finally:
            staged.unlink(missing_ok=True)

    def reuse_asset(self, episode, group, identity, state, version, *, deliver=False, filename=None):
        with self.writing() as db:
            row = _row(db, episode)
            path = next((p for p in self._paths(row) if p.stem == group), None)
            if path is None:
                raise ValueError("请选择当前集的分组。")
            found = db.execute("SELECT * FROM assets WHERE identity=? AND state=? AND version=?",
                               (identity, state, version)).fetchone()
            if found is None:
                raise ValueError("没有找到身份、状态和版本都相符的批准图。")
            asset = BatchAsset(*found)
            source = self.root / "images" / (asset.digest + ".png")
            if sha256_file(source) != asset.digest:
                raise ValueError("公共资产副本指纹已变化。")
            project = ProductionProject.open(path)
            origin = f"batch-asset:{asset.id}"
            chosen_name = checked_name(filename or asset.filename) if deliver else f"ref_{asset.id[:12]}.png"
            if not chosen_name.lower().endswith(".png"):
                raise ValueError("正式交付原图需要 .png 文件名。")
            for index, image in enumerate(project.images):
                if image.origin != origin:
                    continue
                if image.digest != asset.digest:
                    raise ValueError("组内已绑定不同指纹的版本。")
                project.checked_image(path, image)
                if deliver and image.reference_only:
                    image = replace(image, filename=chosen_name, reference_only=False)
                    project.images[index] = image
                    project.save(path)
                return image
            image = project.import_image(path, source, chosen_name, action="直接复用", reference_only=not deliver,
                                         reason=f"批准的 {identity} · {state}", inspection=asset.inspection,
                                         version=asset.version, origin_label=origin)
            project.save(path)
            return image

    def group_reference_ids(self, episode, group):
        path = self.group_path(episode, group)
        project = ProductionProject.open(path)
        assets = {"batch-asset:" + item.id: item for item in self.asset_inventory()}
        ids = []
        for image in project.images:
            asset = assets.get(image.origin)
            if asset is not None:
                if asset.digest != image.digest or asset.version != image.version:
                    raise ValueError(f"{image.filename} 与登记的批准资产版本不一致。")
                project.checked_image(path, image)
                ids.append(image.id)
        return ids

    def _requirement_scope(self, db, episode, group):
        row = _row(db, episode)
        if group not in {p.stem for p in self._paths(row)}:
            raise ValueError("请选择当前集的分组。")
        return row["id"], row["generation"], group

    def require_asset(self, episode, group, identity, state, version, *, deliver=False):
        identity, state = _label(identity, "资产身份"), _label(state, "资产状态")
        version = _label(version, "资产版本")
        if not re.fullmatch(r"[^@|；;\s]+", version):
            raise ValueError("资产版本请使用 R1、V2 等无空格标记。")
        with self.writing() as db:
            scope = self._requirement_scope(db, episode, group)
            db.execute("""
                INSERT INTO requirements VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(episode,generation,grp,identity,state,version) DO UPDATE SET deliver=excluded.deliver
                """, (*scope, identity, state, version, int(bool(deliver))))

    def remove_requirement(self, episode, group, identity, state, version):
        with self.writing() as db:
            scope = self._requirement_scope(db, episode, group)
            db.execute("""DELETE FROM requirements WHERE episode=? AND generation=? AND grp=?
                          AND identity=? AND state=? AND version=?""", (*scope, identity, state, version))

    def required_assets(self, episode, group):
        with closing(self.connect(self.root)) as db:
            scope = self._requirement_scope(db, episode, group)
            rows = db.execute("""SELECT identity,state,version,deliver FROM requirements
                                 WHERE episode=? AND generation=? AND grp=? ORDER BY identity,state,version""", scope)
            return [AssetRequirement(ident, state, version, bool(deliver)) for ident, state, version, deliver in rows]

    def required_asset_gaps(self, episode, group):
        requirements = self.required_assets(episode, group)
        if not requirements:
            return []
        path = self.group_path(episode, group)
        project = ProductionProject.open(path)
        pool = {(asset.identity, asset.state, asset.version): asset for asset in self.asset_inventory()}
        images = {item.origin: item for item in project.images}
        gaps = []
        for req in requirements:
            key = (req.identity, req.state, req.version)
            asset = pool.get(key)
            image = images.get("batch-asset:" + asset.id) if asset else None
            if not image or asset.digest != image.digest or image.version != req.version or (req.deliver and image.reference_only):
                gaps.append(" · ".join(key))
            else:
                project.checked_image(path, image)
        return gaps

    def resolve_required_assets(self, episode, group):
        requirements = self.required_assets(episode, group)
        if not requirements:
            return []
        available = {(asset.identity, asset.state, asset.version) for asset in self.asset_inventory()}
        for req in requirements:
            key = (req.identity, req.state, req.version)
            if key in available:
                self.reuse_asset(episode, group, *key, deliver=req.deliver)
        return self.required_asset_gaps(episode, group)

    @staticmethod
    def _asset_gaps(group, project, identities):
        linked = {identities.get(image.origin) for image in project.images}
        return [name for name in group["assets"] if name not in linked]

    def group_asset_gaps(self, episode, group_id):
        """Inferred candidates are separate from explicit, state-specific dependencies."""
        plan = self.plan_for(episode)
        path = self.group_path(episode, group_id)
        group = next(item for item in plan["groups"] if item["group"] == group_id)
        identities = {"batch-asset:" + asset.id: asset.identity for asset in self.asset_inventory()}
        return self._asset_gaps(group, ProductionProject.open(path), identities)

    def asset_gaps(self, episode):
        plan = self.plan_for(episode)
        paths = self.group_paths(episode)
        identities = {"batch-asset:" + asset.id: asset.identity for asset in self.asset_inventory()}
        missing = []
        for group, path in zip(plan["groups"], paths):
            missing.extend(self._asset_gaps(group, ProductionProject.open(path), identities))
        return list(dict.fromkeys(missing))
