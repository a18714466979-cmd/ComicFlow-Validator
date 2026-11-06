
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED

from src.archive_checker import validate_archive


def test_valid_archive(tmp_path):
    """正常ZIP应该通过"""

    path = tmp_path / "valid.zip"

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("assets/", b"")
        archive.writestr("assets/shot.txt", b"frame data")

    result = validate_archive(path)

    assert result.status == "PASS"
    assert result.file_count == 1
    assert len(result.sha256) == 64
    assert "assets/shot.txt" in result.members


def test_crc_failure(tmp_path):
    """修改ZIP内部数据后应该检测到CRC错误"""

    path = tmp_path / "broken_crc.zip"

    payload = b"UNIQUE_CRC_PAYLOAD_123456"

    with ZipFile(path, "w", ZIP_STORED) as archive:
        archive.writestr("shot.txt", payload)

    # 修改压缩包内部数据，但不修改原CRC记录
    raw = bytearray(path.read_bytes())
    offset = raw.find(payload)

    assert offset >= 0

    raw[offset] ^= 0x01
    path.write_bytes(raw)

    result = validate_archive(path)

    assert result.status == "FAIL"
    assert any("CRC" in issue for issue in result.issues)


def test_invalid_zip(tmp_path):
    """非ZIP文件应该识别为异常"""

    path = tmp_path / "invalid.zip"
    path.write_bytes(b"this is not a zip file")

    result = validate_archive(path)

    assert result.status == "FAIL"
    assert result.error is not None


def test_missing_zip(tmp_path):
    """不存在的压缩包应该识别"""

    path = tmp_path / "missing.zip"

    result = validate_archive(path)

    assert result.status == "FAIL"
    assert "文件不存在" in result.issues


def test_sha256_matches(tmp_path):
    """SHA256应该与标准计算结果一致"""

    path = tmp_path / "hash_test.zip"

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("test.txt", b"hello world")

    result = validate_archive(path)

    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    assert result.sha256 == expected


def test_directory_is_not_counted(tmp_path):
    """目录不应该计入文件数量"""

    path = tmp_path / "directory_test.zip"

    with ZipFile(path, "w") as archive:
        archive.writestr("folder/", b"")
        archive.writestr("folder/a.txt", b"A")
        archive.writestr("folder/b.txt", b"B")

    result = validate_archive(path)

    assert result.status == "PASS"
    assert result.file_count == 2
