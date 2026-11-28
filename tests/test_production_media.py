from PIL import Image

from src.production_layout import bind_window
from src.production_media import project_media_catalog, project_media_items
from src.production_project import ProductionProject, Shot


def test_existing_approved_image_has_named_card_and_persistent_category(tmp_path):
    path = tmp_path / "第04集.cfproject"
    source = tmp_path / "unknown.png"
    Image.new("RGB", (160, 90), "steelblue").save(source)
    project = ProductionProject("Library test", "EP04", "SB01")
    shot = Shot(anchor="米洛转身")
    project.shots.append(shot)
    image = project.import_image(
        path, source, "人工命名.png", action="直接复用", reason="复用原图", inspection="按原始尺寸核对",
    )
    bind_window(project, path, shot.id, "plate", image.id)
    project.save(path)
    approved_before = path.read_bytes()
    original = project.checked_image(path, image)

    original_project = ProductionProject.open(path)
    initial = project_media_items(original_project, path)
    card, = initial
    assert (card.key, card.display_name, card.category, card.path) == (
        image.id, "人工命名.png", "clean_plate", original,
    )

    catalog = project_media_catalog(path)
    catalog.categorize([card.key], "scene")
    video = tmp_path / "人物转身.mp4"
    video.write_bytes(b"Local video link fixture")
    linked, = catalog.import_paths([video], "character")
    reopened = ProductionProject.open(path)
    by_key = {
        item.key: item for item in project_media_catalog(path).items(project_media_items(reopened, path, english=True))
    }
    assert by_key[card.key].category == "scene" and "Delivery image" in by_key[card.key].purpose
    assert (by_key[linked.key].category, by_key[linked.key].media_type, by_key[linked.key].path) == (
        "character", "video", video,
    )
    assert path.read_bytes() == approved_before
    assert source.read_bytes() == original.read_bytes()
    assert reopened.images == original_project.images
