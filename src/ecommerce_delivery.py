"""Compose and validate independent groups for ecommerce video delivery."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
from math import ceil
import os
from pathlib import Path
import re
import runpy
from tempfile import TemporaryDirectory

from PIL import Image, ImageChops, ImageCms, ImageDraw, ImageFont, ImageOps, ImageStat

from .ecommerce_project import SHOT_ID, time_range
from .asset_registry import sha256_file
from .repair_package import write_delivery_zip, zip_fingerprints


WORKFLOW_VALIDATOR = (
    Path(__file__).resolve().parents[1]
    / "assets" / "workflow_validators" / "ecommerce" / "validate_storyboard_package.py"
)
PHOTO_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_IMAGE_BYTES = 64 * 1024**2
MAX_IMAGE_PIXELS = 40_000_000
BOARD_BACKGROUND = "#1e2935"
PRODUCT_BACKGROUND = "#e8e8e8"
PRODUCT_FILE = "06_product_asset_combined_16x9.png"


@dataclass(frozen=True)
class AssetNeed:
    key: str
    kind: str
    name: str
    status: str
    required: bool
    source: str = ""


@dataclass(frozen=True)
class StagedEcommerceDelivery:
    folder: Path
    visuals: tuple[Path, ...]
    fingerprint: str
    validator: Path


@dataclass(frozen=True)
class EcommerceDeliveryResult:
    output: Path
    sha256: str


def _image(path: Path) -> tuple[Image.Image, bytes, str]:
    path = Path(path)
    with path.open("rb") as stream:
        data = stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"{path.name} 超过 64 MiB，请选用适合交付的图片。")
    try:
        with Image.open(BytesIO(data)) as original:
            kind = original.format
            if kind not in PHOTO_FORMATS or getattr(original, "n_frames", 1) != 1:
                raise ValueError("请使用单帧 PNG、JPEG 或 WebP。")
            if original.width * original.height > MAX_IMAGE_PIXELS:
                raise ValueError("图片超过 4000 万像素。")
            original.load()
            return ImageOps.exif_transpose(original), data, kind
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError(f"{path.name} 无法完整解码：{exc}") from exc


def _rgb(image: Image.Image, background: str) -> Image.Image:
    alpha = image.convert("RGBA").getchannel("A") if "A" in image.getbands() or "transparency" in image.info else None
    color = image.convert("RGB")
    profile = image.info.get("icc_profile")
    if profile:
        try:
            managed = image if image.mode in {"RGB", "CMYK", "L"} else color
            color = ImageCms.profileToProfile(managed, BytesIO(profile), ImageCms.createProfile("sRGB"), outputMode="RGB")
        except (ImageCms.PyCMSError, OSError, ValueError) as exc:
            raise ValueError("提供的图片包含无法转换为 sRGB 的色彩配置。") from exc
    if alpha is not None:
        opaque = Image.new("RGB", color.size, background)
        opaque.paste(color, (0, 0), alpha)
        return opaque
    return color


def _inside(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    # Contain instead of fitting or cropping. Small source images stay small.
    return ImageOps.contain(image, (min(image.width, size[0]), min(image.height, size[1])),
                            method=Image.Resampling.LANCZOS)


def _place(canvas: Image.Image, picture: Image.Image, bounds: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = bounds
    scaled = _inside(picture, (right - left, bottom - top))
    canvas.paste(scaled, (left + (right - left - scaled.width) // 2,
                          top + (bottom - top - scaled.height) // 2))


def compose_product_sheet(references, output: Path) -> Path:
    """Lay out all supplied product views without cropping or inventing details."""
    paths = [Path(path) for path in references]
    if not paths:
        raise ValueError("制作产品总图前，请先提供至少一张产品原图。")
    if len(paths) > 24:
        raise ValueError("一张产品总图最多容纳 24 个参考视角。请合并明显重复的照片。")
    width, height = 1920, 1080
    margin, gutter = 14, 10
    aspects = []
    for path in paths:
        try:
            with Image.open(path) as image:
                transposed = image.getexif().get(274) in (5, 6, 7, 8)
                aspects.append(image.height / image.width if transposed else image.width / image.height)
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError(f"{path.name} 无法读取产品照片。") from exc

    def score(columns):
        rows = ceil(len(paths) / columns)
        tile_width = (width - 2 * margin - (columns - 1) * gutter) // columns
        tile_height = (height - 2 * margin - (rows - 1) * gutter) // rows
        return sum(min(tile_width, tile_height * aspect) * min(tile_height, tile_width / aspect)
                   for aspect in aspects)

    columns = max(range(1, len(paths) + 1), key=score)
    rows = ceil(len(paths) / columns)
    tile_width = (width - 2 * margin - (columns - 1) * gutter) // columns
    tile_height = (height - 2 * margin - (rows - 1) * gutter) // rows
    if min(tile_width, tile_height) < 140:
        raise ValueError("一张产品总图容纳不了这些视角。请合并明显重复的照片，再重新预览。")
    canvas = Image.new("RGB", (width, height), PRODUCT_BACKGROUND)
    for index, path in enumerate(paths):
        picture = _rgb(_image(path)[0], PRODUCT_BACKGROUND)
        row, column = divmod(index, columns)
        occupied = min(columns, len(paths) - row * columns)
        row_x = (width - (occupied * tile_width + (occupied - 1) * gutter)) // 2
        left, top = row_x + column * (tile_width + gutter), margin + row * (tile_height + gutter)
        _place(canvas, picture, (left, top, left + tile_width, top + tile_height))
    output = Path(output)
    canvas.save(output, format="PNG")
    return output


def board_layout(count: int) -> tuple[int, int]:
    """Columns and rows for a uniform group sheet, in left-to-right row order."""
    if type(count) is not int or not 1 <= count <= 10:
        raise ValueError("每张电商故事板需要 1 到 10 个分镜。")
    columns = 1 if count == 1 else 2 if count <= 6 else 3
    return columns, ceil(count / columns)


def _bounds(width, height, columns, rows, index):
    row, column = divmod(index, columns)
    return (column * width // columns, row * height // rows,
            (column + 1) * width // columns, (row + 1) * height // rows)


def _labels(board: Image.Image, shot_ids) -> Image.Image:
    if len(set(shot_ids)) != len(shot_ids) or any(not SHOT_ID.fullmatch(value) for value in shot_ids):
        raise ValueError("故事板存在重复或无效的格号。")
    columns, rows = board_layout(len(shot_ids))
    draw = ImageDraw.Draw(board)
    scale = max(19, round(board.width * 0.024))
    font = ImageFont.load_default(size=scale)
    pad = max(5, scale // 4)
    line = max(2, board.width // 390)
    for index, identity in enumerate(shot_ids):
        left, top, right, bottom = _bounds(board.width, board.height, columns, rows, index)
        draw.rectangle((left, top, right - 1, bottom - 1), outline="#e9edf1", width=line)
        x, y = left + 2 * pad, top + 2 * pad
        length = ceil(draw.textlength(identity, font=font))
        draw.rectangle((x - pad, y - pad, x + length + pad, y + scale + pad), fill="#101722")
        draw.text((x, y), identity, font=font, fill="#ffffff", anchor="lt")
    return board


def _is_grayscale(image: Image.Image) -> bool:
    red, green, blue = image.convert("RGB").split()
    pairs = ((red, green), (red, blue), (green, blue))
    return all(ImageStat.Stat(ImageChops.difference(left, right)).mean[0] <= 1.5 for left, right in pairs)


def _require_board(image: Image.Image, name: str) -> None:
    if image.width < 1080 or image.height < 1920 or image.width * 16 != image.height * 9:
        raise ValueError(f"{name} 应为 9:16 竖屏彩色总图，尺寸至少 1080×1920。")
    if _is_grayscale(image):
        raise ValueError(f"{name} 整体色彩接近灰度，请确认并提供清晰彩色故事板。")


def label_board_sheet(source: Path, output: Path, shot_ids) -> Path:
    """Label the uniform cells of a finished draft, for explicit visual review."""
    board, _, _ = _image(Path(source))
    _require_board(board, Path(source).name)
    output = Path(output)
    _labels(_rgb(board, BOARD_BACKGROUND), tuple(shot_ids)).save(output, format="PNG")
    return output


def _assemble_existing_panels(paths, shot_ids, output: Path) -> None:
    columns, rows = board_layout(len(shot_ids))
    size = (1080, 1920) if len(shot_ids) == 1 else (2160, 3840)
    canvas = Image.new("RGB", size, BOARD_BACKGROUND)
    margin = size[0] // 140
    for index, path in enumerate(paths):
        image, _, _ = _image(Path(path))
        if image.width * 16 != image.height * 9:
            raise ValueError(f"{Path(path).name} 的画面应为 9:16，不能自动裁掉原构图。")
        if _is_grayscale(image):
            raise ValueError(f"{Path(path).name} 整体色彩接近灰度，请换成清晰的彩色画面。")
        left, top, right, bottom = _bounds(*size, columns, rows, index)
        _place(canvas, _rgb(image, BOARD_BACKGROUND),
               (left + margin, top + max(margin, size[0] // 24), right - margin, bottom - margin))
    _labels(canvas, shot_ids).save(output, format="PNG")


def asset_audit(project) -> list[AssetNeed]:
    """Enumerate group inputs after shot and product checks have passed."""
    return _audit_for_groups(project, project.groups())


def _audit_for_groups(project, groups) -> list[AssetNeed]:
    audit = {}
    for group in groups:
        specifications = [
            (f"board:{group.id}", "board", group.id),
            (f"scene:{group.scene}", "scene", group.scene),
        ]
        specifications.extend((f"character:{name}", "character", name) for name in group.characters)
        if group.props:
            specifications.append((f"props:{group.id}", "props", "、".join(group.props)))
        for key, kind, name in specifications:
            if key in audit:
                continue
            registered = project.assets.get(key, "")
            if registered and Path(registered).is_file():
                status = "reuse"
            elif kind == "board" and all(
                (registered_panel := project.assets.get(f"panel:{shot.id}"))
                and Path(registered_panel).is_file() for shot in group.shots
            ):
                status = "derive"
            else:
                status = "generate"
            audit[key] = AssetNeed(key, kind, name, status, True, str(registered))
        if group.contains_product:
            audit["product"] = AssetNeed("product", "product", project.product_name, "derive", True)
    return list(audit.values())


def _inline(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", value).strip()


def _field(caption: str, value: str, empty: str = "无") -> str:
    return f"{caption}：{_inline(value) or empty}"


def _dialogue(project, shot) -> str:
    if project.video_has_audio and not shot.dialogue.strip():
        return "待确认原声"
    return project.dialogue_for(shot) if shot.has_dialogue else "无"


def render_group_prompt(project, group) -> str:
    """Write only generation-facing directions and source-language speech."""
    result = [
        "9:16 竖屏彩色写实广告成片，顺序以合并故事板为准。",
        f"场景：{group.scene}",
    ]
    if group.contains_product:
        result.append(f"产品：{project.product_name}。始终使用独立产品总图确认的外形、颜色、材料、品牌和可见状态。")
    if project.continuity.strip():
        result.append(_field("全组连续性", project.continuity))
    for shot in group.shots:
        result.extend(("", f"分镜 {shot.id}", _field("时间码", time_range(shot))))
        if group.contains_product:
            result.append(_field("产品入画", project.product_name if shot.contains_product else "无"))
        for caption, value in (
            ("景别", shot.size), ("机位/角度", shot.angle), ("运镜", shot.camera), ("画面/事件", shot.action),
            ("人物站位", shot.positions), ("视线/轴线", shot.axis),
            ("表演/情绪", shot.performance), ("对白", _dialogue(project, shot)),
            ("声音", shot.sound), ("画面文字", shot.visual_text), ("连续性", shot.continuity),
            ("视频模型约束", shot.constraints),
        ):
            if value.strip():
                result.append(_field(caption, value))
    result.extend(("", "连续使用批准的角色、服装、场景、道具和产品状态。逐镜保持人物站位、轴线与动作起止。"))
    return "\n".join(result) + "\n"


def render_group_text(project, group, filenames: dict[str, str]) -> str:
    """Generate the authoritative, fixed-label text for one self-contained group."""
    first, last = group.shots[0].id, group.shots[-1].id
    length = group.duration_ms
    result = [
        f"分组：{group.id}", f"覆盖段落：{first}-{last}",
        f"组时长：{length / 1000:g} 秒" if length is not None else "组时长：待剪辑",
        f"格数：{len(group.shots)}", "画面格式：9:16 竖屏高清彩色写实故事板", "故事板文件数：1",
        "", "连续性锁定", f"- 场景布局：{group.scene}",
        f"- 公共连续性：{_inline(project.continuity) or '见逐镜连续性字段'}",
        f"- 持续道具：{'、'.join(group.props) or '无'}",
    ]
    for shot in group.shots:
        result.extend(("", "分镜 " + shot.id, _field("时间码", time_range(shot))))
        for caption, value in (
            ("景别", shot.size), ("机位/角度", shot.angle), ("运镜", shot.camera), ("画面/事件", shot.action),
            ("人物站位", shot.positions), ("视线/轴线", shot.axis),
            ("表演/情绪", shot.performance), ("对白", _dialogue(project, shot)),
            ("声音", shot.sound), ("画面文字", shot.visual_text), ("连续性", shot.continuity),
            ("视频模型约束", shot.constraints),
        ):
            result.append(_field(caption, value))
    result.extend(("", "人物资产核对："))
    result.extend([f"- {name} → {filenames[f'character:{name}']}" for name in group.characters] or ["- 无"])
    result.extend(("", "资产清单",
                   f"- 场景：{group.scene} → {filenames[f'scene:{group.scene}']}",
                   f"- 道具：{filenames.get(f'props:{group.id}', '无')}"))
    product = f"{PRODUCT_FILE}（{project.product_name}·用户提供的 {len(project.product_refs)} 个参考视角/状态）"
    result.append("- 产品资产：" + (product if group.contains_product else "无"))
    result.append(f"- 故事板：{filenames[f'board:{group.id}']}")
    result.extend(("", "禁止事项", "- 不得改变人物身份、动作顺序、场景结构、轴线或已确认的产品外观。",
                   "- 不得复刻原演员的面貌。保持一个角色一张资产图。",
                   "- 单组全部格子保留在同一张彩色总图中。"))
    return "\n".join(result) + "\n"


def _copy_sheet(source: Path, destination: Path, *, board: bool = False) -> None:
    image, data, kind = _image(source)
    if board:
        _require_board(image, source.name)
    elif image.width * 9 != image.height * 16:
        raise ValueError(f"{source.name} 应为 16:9 资产图。")
    if kind == "PNG":
        with Image.open(BytesIO(data)) as original:
            if original.getexif().get(274, 1) == 1:
                destination.write_bytes(data)
                return
    _rgb(image, PRODUCT_BACKGROUND).save(destination, format="PNG")


def _asset_path(project, key: str) -> Path:
    path = project.assets.get(key)
    if not path or not Path(path).is_file():
        raise ValueError(f"缺少已确认资产：{key}")
    return Path(path)


def _validate(directory: Path, validator: Path, archive: Path | None = None) -> None:
    workflow = runpy.run_path(str(validator))
    errors, _warnings = workflow["validate"](directory)
    if archive is not None:
        errors.extend(workflow["validate_zip"](archive))
    if errors:
        raise ValueError("电商交付未通过结构校验：\n" + "\n".join(errors[:12]))


def _fingerprints(folder: Path) -> dict[str, str]:
    files = {}
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"预览目录有符号链接：{path.name}")
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = sha256_file(path)
    return files


def _fingerprint(files: dict[str, str]) -> str:
    return sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()


def stage_ecommerce_delivery(project, folder: Path, *, validator: Path | None = None) -> StagedEcommerceDelivery:
    """Materialize exact preview images and text in a dedicated empty folder."""
    folder = Path(folder).resolve()
    validator = Path(validator or WORKFLOW_VALIDATOR).resolve()
    if not validator.is_file():
        raise ValueError("找不到内置电商交付规则校验器。请使用完整安装包。")
    groups = project.groups()
    if not groups:
        raise ValueError("请先确认至少一个分镜和故事板分组。")
    if not project.shot_approval or project.shot_approval != project.shot_key():
        raise ValueError("请先核对并确认当前分镜清单和产品素材，再预览交付。")
    if project.video_has_audio:
        unchecked = [shot.id for group in groups for shot in group.shots if not shot.dialogue.strip()]
        if unchecked:
            raise ValueError("请逐镜确认原片对白。无对白填「无」，听不清填「[听辨不清]」："
                             + "、".join(unchecked))
    needs = _audit_for_groups(project, groups)
    incomplete = [entry.key for entry in needs if entry.required and entry.status == "generate"]
    if incomplete:
        raise ValueError("先确认缺失的资产：" + "、".join(incomplete))
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError("请选择空的预览目录。")
    visuals = []
    readme = [
        "电商信息流视频复刻", f"项目：{project.name}", f"分组数：{len(groups)}",
        "画面标准：每组一张 9:16 彩色故事板总图，配套 16:9 资产。",
        "对白保留源语言。精确标识、字幕和 HUD 须按批准文字叠加。",
        f"公共连续性：{_inline(project.continuity) or '见各组分镜'}",
        f"生成日期：{datetime.now(timezone(timedelta(hours=8))):%Y-%m-%d}",
    ]
    first_product = None
    for group in groups:
        group_folder = folder / f"{group.id}_{group.shots[0].id}-{group.shots[-1].id}"
        group_folder.mkdir()
        board_key = f"board:{group.id}"
        filenames = {board_key: f"01_storyboard_sheet_{len(group.shots)}panel_color_9x16.png"}
        board_file = group_folder / filenames[board_key]
        if project.assets.get(board_key) and Path(project.assets[board_key]).is_file():
            _copy_sheet(_asset_path(project, board_key), board_file, board=True)
        else:
            panel_paths = [_asset_path(project, f"panel:{shot.id}") for shot in group.shots]
            _assemble_existing_panels(panel_paths, tuple(shot.id for shot in group.shots), board_file)
        visuals.append(board_file)
        for index, name in enumerate(group.characters, 1):
            key = f"character:{name}"
            filenames[key] = f"02_character_{index:02d}_turnaround_16x9.png"
        if group.props:
            filenames[f"props:{group.id}"] = "04_props_16x9.png"
        filenames[f"scene:{group.scene}"] = "05_scene_angles_16x9.png"
        sources = {}
        for key, filename in filenames.items():
            if key != board_key:
                path = group_folder / filename
                source = _asset_path(project, key)
                digest = sha256_file(source)
                if digest in sources:
                    raise ValueError(f"以下不同用途的资产使用同一原图：{sources[digest]} 和 {key}")
                sources[digest] = key
                _copy_sheet(source, path)
                visuals.append(path)
        if group.contains_product:
            path = group_folder / PRODUCT_FILE
            if first_product is None:
                first_product = compose_product_sheet(project.product_refs, path)
            else:
                path.write_bytes(first_product.read_bytes())
            visuals.append(path)
        details = group_folder / f"{group.id}_shot_details.txt"
        details.write_text(render_group_text(project, group, filenames), encoding="utf-8-sig")
        prompt = group_folder / "prompts" / "SD2_prompt.txt"
        prompt.parent.mkdir()
        prompt.write_text(render_group_prompt(project, group), encoding="utf-8-sig")
        readme.extend(("", f"{group_folder.name} · {group.scene}",
                       *(f"- {file.relative_to(group_folder).as_posix()}"
                         for file in sorted(group_folder.rglob("*")) if file.is_file())))
    (folder / "README.txt").write_text("\n".join(readme) + "\n", encoding="utf-8-sig")
    _validate(folder, validator)
    return StagedEcommerceDelivery(folder, tuple(visuals), _fingerprint(_fingerprints(folder)), validator)


def publish_ecommerce_delivery(staged: StagedEcommerceDelivery, output: Path, *, visual_approval: str) -> EcommerceDeliveryResult:
    """Publish only the approved preview bytes, after structural and ZIP checks."""
    files = _fingerprints(staged.folder)
    if not visual_approval or visual_approval != staged.fingerprint or _fingerprint(files) != staged.fingerprint:
        raise ValueError("请逐张核对最新预览后再确认打包。预览有改动时需重新生成。")
    output = Path(output).resolve()
    if output.suffix.lower() != ".zip" or output.is_relative_to(staged.folder) or not output.parent.is_dir():
        raise ValueError("请在预览目录以外选择 ZIP 保存位置。")
    if output.exists():
        raise FileExistsError(f"目标已存在，请选择新文件名：{output.name}")
    with TemporaryDirectory(prefix="comicflow-ecommerce-", dir=output.parent) as temporary:
        draft = Path(temporary) / output.name
        write_delivery_zip(staged.folder, draft)
        _validate(staged.folder, staged.validator, draft)
        if zip_fingerprints(draft) != files or _fingerprints(staged.folder) != files:
            raise ValueError("预览文件与 ZIP 成员或 SHA-256 不一致。")
        digest = sha256_file(draft)
        if os.name == "nt":
            draft.rename(output)
        else:
            os.link(draft, output)
    return EcommerceDeliveryResult(output, digest)
