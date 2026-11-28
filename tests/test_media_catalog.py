from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from src.media_catalog import MediaCatalog, MediaCatalogError, MediaItem, category_for_filename


def test_overlay_merges_linked_assets_without_changing_native_records(tmp_path):
    stored = tmp_path / "native.png"
    stored.write_bytes(b"approved original")
    aspect = tmp_path / "Vera.jpg"
    aspect.write_bytes(b"unclassified portrait")
    video = tmp_path / "03_scene_rooftop.MP4"
    video.write_bytes(b"motion clip")
    unsupported = tmp_path / "draft.txt"
    unsupported.write_text("plain text", encoding="utf-8")
    native = MediaItem("asset-1", stored, "角色", "Approved", name="维拉三视图.png")
    target = tmp_path / "cut.assets" / "media.json"
    catalog = MediaCatalog(target)
    assert catalog.items([native])[0].category == "character"
    assert not target.exists()

    imported = catalog.import_paths([aspect, video, unsupported])
    assert [(item.category, item.media_type) for item in imported] == [
        ("unclassified", "image"), ("scene", "video"),
    ]
    assert catalog.import_paths([aspect])[0].key == imported[0].key
    catalog.categorize([native.key, imported[0].key], "道具")
    catalog.set_poster(imported[1].key, 330)
    repaired = MediaCatalog(target)
    assert [(item.key, item.category) for item in repaired.items([native])] == [
        (native.key, "prop"), (imported[0].key, "prop"), (imported[1].key, "scene"),
    ]
    assert repaired.poster_times() == {imported[1].key: 330}
    assert repaired.items([native])[0].display_name == native.display_name == "维拉三视图.png"
    assert native.category == "角色" and stored.read_bytes() == b"approved original"


def test_import_can_cancel_without_writing_and_relink_keeps_category(tmp_path):
    target = tmp_path / "media.json"
    first = tmp_path / "Action.MP4"
    second = tmp_path / "Motion.mov"
    photo = tmp_path / "Frame.jpg"
    for path in (first, second, photo):
        path.write_bytes(b"demo")
    catalog = MediaCatalog(target)
    cancel = Event()

    def interrupted():
        yield first
        cancel.set()
        yield second

    assert catalog.import_paths(interrupted(), stop=cancel) == ()
    assert not target.exists()
    item, = catalog.import_paths([first], "motion_reference")
    catalog.set_poster(item.key, 200)
    with pytest.raises(ValueError, match="same media type"):
        catalog.relink(item.key, photo)
    catalog.relink(item.key, second)
    assert catalog.poster_time(item.key) is None
    result, = MediaCatalog(target).items()
    assert result.path == second and result.key == item.key and result.category == "motion_reference"
    assert first.read_bytes() == second.read_bytes() == b"demo"


def test_untitled_catalog_can_attach_and_merge_concurrent_updates(tmp_path):
    memory = MediaCatalog(None)
    photo = tmp_path / "画面.webp"
    photo.write_bytes(b"local original")
    item, = memory.import_paths([photo], "人物")
    target = tmp_path / "media.json"
    disk = MediaCatalog(target)
    disk.categorize(["native-1"], "scene")
    memory.attach(target)
    assert memory.items()[0] == item
    assert disk.items([MediaItem("native-1", Path("native.png"))])[0].category == "scene"

    def label(key):
        MediaCatalog(target).categorize([f"native-{key}"], "charACTER")

    with ThreadPoolExecutor(max_workers=4) as pool:
        tuple(pool.map(label, range(2, 12)))
    states = memory.items([MediaItem(f"native-{key}", Path("native.png")) for key in range(2, 12)])
    assert [record.category for record in states[:-1]] == ["character"] * 10


def test_bad_catalog_fails_instead_of_replacing_existing_file(tmp_path):
    target = tmp_path / "media.json"
    original = b"invalid format"
    target.write_bytes(original)
    catalog = MediaCatalog(target)
    with pytest.raises(MediaCatalogError):
        catalog.categorize(["x"], "scene")
    assert target.read_bytes() == original


@pytest.mark.parametrize(("filename", "category"), [
    ("07_props_信封.png", "prop"), ("04_other_characters_crowd.PNG", "character"),
    ("08_scene_值守站_16x9.jpg", "scene"), ("storyboard_EP04.png", "storyboard"),
    ("08_河边的人群.png", "unclassified"), ("2024_characteristic_photo.png", "unclassified"),
    ("01_场景-码头.png", "scene"), ("角色_米洛.png", "character"), ("道具-信封.png", "prop"),
    ("动作参考_转身.mp4", "motion_reference"), ("场景气氛图.png", "unclassified"),
])
def test_inference_uses_production_prefixes(filename, category):
    assert category_for_filename(filename) == category
