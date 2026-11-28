from zipfile import ZipFile

import pytest

from src.asset_registry import AssetRegistry, check_package_assets
from src.repair_package import affected_files, pack_repair
from src.storyboard_review import ReviewResult, index_members


def test_asset_recovery_uses_fingerprint_and_proves_direct_copy(tmp_path):
    source = tmp_path / "old.png"
    source.write_bytes(b"approved")
    registry = AssetRegistry(tmp_path / "assets.sqlite3", create=True)
    asset = registry.register(source, "凯尔", "R1")
    migrated = tmp_path / "migrated"
    migrated.mkdir()
    (migrated / source.name).write_bytes(b"different")
    moved = source.rename(migrated / "changed-name.png")
    assert registry.recover(migrated) == {asset: moved}
    with pytest.raises(ValueError, match="新版本号"):
        registry.register(migrated / source.name, "凯尔", "R1", asset.origin)

    group = tmp_path / "package" / "SB05"
    group.mkdir(parents=True)
    record = group / "SB05_shot_details.txt"
    record.write_text(f"资产复用核对：\n- copy.png | 直接复用 | {source} | 保留批准图\n", encoding="utf-8")
    delivery = group / "copy.png"
    delivery.write_bytes(b"approved")
    resolved, errors = check_package_assets(group.parent, registry)
    assert not errors and len(resolved) == 1
    delivery.write_bytes(b"different")
    resolved, errors = check_package_assets(group.parent, registry)
    assert not resolved and "直接复用" in errors[0]


def test_related_files_follow_the_actual_clean_plate_reference(tmp_path):
    archive = tmp_path / "before.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("README.txt", "notes")
        package.writestr("SB05/SB05_shot_details.txt", (
            "分镜 SB05-04\n动作：回头\n场景局部对应表：\n"
            "- SB05-04 | details_2.png | 局部04 | 走廊 | 无人物\n"
        ))
        package.writestr("SB05/SD2_prompt.txt", "分镜编号：SB05-04\n动作：回头\n")
        for filename in ("storyboard.png", "details_1.png", "details_2.png"):
            package.writestr("SB05/" + filename, "image")
        members = index_members(package)
    result = ReviewResult(0, "", archive, members, [])
    assert set(affected_files(result, "SB05", "SB05-04")) == {
        "SB05/storyboard.png", "SB05/details_2.png", "SB05/SB05_shot_details.txt", "SB05/SD2_prompt.txt", "README.txt",
    }


def test_repack_publishes_only_validated_new_zip(tmp_path):
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    baseline = tmp_path / "before.zip"
    with ZipFile(baseline, "w") as package:
        package.writestr("README.txt", "before")
    original = baseline.read_bytes()
    target = tmp_path / "after.zip"
    validator = tmp_path / "validator.py"
    validator.write_text("raise SystemExit(1)\n", encoding="utf-8")
    (delivery / "README.txt").write_text("after", encoding="utf-8")

    assert pack_repair(delivery, target, validator, baseline).exit_code == 1
    assert not target.exists()

    validator.write_text("print('RESULT: 0 error(s), 0 warning(s)')\n", encoding="utf-8")
    result = pack_repair(delivery, target, validator, baseline)
    assert result.output == target and result.sha256 and result.changed == ("README.txt",)
    assert original == baseline.read_bytes()
    with ZipFile(target) as package:
        assert package.testzip() is None and package.read("README.txt") == b"after"
    with pytest.raises(FileExistsError):
        pack_repair(delivery, target, validator, baseline)


@pytest.mark.parametrize(("old_eol", "new_eol"), [(b"\r\n", b"\n"), (b"\n", b"\r\n")])
def test_cross_platform_repair_preserves_unedited_members(tmp_path, old_eol, new_eol):
    delivery = tmp_path / "delivery"
    baseline = tmp_path / "original.zip"
    original = {
        "README.txt": b"\xef\xbb\xbfnotes\nsecond line\n",
        "SB02/SB02_shot_details.txt": b"another group\nend",
        "SB01/SB01_shot_details.txt": b"old shot\n",
        "SB01/plate.bin": b"original\r\n",
    }
    with ZipFile(baseline, "w") as previous:
        for member, data in original.items():
            before = data.replace(b"\n", old_eol) if member.endswith(".txt") else data
            previous.writestr("delivery/" + member, before)
            staged = delivery / member
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(data.replace(b"\n", new_eol) if member.endswith(".txt") else data)
    changed = {"SB01/SB01_shot_details.txt": b"new shot" + new_eol, "SB01/plate.bin": b"original\n"}
    for name, data in changed.items():
        (delivery / name).write_bytes(data)
    staged_files = {name: (delivery / name).read_bytes() for name in original}
    validator = tmp_path / "validator.py"
    validator.write_text("print('RESULT: 0 error(s), 0 warning(s)')\n", encoding="utf-8")
    target = tmp_path / "repaired.zip"
    result = pack_repair(delivery, target, validator, baseline)

    assert result.exit_code == 0, result.report
    assert set(result.changed) == set(changed) and not result.added and not result.removed
    with ZipFile(target) as repaired, ZipFile(baseline) as previous:
        assert repaired.testzip() is None
        for name in original:
            expected = changed.get(name, previous.read("delivery/" + name))
            assert repaired.read(name) == expected
            assert (delivery / name).read_bytes() == staged_files[name]
