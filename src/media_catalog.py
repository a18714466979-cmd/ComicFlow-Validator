"""Persist gallery metadata without editing production, batch or ecommerce source records."""

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import gettempdir
from threading import RLock
from uuid import uuid4

from .ecommerce_video import VIDEO_FILTER
from .production_project import atomic_text


IMAGE_FILTER = "*.png *.jpg *.jpeg *.webp *.gif *.bmp *.tif *.tiff"
MEDIA_FILTER = f"{IMAGE_FILTER} {VIDEO_FILTER}"
MEDIA_TYPES = {extension[1:]: kind for kind, pattern in (("image", IMAGE_FILTER), ("video", VIDEO_FILTER))
               for extension in pattern.split()}
CATEGORIES = ("scene", "character", "prop", "unclassified", "product", "storyboard", "clean_plate",
              "motion_reference")
CATEGORY_ALIASES = {
    "场景": "scene", "环境": "scene", "scene": "scene",
    "人物": "character", "角色": "character", "character": "character", "characters": "character",
    "道具": "prop", "prop": "prop", "props": "prop",
    "产品": "product", "product": "product",
    "storyboard": "storyboard", "board": "storyboard", "故事板": "storyboard",
    "clean_plate": "clean_plate", "plate": "clean_plate", "净板": "clean_plate",
    "motion_reference": "motion_reference", "动作参考": "motion_reference",
    "未分类": "unclassified", "待分类": "unclassified",
}
_PREFIX = re.compile(
    r"^(?:\d+[_ -])?(clean_plate|motion_reference|action_reference|other_characters|storyboard|protagonist|"
    r"characters?|props?|scene|plate|product|场景|人物|角色|道具|产品|故事板|净板|动作参考)(?:[_ -]|$)",
    re.I,
)
_FORMAT = "comic-sequence-studio.media-catalog@1"


class MediaCatalogError(ValueError):
    """The media index cannot be read or changed safely."""


def normalize_category(value: str) -> str:
    return CATEGORY_ALIASES.get(value.strip().casefold(), "unclassified") if isinstance(value, str) else "unclassified"


def category_for_filename(filename: str | Path) -> str:
    """Infer from reserved production names, never a guessed subject or extension."""
    stem = Path(filename).stem
    if match := _PREFIX.match(stem):
        label = match[1].lower()
        if label in ("protagonist", "other_characters"):
            return "character"
        if label == "action_reference":
            return "motion_reference"
        return normalize_category(label)
    return "unclassified"


def media_type_for_path(path: str | Path) -> str | None:
    return MEDIA_TYPES.get(Path(path).suffix.casefold())


@dataclass(frozen=True)
class MediaItem:
    key: str
    path: Path
    category: str = "unclassified"
    purpose: str = ""
    media_type: str = "image"
    name: str = ""
    expected_digest: str = ""

    @property
    def display_name(self) -> str:
        return self.name or self.path.name


def _blank():
    return {"format": _FORMAT, "linked": {}, "categories": {}, "posters": {}}


def _key(path: Path):
    return os.path.normcase(os.path.abspath(path))


def _absolute(path):
    return Path(os.path.abspath(Path(path).expanduser()))


@contextmanager
def _file_lock(path: Path):
    """Serialize the short read/replace window across windows and app processes."""
    identifier = hashlib.sha256(os.fsencode(_key(path))).hexdigest()
    with (Path(gettempdir()) / f"sequence-studio-media-{identifier}.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            if not stream.tell():
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX)
        yield


class MediaCatalog:
    def __init__(self, path: Path | None):
        self.path = _absolute(path) if path is not None else None
        self._state = _blank()
        self._gate = RLock()

    def _read(self):
        if self.path is None:
            return self._state
        try:
            value = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return _blank()
        except (OSError, ValueError) as exc:
            raise MediaCatalogError(f"无法读取素材库记录 / Cannot read the media catalog: {self.path.name}") from exc
        if (not isinstance(value, dict) or value.get("format") != _FORMAT
                or not all(isinstance(value.get(name), dict) for name in ("linked", "categories", "posters"))
                or not all(isinstance(path, str) and path and "\0" not in path
                           for path in value["linked"].values())
                or not all(item in CATEGORIES for item in value["categories"].values())
                or not all(type(time) is int and time >= 0 for time in value["posters"].values())):
            raise MediaCatalogError(f"素材库记录格式无效 / Invalid media catalog: {self.path.name}")
        return value

    def _write(self, state):
        if self.path is None:
            self._state = state
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_text(self.path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        except OSError as exc:
            raise MediaCatalogError(f"无法保存素材库记录 / Cannot save the media catalog: {self.path.name}") from exc

    @contextmanager
    def _locked(self):
        with self._gate:
            if self.path is None:
                yield
            else:
                with _file_lock(self.path):
                    yield

    def _resolve(self, value):
        path = Path(value)
        if path.is_absolute() or self.path is None:
            return path
        if path.drive or path.root or ".." in path.parts:
            raise MediaCatalogError(f"素材库相对路径无效 / Invalid relative media path: {value}")
        return self.path.parent / path

    def _store_path(self, path):
        if self.path is not None and path.is_relative_to(self.path.parent):
            return str(path.relative_to(self.path.parent))
        return str(path)

    def _linked(self, state):
        for key, value in state["linked"].items():
            path = self._resolve(value)
            media_type = media_type_for_path(path)
            if media_type is not None:
                yield MediaItem(key, path, category_for_filename(path), media_type=media_type)

    def items(self, native=()) -> tuple[MediaItem, ...]:
        with self._locked():
            state = self._read()
            records = {item.key: item for item in native}
            native_paths = {_key(item.path) for item in records.values()}
            records.update((item.key, item) for item in self._linked(state) if item.key not in records
                           and _key(item.path) not in native_paths)
            return tuple(replace(item, category=state["categories"].get(item.key, normalize_category(item.category)))
                         for item in records.values())

    def import_paths(self, paths, category="unclassified", *, stop=None) -> tuple[MediaItem, ...]:
        candidates = {}
        for candidate in paths:
            if stop is not None and stop.is_set():
                return ()
            path = _absolute(candidate)
            if media_type_for_path(path) is not None and path.is_file():
                candidates[_key(path)] = path
        if not candidates:
            return ()
        with self._locked():
            state = self._read()
            saved = dict(state["linked"])
            categories = dict(state["categories"])
            by_path = {_key(item.path): item.key for item in self._linked(state)}
            result = []
            for cache_key, path in candidates.items():
                if stop is not None and stop.is_set():
                    return ()
                key = by_path.get(cache_key) or f"import:{uuid4().hex}"
                saved[key] = self._store_path(path)
                selected = normalize_category(category)
                if selected != "unclassified":
                    categories[key] = selected
                new_category = categories.get(key, category_for_filename(path))
                result.append(MediaItem(key, path, new_category, media_type=media_type_for_path(path)))
            if stop is not None and stop.is_set():
                return ()
            if saved != state["linked"] or categories != state["categories"]:
                self._write({**state, "linked": saved, "categories": categories})
            return tuple(result)

    def categorize(self, keys, category):
        category = normalize_category(category)
        with self._locked():
            state = self._read()
            values = dict(state["categories"])
            values.update(dict.fromkeys(keys, category))
            if values != state["categories"]:
                self._write({**state, "categories": values})

    def set_poster(self, key, time_ms):
        if type(time_ms) is not int or time_ms < 0:
            raise ValueError("封面时间无效 / Invalid poster time.")
        with self._locked():
            state = self._read()
            if state["posters"].get(key) != time_ms:
                self._write({**state, "posters": {**state["posters"], key: time_ms}})

    def poster_time(self, key) -> int | None:
        with self._locked():
            return self._read()["posters"].get(key)

    def poster_times(self) -> dict[str, int]:
        with self._locked():
            return dict(self._read()["posters"])

    def relink(self, key, path):
        path = _absolute(path)
        with self._locked():
            state = self._read()
            previous = state["linked"].get(key)
            if previous is None:
                raise ValueError("请从原入口更新此素材 / Update this asset from its original import tool.")
            if not path.is_file() or media_type_for_path(path) != media_type_for_path(previous):
                raise ValueError("请选择相同媒体类型的文件 / Choose a file of the same media type.")
            if any(item.key != key and _key(item.path) == _key(path) for item in self._linked(state)):
                raise ValueError("此文件已在素材库中 / The file is already in the catalog.")
            posters = dict(state["posters"])
            posters.pop(key, None)
            self._write({**state, "linked": {**state["linked"], key: self._store_path(path)}, "posters": posters})

    def attach(self, path):
        path = _absolute(path)
        with self._gate:
            if self.path is not None and _key(path) == _key(self.path):
                return
            old_path = self.path
            with self._locked():
                state = self._read()
                linked = tuple(self._linked(state))
            with _file_lock(path):
                self.path = path
                try:
                    existing = self._read()
                    merged = {
                        **existing,
                        "linked": {**existing["linked"], **{item.key: self._store_path(item.path) for item in linked}},
                        "categories": {**existing["categories"], **state["categories"]},
                        "posters": {**existing["posters"], **state["posters"]},
                    }
                    if merged != existing:
                        self._write(merged)
                except BaseException:
                    self.path = old_path
                    raise

    def save_as(self, path):
        self.attach(path)
