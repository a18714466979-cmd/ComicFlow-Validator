"""Gallery entries for e-commerce originals and the production images they reference."""

from hashlib import blake2b
from os.path import normcase
from pathlib import Path

from .media_catalog import MediaItem, normalize_category


def _identity(value: str) -> str:
    return blake2b(value.encode("utf-8"), digest_size=16).hexdigest()


def catalog_path(path: Path, project_id: str) -> Path:
    # Several projects can use the same output folder after a project file is replaced.
    return path.with_suffix(".ecom-assets") / f"media-{_identity(project_id)}.json"


def source_clip(path: Path, purpose: str) -> MediaItem:
    # The poster belongs to the source clip, so replacing the video starts with an automatic frame.
    return MediaItem(f"video:{_identity(normcase(str(path)))}", path, purpose=purpose, media_type="video")


def product_photo(path: Path, purpose: str) -> MediaItem:
    return MediaItem(f"photo:{_identity(normcase(str(path)))}", path, category="product", purpose=purpose)


def linked_image(slot: str, path: Path, purpose: str) -> MediaItem:
    kind = slot.split(":", 1)[0]
    category = {"board": "storyboard", "panel": "storyboard", "props": "prop"}.get(kind, normalize_category(kind))
    return MediaItem(f"binding:{_identity(slot)}", path, category=category, purpose=purpose)
