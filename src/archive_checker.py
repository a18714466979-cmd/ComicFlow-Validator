
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZipFile
import hashlib


@dataclass
class ArchiveCheckResult:
    """ZIP压缩包验收结果"""

    path: str
    status: str
    file_count: int = 0
    members: list[str] = field(default_factory=list)
    sha256: str | None = None
    issues: list[str] = field(default_factory=list)
    error: str | None = None


def calculate_sha256(file_path: str | Path) -> str:
    """计算文件SHA256指纹"""

    digest = hashlib.sha256()

    with Path(file_path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def validate_archive(file_path: str | Path) -> ArchiveCheckResult:
    """检查ZIP压缩包完整性、CRC和SHA256"""

    archive_path = Path(file_path)

    if not archive_path.exists():
        return ArchiveCheckResult(
            path=str(archive_path),
            status="FAIL",
            issues=["文件不存在"],
        )

    if not archive_path.is_file():
        return ArchiveCheckResult(
            path=str(archive_path),
            status="FAIL",
            issues=["目标不是文件"],
        )

    sha256 = None

    try:
        # 计算压缩包SHA256
        sha256 = calculate_sha256(archive_path)

        # 打开ZIP压缩包
        with ZipFile(archive_path, "r") as archive:

            infos = archive.infolist()

            # 获取压缩包成员列表
            members = [info.filename for info in infos]

            # 只统计实际文件，不统计目录
            file_count = sum(
                not info.is_dir()
                for info in infos
            )

            # 逐个读取成员并检查CRC
            bad_member = archive.testzip()

            issues = []

            if bad_member is not None:
                issues.append(
                    f"CRC校验失败：{bad_member}"
                )

    except Exception as exc:
        return ArchiveCheckResult(
            path=str(archive_path),
            status="FAIL",
            sha256=sha256,
            error=f"{type(exc).__name__}: {exc}",
        )

    return ArchiveCheckResult(
        path=str(archive_path),
        status="PASS" if not issues else "FAIL",
        file_count=file_count,
        members=members,
        sha256=sha256,
        issues=issues,
    )
