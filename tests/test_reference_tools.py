from hashlib import sha256

import pytest
from PIL import Image

from src.production_project import ProductionProject
from src.reference_tools_dialog import (
    COSTUME_GROUPS, COSTUMES, COSTUME_ROOT, SHISEI_SOURCE, filter_costumes, import_reference, read_reference,
)


def test_pose_png_reuses_exact_bytes(tmp_path):
    source = tmp_path / "pose.png"
    path = tmp_path / "group.cfproject"
    Image.new("RGB", (640, 360), "steelblue").save(source)
    image_bytes = source.read_bytes()
    digest = sha256(image_bytes).hexdigest()
    project = ProductionProject("Reference test", "EP01", "SB01")

    asset = import_reference(project, path, source, "pose", seen_digest=digest)
    assert asset.reference_only
    assert project.checked_image(path, asset).read_bytes() == image_bytes
    assert import_reference(project, path, source, "pose", seen_digest=digest).id == asset.id

    Image.new("RGB", (640, 360), "red").save(source)
    with pytest.raises(ValueError, match="预览后发生变化"):
        import_reference(project, path, source, "pose", seen_digest=digest)
    assert len(project.images) == 1


def test_bundled_costumes_match_pinned_upstream_and_convert_to_reference_png(tmp_path):
    path = tmp_path / "group.cfproject"
    project = ProductionProject("Reference test", "EP01", "SB01")
    assert (COSTUME_ROOT / "LICENSE-images").is_file()
    assert (COSTUME_ROOT / "NOTICE").is_file()
    source_record = (COSTUME_ROOT / "SOURCE.txt").read_text(encoding="utf-8")
    assert {path.stem.split("_")[1] for path in COSTUME_ROOT.glob("costume_*_front.webp")} == {
        identity for identity, _, _, _ in COSTUMES
    }
    for identity, _, _, digest in COSTUMES:
        filename = f"costume_{identity}_front.webp"
        assert f"{filename} {digest}" in source_record
        source = COSTUME_ROOT / filename
        _, source_format, preview = read_reference(source, digest)
        assert source_format == "WEBP" and preview.size == (900, 1200)
        asset = import_reference(project, path, source, "costume", seen_digest=digest, origin=SHISEI_SOURCE + filename)
        assert asset.reference_only
        assert asset.origin == f"{SHISEI_SOURCE}{filename} | WEBP SHA-256 {digest}"
        with Image.open(project.checked_image(path, asset)) as converted:
            converted.load()
            assert converted.format == "PNG" and converted.size == preview.size
            assert converted.tobytes() == preview.convert("RGB").tobytes()

    with pytest.raises(ValueError, match="SHA-256"):
        read_reference(source, "0" * 64)


def test_costume_search_matches_chinese_english_and_ids_within_selected_category():
    assert filter_costumes(COSTUMES, "   ") == COSTUMES
    assert [outfit[0] for outfit in filter_costumes(COSTUMES, "护士")] == ["C259"]
    assert [outfit[0] for outfit in filter_costumes(COSTUMES, "BLUE  Nurse")] == ["C259"]
    assert [outfit[0] for outfit in filter_costumes(COSTUMES, "c259")] == ["C259"]
    assert filter_costumes(COSTUME_GROUPS[0][2], "护士") == ()


def test_local_jpeg_can_be_used_as_a_pose_reference(tmp_path):
    source = tmp_path / "pose.jpg"
    path = tmp_path / "group.cfproject"
    Image.new("RGB", (320, 180), "steelblue").save(source)
    project = ProductionProject("Reference test", "EP01", "SB01")
    asset = import_reference(project, path, source, "pose", seen_digest=sha256(source.read_bytes()).hexdigest())
    with Image.open(project.checked_image(path, asset)) as converted:
        assert asset.reference_only and converted.format == "PNG"
