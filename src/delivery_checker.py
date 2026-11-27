from __future__ import annotations

import argparse
import json
import re
import stat
import subprocess
import sys
import zipfile

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


# ============================================================
# ComicFlow Validator - 交付包验收模块
# ============================================================

DEFAULT_FORBIDDEN_NAMES = (
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "__MACOSX",
)


@dataclass
class DeliveryRules:
    """交付包验收规则。"""

    required_dirs: tuple[str, ...] = ()
    required_files: tuple[str, ...] = ()
    forbidden_names: tuple[str, ...] = DEFAULT_FORBIDDEN_NAMES
    allowed_extensions: tuple[str, ...] = ()
    max_file_size_mb: float | None = None

    # ZIP 安全限制
    max_zip_members: int = 20000
    max_zip_member_size_mb: float = 512
    max_zip_total_size_mb: float = 5120
    max_compression_ratio: float = 200.0


@dataclass
class DeliveryIssue:
    """单项验收结果。"""

    level: str
    path: str
    message: str


@dataclass
class DeliveryReport:
    """完整验收报告。"""

    source: str
    file_count: int = 0
    directory_count: int = 0
    issues: list[DeliveryIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(issue.level == "ERROR" for issue in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(issue.level == "WARNING" for issue in self.issues)

    @property
    def passed(self) -> bool:
        return self.error_count == 0


# ============================================================
# 规则配置
# ============================================================

def normalize_rule_path(value: str) -> str:
    """规范化规则中的相对路径。"""

    value = value.replace("\\", "/")

    if (
        not value
        or value.startswith("/")
        or re.match(r"^[a-zA-Z]:", value)
        or "\x00" in value
    ):
        raise ValueError(f"无效规则路径: {value}")

    path = PurePosixPath(value)

    if ".." in path.parts:
        raise ValueError(f"规则路径不能包含上级目录: {value}")

    normalized = path.as_posix().rstrip("/")
    if normalized in ("", "."):
        raise ValueError(f"无效规则路径: {value}")

    return normalized


def load_rules(path: Path | None) -> DeliveryRules:
    """读取 JSON 验收规则。"""

    if path is None:
        return DeliveryRules()

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return DeliveryRules(
        required_dirs=tuple(
            normalize_rule_path(value)
            for value in data.get("required_dirs", [])
        ),
        required_files=tuple(
            normalize_rule_path(value)
            for value in data.get("required_files", [])
        ),
        forbidden_names=tuple(
            str(value).casefold()
            for value in data.get("forbidden_names", DEFAULT_FORBIDDEN_NAMES)
        ),
        allowed_extensions=tuple(
            str(value).lower()
            if str(value).startswith(".")
            else "." + str(value).lower()
            for value in data.get("allowed_extensions", [])
        ),
        max_file_size_mb=data.get("max_file_size_mb"),
        max_zip_members=int(data.get("max_zip_members", 20000)),
        max_zip_member_size_mb=float(
            data.get("max_zip_member_size_mb", 512)
        ),
        max_zip_total_size_mb=float(
            data.get("max_zip_total_size_mb", 5120)
        ),
        max_compression_ratio=float(
            data.get("max_compression_ratio", 200.0)
        ),
    )


# ============================================================
# ZIP 路径安全检查
# ============================================================

def normalize_archive_path(name: str) -> str | None:
    """检查 ZIP 内部路径，防止路径穿越。"""

    name = name.replace("\\", "/")

    if (
        not name
        or "\x00" in name
        or name.startswith("/")
        or re.match(r"^[a-zA-Z]:", name)
    ):
        return None

    path = PurePosixPath(name)

    if ".." in path.parts:
        return None

    parts = [part for part in path.parts if part not in ("", ".")]
    if not parts:
        return None

    return "/".join(parts)


# ============================================================
# 通用验收逻辑
# ============================================================

def check_entries(
    source: str,
    files: list[tuple[str, int]],
    directories: set[str],
    initial_issues: list[DeliveryIssue],
    rules: DeliveryRules,
) -> DeliveryReport:
    report = DeliveryReport(
        source=source,
        file_count=len(files),
        directory_count=len(directories),
        issues=initial_issues.copy(),
    )

    def add(level: str, path: str, message: str) -> None:
        report.issues.append(DeliveryIssue(level, path, message))

    # 同时检查大小写冲突，以及同一路径被同时用作文件和目录的冲突。
    seen: dict[str, tuple[str, str]] = {}
    entries = (
        [(path, "directory") for path in directories]
        + [(path, "file") for path, _ in files]
    )

    for path, entry_type in sorted(entries, key=lambda item: (item[0].casefold(), item[0], item[1])):
        key = path.casefold()
        previous = seen.get(key)

        if previous is None:
            seen[key] = (path, entry_type)
            continue

        previous_path, previous_type = previous
        if previous_path != path:
            add(
                "ERROR",
                path,
                f"路径大小写冲突，与 {previous_path} 重复",
            )
        elif previous_type != entry_type:
            add(
                "ERROR",
                path,
                "文件与目录路径冲突：同一路径不能同时是文件和目录",
            )

    file_map = {path.casefold(): size for path, size in files}
    dir_map = {path.casefold() for path in directories}

    # 必需目录与必需文件
    for required in rules.required_dirs:
        if required.casefold() not in dir_map:
            add("ERROR", required, "缺少规定目录")

    for required in rules.required_files:
        if required.casefold() not in file_map:
            add("ERROR", required, "缺少规定文件")

    # 系统文件/目录名称统一按大小写不敏感方式检查。
    forbidden_names = {name.casefold() for name in rules.forbidden_names}
    for path in directories:
        if PurePosixPath(path).name.casefold() in forbidden_names:
            add("WARNING", path, "发现不建议交付的系统目录")

    # 检查每个文件
    for path, size in files:
        basename = PurePosixPath(path).name.casefold()
        extension = PurePosixPath(path).suffix.lower()

        if basename in forbidden_names:
            add("WARNING", path, "发现不建议交付的系统文件")

        if size == 0:
            add("WARNING", path, "文件大小为 0 字节")

        if (
            rules.allowed_extensions
            and extension not in rules.allowed_extensions
        ):
            add(
                "ERROR",
                path,
                f"不允许的文件格式: {extension or '无扩展名'}",
            )

        if rules.max_file_size_mb is not None:
            limit = rules.max_file_size_mb * 1024 * 1024
            if size > limit:
                add(
                    "ERROR",
                    path,
                    f"文件超过大小限制: {size / 1024 / 1024:.2f} MB",
                )

    return report


# ============================================================
# 文件夹验收
# ============================================================

def scan_folder(
    folder: Path,
    rules: DeliveryRules,
) -> DeliveryReport:
    folder = Path(folder).expanduser()

    if not folder.exists():
        raise FileNotFoundError(f"文件夹不存在: {folder}")

    if not folder.is_dir():
        raise NotADirectoryError(f"不是文件夹: {folder}")

    root = folder.resolve()
    files: list[tuple[str, int]] = []
    directories: set[str] = set()
    issues: list[DeliveryIssue] = []

    for item in root.rglob("*"):
        relative = item.relative_to(root).as_posix()

        # 不跟随符号链接；发现后作为错误报告。
        if item.is_symlink():
            issues.append(
                DeliveryIssue(
                    "ERROR",
                    relative,
                    "发现符号链接，无法确认实际目标",
                )
            )
            continue

        if item.is_dir():
            directories.add(relative)
        elif item.is_file():
            files.append((relative, item.stat().st_size))

    return check_entries(
        str(folder),
        files,
        directories,
        issues,
        rules,
    )


# ============================================================
# ZIP 压缩包验收
# ============================================================

def scan_zip(
    archive: Path,
    rules: DeliveryRules,
) -> DeliveryReport:
    files: list[tuple[str, int]] = []
    directories: set[str] = set()
    issues: list[DeliveryIssue] = []

    with zipfile.ZipFile(archive, "r") as zf:
        # 先读取 ZIP 中央目录，进行资源限制预检；此阶段不解压成员内容。
        infos = zf.infolist()
        resource_limit_exceeded = False

        # 1. ZIP 成员数量限制
        if len(infos) > rules.max_zip_members:
            issues.append(
                DeliveryIssue(
                    "ERROR",
                    str(archive),
                    f"ZIP 成员数量超过限制：{len(infos)} > {rules.max_zip_members}",
                )
            )
            resource_limit_exceeded = True

        # 2. 单个文件及总解压大小限制
        member_limit_bytes = rules.max_zip_member_size_mb * 1024 * 1024
        total_limit_bytes = rules.max_zip_total_size_mb * 1024 * 1024
        total_uncompressed_size = sum(info.file_size for info in infos)

        if total_uncompressed_size > total_limit_bytes:
            issues.append(
                DeliveryIssue(
                    "ERROR",
                    str(archive),
                    "ZIP 总解压大小超过限制："
                    f"{total_uncompressed_size / 1024 / 1024:.2f} MB > "
                    f"{rules.max_zip_total_size_mb} MB",
                )
            )
            resource_limit_exceeded = True

        # 3. 检查每个成员的解压大小和压缩率
        for info in infos:
            if info.file_size > member_limit_bytes:
                issues.append(
                    DeliveryIssue(
                        "ERROR",
                        info.filename,
                        "ZIP 单个成员解压大小超过限制："
                        f"{info.file_size / 1024 / 1024:.2f} MB > "
                        f"{rules.max_zip_member_size_mb} MB",
                    )
                )
                resource_limit_exceeded = True

            if info.file_size > 0:
                ratio = (
                    float("inf")
                    if info.compress_size == 0
                    else info.file_size / info.compress_size
                )
                if ratio > rules.max_compression_ratio:
                    issues.append(
                        DeliveryIssue(
                            "ERROR",
                            info.filename,
                            "ZIP 压缩率超过限制："
                            f"{ratio:.2f} > {rules.max_compression_ratio}",
                        )
                    )
                    resource_limit_exceeded = True

        # 4. 只有资源预检通过后才执行 CRC 完整性验证，避免对超限包进行解压扫描。
        if not resource_limit_exceeded:
            try:
                bad_file = zf.testzip()
            except Exception as exc:
                issues.append(
                    DeliveryIssue(
                        "ERROR",
                        str(archive),
                        f"ZIP CRC 完整性检查异常：{type(exc).__name__}: {exc}",
                    )
                )
            else:
                if bad_file is not None:
                    issues.append(
                        DeliveryIssue(
                            "ERROR",
                            bad_file,
                            "ZIP 文件 CRC 校验失败",
                        )
                    )

        # 5. 继续成员安全检查。即使资源超限，也继续检查中央目录中的路径与类型信息。
        seen_members: set[str] = set()

        for info in infos:
            relative = normalize_archive_path(info.filename)

            # 路径安全
            if relative is None:
                issues.append(
                    DeliveryIssue(
                        "ERROR",
                        info.filename,
                        "ZIP 内存在不安全路径",
                    )
                )
                continue

            # 重复成员（按大小写不敏感方式检查）
            member_key = relative.casefold()
            if member_key in seen_members:
                issues.append(
                    DeliveryIssue(
                        "ERROR",
                        relative,
                        "ZIP 内存在重复路径",
                    )
                )
                continue
            seen_members.add(member_key)

            # 符号链接
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                issues.append(
                    DeliveryIssue(
                        "ERROR",
                        relative,
                        "ZIP 内存在符号链接",
                    )
                )
                continue

            if info.is_dir():
                directories.add(relative.rstrip("/"))
                continue

            files.append((relative, info.file_size))

            # 自动补充父目录，以便必需目录检查和文件/目录冲突检查完整。
            parent = PurePosixPath(relative).parent
            while str(parent) != ".":
                directories.add(parent.as_posix())
                parent = parent.parent

    return check_entries(
        str(archive),
        files,
        directories,
        issues,
        rules,
    )


# ============================================================
# 统一入口
# ============================================================

def validate_delivery(
    source: str | Path,
    rules: DeliveryRules | None = None,
) -> DeliveryReport:
    path = Path(source).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"目标不存在: {path}")

    rules = rules or DeliveryRules()

    if path.is_dir():
        return scan_folder(path, rules)

    if path.is_file() and path.suffix.lower() == ".zip":
        return scan_zip(path, rules)

    raise ValueError("只支持文件夹或 ZIP 压缩包")


# ============================================================
# 报告输出
# ============================================================

def print_report(report: DeliveryReport) -> None:
    print()
    print("=" * 65)
    print("ComicFlow Validator - 交付包验收报告")
    print("=" * 65)
    print(f"目标: {report.source}")
    print(f"文件总数: {report.file_count}")
    print(f"目录总数: {report.directory_count}")
    print("-" * 65)

    if not report.issues:
        print("[通过] 未发现异常")
    else:
        for issue in report.issues:
            print(f"[{issue.level}] {issue.path} | {issue.message}")

    print("-" * 65)
    print(f"错误: {report.error_count}")
    print(f"警告: {report.warning_count}")
    print("最终结果: PASS" if report.passed else "最终结果: FAIL")
    print("=" * 65)


# ============================================================
# 命令行
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="ComicFlow Validator - 交付包验收工具"
    )
    parser.add_argument(
        "source",
        help="需要验收的文件夹或 ZIP 文件",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=None,
        help="可选的 JSON 验收规则文件",
    )
    parser.add_argument(
        "--storyboard-validator",
        type=Path,
        help="已安装故事板工作流的 validate_storyboard_package.py 路径",
    )
    parser.add_argument("--zip", type=Path, help="与故事板交付目录逐文件比对的最终 ZIP")
    parser.add_argument("--allow-legacy", action="store_true", help="按历史格式复核故事板包")
    args = parser.parse_args()

    if args.storyboard_validator is None and (args.zip or args.allow_legacy):
        parser.error("--zip 和 --allow-legacy 需要 --storyboard-validator")

    source = Path(args.source).expanduser()
    if args.storyboard_validator is not None and not source.is_dir():
        parser.error("故事板验收需提供解压后的完整交付目录，并可用 --zip 指定最终包")

    try:
        rules = load_rules(args.rules)
        report = validate_delivery(source, rules)
        if args.storyboard_validator is None or not report.passed:
            print_report(report)
            return 0 if report.passed else 1

        if report.warning_count:
            for issue in report.issues:
                print(f"[{issue.level}] {issue.path} | {issue.message}", flush=True)

        script = args.storyboard_validator.expanduser().resolve()
        if not script.is_file():
            parser.error(f"找不到故事板校验脚本：{script}")

        command = [sys.executable, str(script), str(source.resolve())]
        if args.zip is not None:
            archive = args.zip.expanduser().resolve()
            if not archive.is_file() or archive.suffix.lower() != ".zip":
                parser.error(f"--zip 需指定存在的 ZIP 文件：{archive}")
            archive_report = validate_delivery(archive)
            if not archive_report.passed:
                print_report(archive_report)
                return 1
            for issue in archive_report.issues:
                print(f"[{issue.level}] {issue.path} | {issue.message}", flush=True)
            command.extend(("--zip", str(archive)))

        if args.allow_legacy:
            command.append("--allow-legacy")

        completed = subprocess.run(command, check=False)
        return completed.returncode
    except Exception as exc:
        print(f"\n[验收失败] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
