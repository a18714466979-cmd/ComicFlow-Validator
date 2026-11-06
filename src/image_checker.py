
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


# 支持的图片格式
SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


@dataclass(frozen=True)
class ImageCheckConfig:
    """图片验收配置"""

    target_ratio: tuple[int, int] | None = None
    ratio_tolerance: float = 0.005
    min_width: int = 0
    min_height: int = 0
    recursive: bool = True


@dataclass
class ImageCheckResult:
    """单张图片验收结果"""

    path: str
    status: str
    width: int | None = None
    height: int | None = None
    image_format: str | None = None
    issues: list[str] = field(default_factory=list)
    error: str | None = None


def validate_image(
    file_path: Path,
    config: ImageCheckConfig,
) -> ImageCheckResult:
    """检查单张图片是否完整以及是否符合尺寸要求"""

    try:
        # 第一次打开：检查文件结构
        with Image.open(file_path) as image:
            image.verify()

        # 第二次打开：实际解码全部像素
        with Image.open(file_path) as image:
            width, height = image.size
            image_format = image.format or "UNKNOWN"
            image.load()

    except Exception as exc:
        return ImageCheckResult(
            path=str(file_path),
            status="FAIL",
            error=f"{type(exc).__name__}: {exc}",
        )

    issues = []

    # 检查最低分辨率
    if config.min_width and width < config.min_width:
        issues.append(
            f"宽度不足：{width} < {config.min_width}"
        )

    if config.min_height and height < config.min_height:
        issues.append(
            f"高度不足：{height} < {config.min_height}"
        )

    # 检查宽高比例
    if config.target_ratio is not None:
        ratio_width, ratio_height = config.target_ratio

        expected_ratio = ratio_width / ratio_height
        actual_ratio = width / height

        deviation = abs(
            actual_ratio - expected_ratio
        ) / expected_ratio

        if deviation > config.ratio_tolerance:
            issues.append(
                f"比例不符：{width}:{height}，"
                f"要求 {ratio_width}:{ratio_height}"
            )

    return ImageCheckResult(
        path=str(file_path),
        status="PASS" if not issues else "FAIL",
        width=width,
        height=height,
        image_format=image_format,
        issues=issues,
    )


def scan_folder(
    folder: Path,
    config: ImageCheckConfig,
) -> list[ImageCheckResult]:
    """批量扫描文件夹中的图片"""

    if not folder.exists():
        raise FileNotFoundError(f"文件夹不存在：{folder}")

    if not folder.is_dir():
        raise NotADirectoryError(f"不是文件夹：{folder}")

    paths = (
        folder.rglob("*")
        if config.recursive
        else folder.iterdir()
    )

    image_paths = sorted(
        (
            path
            for path in paths
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: str(path).lower(),
    )

    return [
        validate_image(path, config)
        for path in image_paths
    ]


def parse_ratio(value: str) -> tuple[int, int]:
    """解析比例，例如 16:9"""

    try:
        width, height = map(int, value.split(":"))

        if width <= 0 or height <= 0:
            raise ValueError

        return width, height

    except ValueError:
        raise argparse.ArgumentTypeError(
            "比例格式错误，请使用 16:9 或 1:1"
        )


def parse_min_size(value: str) -> tuple[int, int]:
    """解析最低分辨率，例如 1920x1080"""

    try:
        width, height = map(
            int,
            value.lower().replace("×", "x").split("x"),
        )

        if width <= 0 or height <= 0:
            raise ValueError

        return width, height

    except ValueError:
        raise argparse.ArgumentTypeError(
            "分辨率格式错误，请使用 1920x1080"
        )


def print_report(
    results: list[ImageCheckResult],
) -> None:
    """输出验收报告"""

    passed = sum(
        result.status == "PASS"
        for result in results
    )

    failed = len(results) - passed

    print("\n" + "=" * 60)
    print("ComicFlow Validator - 图片验收报告")
    print("=" * 60)

    for result in results:
        if result.status == "PASS":
            print(
                f"[通过] {result.path} | "
                f"{result.width}x{result.height} | "
                f"{result.image_format}"
            )
        else:
            print(f"[异常] {result.path}")

            if result.error:
                print(f"       解码错误：{result.error}")

            for issue in result.issues:
                print(f"       {issue}")

    print("-" * 60)
    print(f"图片总数：{len(results)}")
    print(f"验收通过：{passed}")
    print(f"发现异常：{failed}")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ComicFlow 批量图片验收工具"
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="需要检查的图片文件夹",
    )

    parser.add_argument(
        "--ratio",
        help="目标宽高比，例如 16:9 或 1:1",
    )

    parser.add_argument(
        "--min-size",
        help="最低分辨率，例如 1920x1080",
    )

    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="只检查当前文件夹，不扫描子文件夹",
    )

    args = parser.parse_args()

    if not args.folder.is_dir():
        parser.error(f"文件夹不存在或不是目录：{args.folder}")

    try:
        target_ratio = (
            parse_ratio(args.ratio)
            if args.ratio
            else None
        )

        min_width, min_height = (
            parse_min_size(args.min_size)
            if args.min_size
            else (0, 0)
        )

    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    config = ImageCheckConfig(
        target_ratio=target_ratio,
        min_width=min_width,
        min_height=min_height,
        recursive=not args.no_recursive,
    )

    results = scan_folder(args.folder, config)

    if not results:
        print("没有找到支持的图片（PNG/JPG/JPEG/WEBP）")
        return 0

    print_report(results)

    return 1 if any(
        result.status == "FAIL"
        for result in results
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
