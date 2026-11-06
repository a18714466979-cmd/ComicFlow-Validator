
import argparse
from pathlib import Path

import pytest
from PIL import Image

from src.image_checker import (
    ImageCheckConfig,
    validate_image,
    scan_folder,
    parse_ratio,
    parse_min_size,
)


def create_image(path: Path, size: tuple[int, int]):
    """创建测试图片"""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return path


def test_valid_image_passes(tmp_path):
    """正常16:9图片应该通过"""
    path = create_image(tmp_path / "valid.jpg", (1920, 1080))

    result = validate_image(
        path,
        ImageCheckConfig(
            target_ratio=(16, 9),
            min_width=1920,
            min_height=1080,
        ),
    )

    assert result.status == "PASS"
    assert result.width == 1920
    assert result.height == 1080


def test_wrong_ratio_fails(tmp_path):
    """正方形图片不应该通过16:9验收"""
    path = create_image(tmp_path / "square.png", (1000, 1000))

    result = validate_image(
        path,
        ImageCheckConfig(target_ratio=(16, 9)),
    )

    assert result.status == "FAIL"
    assert any("比例不符" in issue for issue in result.issues)


def test_small_resolution_fails(tmp_path):
    """分辨率不足应该报错"""
    path = create_image(tmp_path / "small.jpg", (1280, 720))

    result = validate_image(
        path,
        ImageCheckConfig(
            min_width=1920,
            min_height=1080,
        ),
    )

    assert result.status == "FAIL"
    assert len(result.issues) == 2


def test_corrupt_image_fails(tmp_path):
    """损坏图片应该被识别"""
    path = tmp_path / "corrupt.jpg"
    path.write_bytes(b"not a real image")

    result = validate_image(path, ImageCheckConfig())

    assert result.status == "FAIL"
    assert result.error is not None


def test_scan_folder_recursive(tmp_path):
    """默认应该扫描子文件夹"""
    create_image(tmp_path / "top.jpg", (1920, 1080))
    create_image(tmp_path / "sub" / "nested.png", (1920, 1080))
    (tmp_path / "ignore.txt").write_text("test")

    results = scan_folder(tmp_path, ImageCheckConfig())

    assert len(results) == 2
    assert all(item.status == "PASS" for item in results)


def test_scan_folder_non_recursive(tmp_path):
    """关闭递归后只扫描当前文件夹"""
    create_image(tmp_path / "top.jpg", (1920, 1080))
    create_image(tmp_path / "sub" / "nested.png", (1920, 1080))

    results = scan_folder(
        tmp_path,
        ImageCheckConfig(recursive=False),
    )

    assert len(results) == 1


def test_missing_folder_raises_error(tmp_path):
    """不存在的文件夹应该报错"""
    with pytest.raises(FileNotFoundError):
        scan_folder(tmp_path / "missing", ImageCheckConfig())


def test_file_instead_of_folder_raises_error(tmp_path):
    """传入文件而不是文件夹应该报错"""
    path = tmp_path / "test.txt"
    path.write_text("test")

    with pytest.raises(NotADirectoryError):
        scan_folder(path, ImageCheckConfig())


def test_parse_ratio():
    assert parse_ratio("16:9") == (16, 9)
    assert parse_ratio("1:1") == (1, 1)


def test_parse_ratio_invalid():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_ratio("0:9")


def test_parse_min_size():
    assert parse_min_size("1920x1080") == (1920, 1080)
    assert parse_min_size("1920×1080") == (1920, 1080)


def test_parse_min_size_invalid():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_min_size("0x1080")
