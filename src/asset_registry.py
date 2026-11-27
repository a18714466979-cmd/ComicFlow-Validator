"""Local, versioned fingerprints of user-approved production assets."""

import hashlib
import os
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class Asset:
    identifier: str
    version: str
    origin: str
    sha256: str
    size: int
    location: str


class AssetRegistry:
    def __init__(self, path: Path, *, create: bool = False):
        self.path = path.expanduser().resolve()
        if not create and not self.path.is_file():
            raise ValueError("找不到本地资产登记库。")
        if create:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("""CREATE TABLE IF NOT EXISTS assets (
                           identifier TEXT NOT NULL, version TEXT NOT NULL, origin TEXT NOT NULL,
                           sha256 TEXT NOT NULL, size INTEGER NOT NULL, location TEXT NOT NULL,
                           PRIMARY KEY (identifier, version)
                           )""")

    def records(self) -> list[Asset]:
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
            return [Asset(*row) for row in db.execute("SELECT * FROM assets ORDER BY identifier, version")]

    def register(self, path: Path, identifier: str, version: str, origin: str = "") -> Asset:
        identifier, version = identifier.strip(), version.strip()
        if not identifier or not version or any(char in identifier + version + origin for char in "\r\n\x00"):
            raise ValueError("请填写单行资产 ID 和版本号。")
        path = path.expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("请选择批准的原始文件。")
        before = path.stat()
        digest = sha256_file(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("登记期间原图发生变化，请重新登记。")
        asset = Asset(identifier, version, origin.strip() or str(path), digest, after.st_size, str(path))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM assets WHERE identifier=? AND version=?", (identifier, version)).fetchone()
            if previous and (previous[2], previous[3]) != (asset.origin, asset.sha256):
                raise ValueError("此资产版本已有批准来源和指纹，请使用新版本号。")
            db.execute("INSERT OR REPLACE INTO assets VALUES (?, ?, ?, ?, ?, ?)", (
                asset.identifier, asset.version, asset.origin, asset.sha256, asset.size, asset.location,
            ))
        return asset

    def recover(self, folder: Path) -> dict[Asset, Path]:
        if not folder.is_dir():
            raise ValueError("请选择原图所在目录。")
        by_size = {}
        for asset in self.records():
            by_size.setdefault(asset.size, {}).setdefault(asset.sha256, []).append(asset)
        if not by_size:
            return {}
        recovered = {}
        for root, dirs, files in os.walk(folder, followlinks=False):
            dirs.sort()
            for name in sorted(files):
                path = Path(root, name)
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    fingerprints = by_size.get(path.stat().st_size)
                    if fingerprints:
                        for asset in fingerprints.get(sha256_file(path), ()):
                            recovered.setdefault(asset, path.resolve())
                except OSError:
                    continue
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany("UPDATE assets SET location=? WHERE identifier=? AND version=? AND sha256=?", (
                (str(path), asset.identifier, asset.version, asset.sha256) for asset, path in recovered.items()
            ))
        return recovered


def check_package_assets(folder: Path, registry: AssetRegistry | None) -> tuple[set[str], list[str]]:
    """Verify registered references and return the exact missing-path diagnostics resolved."""
    by_reference = defaultdict(set)
    for asset in registry.records() if registry else ():
        by_reference[asset.origin].add(asset)
        by_reference[f"asset:{asset.identifier}@{asset.version}"].add(asset)
    resolved, blocked, errors = set(), set(), []
    verified_files = {}
    for group in sorted(folder.glob("SB*")):
        if not group.is_dir():
            continue
        for record in sorted(group.glob("*_shot_details.txt")):
            content = record.read_text(encoding="utf-8-sig")
            ledger = re.search(r"^资产复用核对[ \t]*[：:][ \t]*\n((?:[ \t]*[-*•].*\n?)*)", content, re.MULTILINE)
            if not ledger:
                continue
            for line in ledger[1].splitlines():
                fields = [part.strip() for part in line.strip()[1:].split("|")]
                if len(fields) != 4:
                    continue
                filename, action, references, _ = fields
                for origin in (item.strip() for item in re.split(r"[；;]", references)):
                    matches = by_reference[origin]
                    if not matches and not origin.startswith("asset:"):
                        continue
                    diagnostic = f"ERROR: {group.name}: 资产复用核对 approved local source is missing: {origin}"
                    problem = None
                    if len(matches) != 1:
                        problem = "登记的原图版本缺失或不唯一"
                    else:
                        asset = next(iter(matches))
                        if asset not in verified_files:
                            try:
                                verified_files[asset] = sha256_file(Path(asset.location)) == asset.sha256
                            except OSError:
                                verified_files[asset] = False
                        if not verified_files[asset]:
                            problem = "登记的原图未找到，或其 SHA-256 不匹配"
                        elif action == "直接复用" and Path(filename).name == filename and (group / filename).is_file():
                            if sha256_file(group / filename) != asset.sha256:
                                problem = "直接复用的交付文件与批准原图 SHA-256 不匹配"

                    if problem:
                        errors.append(f"ERROR: {group.name}/{filename}: {problem}（{origin}）")
                        blocked.add(diagnostic)
                    else:
                        resolved.add(diagnostic)
    return resolved - blocked, errors
