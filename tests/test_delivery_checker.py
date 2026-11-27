
import json
import stat
import zipfile

import pytest

from src.delivery_checker import (
    DeliveryRules,
    normalize_rule_path,
    normalize_archive_path,
    load_rules,
    scan_folder,
    scan_zip,
    validate_delivery,
)


# ============================================================
# 1. 路径安全测试
# ============================================================

def test_normalize_rule_path():
    assert normalize_rule_path("storyboards\\page1.png") == (
        "storyboards/page1.png"
    )


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "/absolute/file.txt",
        "C:\\outside.txt",
        "",
    ],
)
def test_reject_unsafe_rule_paths(path):
    with pytest.raises(ValueError):
        normalize_rule_path(path)


def test_reject_archive_path_traversal():
    assert normalize_archive_path("../outside.txt") is None
    assert normalize_archive_path("C:/outside.txt") is None
    assert normalize_archive_path("/outside.txt") is None


def test_normalize_safe_archive_path():
    assert normalize_archive_path(
        "storyboards/page1.png"
    ) == "storyboards/page1.png"


# ============================================================
# 2. 文件夹验收测试
# ============================================================

def test_folder_pass(tmp_path):

    folder = tmp_path / "delivery"
    storyboard = folder / "storyboards"

    storyboard.mkdir(parents=True)

    (storyboard / "page1.png").write_bytes(b"PNG_TEST")
    (folder / "README.md").write_text(
        "ComicFlow delivery",
        encoding="utf-8",
    )

    rules = DeliveryRules(
        required_dirs=("storyboards",),
        required_files=("README.md",),
        allowed_extensions=(".png", ".md"),
    )

    report = scan_folder(folder, rules)

    assert report.passed
    assert report.file_count == 2
    assert report.error_count == 0


def test_folder_missing_required_items(tmp_path):

    folder = tmp_path / "delivery"
    folder.mkdir()

    rules = DeliveryRules(
        required_dirs=("storyboards",),
        required_files=("README.md",),
    )

    report = scan_folder(folder, rules)

    assert not report.passed
    assert report.error_count == 2


def test_folder_detects_forbidden_files(tmp_path):

    folder = tmp_path / "delivery"
    folder.mkdir()

    (folder / "Thumbs.db").write_bytes(b"")
    (folder / "empty.txt").write_bytes(b"")

    report = scan_folder(folder, DeliveryRules())

    assert report.warning_count >= 2
    assert report.file_count == 2


def test_folder_rejects_wrong_extension(tmp_path):

    folder = tmp_path / "delivery"
    folder.mkdir()

    (folder / "document.exe").write_bytes(b"test")

    rules = DeliveryRules(
        allowed_extensions=(".png", ".jpg"),
    )

    report = scan_folder(folder, rules)

    assert not report.passed
    assert report.error_count == 1


def test_folder_checks_max_file_size(tmp_path):

    folder = tmp_path / "delivery"
    folder.mkdir()

    (folder / "large.bin").write_bytes(b"x" * 1024)

    rules = DeliveryRules(
        max_file_size_mb=0.0001,
    )

    report = scan_folder(folder, rules)

    assert not report.passed


# ============================================================
# 3. ZIP 压缩包验收测试
# ============================================================

def test_zip_pass(tmp_path):

    archive = tmp_path / "delivery.zip"

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "storyboards/page1.png",
            b"PNG_TEST",
        )
        zf.writestr(
            "README.md",
            "ComicFlow delivery",
        )

    rules = DeliveryRules(
        required_dirs=("storyboards",),
        required_files=("README.md",),
    )

    report = scan_zip(archive, rules)

    assert report.passed
    assert report.file_count == 2


def test_zip_detects_path_traversal(tmp_path):

    archive = tmp_path / "unsafe.zip"

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "../outside.txt",
            "unsafe content",
        )

    report = scan_zip(archive, DeliveryRules())

    assert not report.passed
    assert report.error_count >= 1


def test_zip_detects_symlink(tmp_path):

    archive = tmp_path / "symlink.zip"

    info = zipfile.ZipInfo("fake_link.txt")
    info.create_system = 3
    info.external_attr = (
        stat.S_IFLNK | 0o777
    ) << 16

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, "target.txt")

    report = scan_zip(archive, DeliveryRules())

    assert not report.passed
    assert any(
        "符号链接" in issue.message
        for issue in report.issues
    )


def test_zip_detects_duplicate_members(tmp_path):

    archive = tmp_path / "duplicate.zip"

    with pytest.warns(UserWarning):
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("README.md", "first")
            zf.writestr("README.md", "second")

    report = scan_zip(archive, DeliveryRules())

    assert not report.passed
    assert any(
        "重复路径" in issue.message
        for issue in report.issues
    )


# ============================================================
# 4. 统一入口测试
# ============================================================

def test_validate_delivery_folder(tmp_path):

    folder = tmp_path / "delivery"
    folder.mkdir()

    (folder / "README.md").write_text(
        "test",
        encoding="utf-8",
    )

    report = validate_delivery(folder)

    assert report.passed


def test_validate_delivery_zip(tmp_path):

    archive = tmp_path / "delivery.zip"

    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("README.md", "test")

    report = validate_delivery(archive)

    assert report.passed


def test_validate_delivery_rejects_unsupported_file(tmp_path):

    file = tmp_path / "document.txt"
    file.write_text("test")

    with pytest.raises(ValueError):
        validate_delivery(file)


# ============================================================
# 5. JSON 规则配置测试
# ============================================================

def test_load_rules(tmp_path):

    config = tmp_path / "rules.json"

    data = {
        "required_dirs": ["storyboards"],
        "required_files": ["README.md"],
        "forbidden_names": ["Thumbs.db"],
        "allowed_extensions": [".png", ".jpg"],
        "max_file_size_mb": 50,
    }

    config.write_text(
        json.dumps(data),
        encoding="utf-8",
    )

    rules = load_rules(config)

    assert rules.required_dirs == ("storyboards",)
    assert rules.required_files == ("README.md",)
    assert rules.allowed_extensions == (".png", ".jpg")
    assert rules.max_file_size_mb == 50


# ============================================================
# 6. ZIP 资源限制与完整性测试
# ============================================================

def test_zip_rejects_member_count_limit(tmp_path):
    archive = tmp_path / "too_many_members.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("one.txt", "1")
        zf.writestr("two.txt", "2")

    report = scan_zip(archive, DeliveryRules(max_zip_members=1))

    assert not report.passed
    assert any("成员数量超过限制" in issue.message for issue in report.issues)


def test_zip_rejects_single_member_size_limit(tmp_path):
    archive = tmp_path / "large_member.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("large.bin", b"x" * 2048)

    report = scan_zip(
        archive,
        DeliveryRules(max_zip_member_size_mb=0.001),
    )

    assert not report.passed
    assert any("单个成员解压大小超过限制" in issue.message for issue in report.issues)


def test_zip_rejects_total_uncompressed_size_limit(tmp_path):
    archive = tmp_path / "large_total.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("one.bin", b"a" * 2048)
        zf.writestr("two.bin", b"b" * 2048)

    report = scan_zip(
        archive,
        DeliveryRules(
            max_zip_member_size_mb=1,
            max_zip_total_size_mb=0.003,
        ),
    )

    assert not report.passed
    assert any("总解压大小超过限制" in issue.message for issue in report.issues)


def test_zip_rejects_excessive_compression_ratio(tmp_path):
    archive = tmp_path / "high_ratio.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("repetitive.txt", b"A" * 8192)

    report = scan_zip(
        archive,
        DeliveryRules(max_compression_ratio=2.0),
    )

    assert not report.passed
    assert any("压缩率超过限制" in issue.message for issue in report.issues)


def test_zip_skips_crc_scan_when_resource_limit_exceeded(tmp_path, monkeypatch):
    archive = tmp_path / "skip_crc.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("large.bin", b"x" * 2048)

    def fail_if_called(self):
        raise AssertionError("资源超限时不应执行 testzip")

    monkeypatch.setattr(zipfile.ZipFile, "testzip", fail_if_called)
    report = scan_zip(
        archive,
        DeliveryRules(max_zip_member_size_mb=0.001),
    )

    assert not report.passed
    assert any("单个成员解压大小超过限制" in issue.message for issue in report.issues)


def test_zip_reports_crc_failure(tmp_path, monkeypatch):
    archive = tmp_path / "crc_failure.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("README.md", "valid content")

    monkeypatch.setattr(zipfile.ZipFile, "testzip", lambda self: "README.md")
    report = scan_zip(archive, DeliveryRules())

    assert not report.passed
    assert any("CRC 校验失败" in issue.message for issue in report.issues)


def test_zip_detects_file_directory_conflict(tmp_path):
    archive = tmp_path / "file_directory_conflict.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a", "this is a file")
        zf.writestr("a/b.txt", "this path requires a to be a directory")

    report = scan_zip(archive, DeliveryRules())

    assert not report.passed
    assert any("文件与目录路径冲突" in issue.message for issue in report.issues)


def test_folder_detects_default_forbidden_names_case_insensitively(tmp_path):
    folder = tmp_path / "delivery"
    folder.mkdir()
    (folder / ".ds_store").write_bytes(b"metadata")
    (folder / "THUMBS.DB").write_bytes(b"metadata")
    (folder / "DESKTOP.INI").write_bytes(b"metadata")

    report = scan_folder(folder, DeliveryRules())

    assert report.warning_count == 3
