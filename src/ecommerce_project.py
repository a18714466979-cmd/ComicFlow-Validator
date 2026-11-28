"""Local project data and editing rules for ecommerce reference-video production."""

import json
import re
from dataclasses import asdict, dataclass, field, fields
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .asset_registry import sha256_file
from .production_project import atomic_text


PROJECT_FORMAT = "comicflow-ecommerce"
PROJECT_VERSION = 1
MAX_PROJECT_BYTES = 16 * 1024 * 1024
MAX_REFERENCE_BYTES = 32 * 1024 * 1024
MAX_REFERENCE_PIXELS = 32_000_000
MAX_SHOTS = 500
MAX_GROUP_MS = 15_000
MIXED_LIMIT = 6
ACTION_LIMIT = 10
SHOT_ID = re.compile(r"[0-9]{1,4}[A-Z]?(?:-[0-9]{1,4})?\Z")
NO_DIALOGUE = frozenset({"", "无", "none"})
IMAGE_TYPES = {"PNG", "JPEG", "WEBP"}


@dataclass(frozen=True)
class EcommerceShot:
    id: str
    start_ms: int | None = None
    end_ms: int | None = None
    scene: str = ""
    size: str = ""
    angle: str = ""
    camera: str = ""
    action: str = ""
    positions: str = ""
    performance: str = ""
    dialogue: str = ""
    sound: str = ""
    continuity: str = ""
    constraints: str = ""
    characters: tuple[str, ...] = ()
    props: tuple[str, ...] = ()
    contains_product: bool = False
    scene_cut: bool = False
    visual_text: str = ""
    axis: str = ""

    @property
    def has_dialogue(self) -> bool:
        return self.dialogue.strip().casefold() not in NO_DIALOGUE


@dataclass(frozen=True)
class AdGroup:
    id: str
    shots: tuple[EcommerceShot, ...]
    scene: str
    start_ms: int | None
    end_ms: int | None

    @property
    def duration_ms(self) -> int | None:
        if self.start_ms is None or self.end_ms is None:
            return None
        return self.end_ms - self.start_ms

    @property
    def characters(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(name for shot in self.shots for name in shot.characters))

    @property
    def props(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(name for shot in self.shots for name in shot.props))

    @property
    def contains_product(self) -> bool:
        return any(shot.contains_product for shot in self.shots)


@dataclass
class EcommerceProject:
    name: str
    video_path: str = ""
    duration_ms: int | None = None
    product_name: str = ""
    product_refs: list[str] = field(default_factory=list)
    product_required: bool = True
    product_reviewed: bool = False
    shots: list[EcommerceShot] = field(default_factory=list)
    continuity: str = ""
    assets: dict[str, str] = field(default_factory=dict)
    visual_approved: str = ""
    source_product_name: str = ""
    source_transcript: str = ""
    shot_approval: str = ""
    video_has_audio: bool = False
    video_width: int | None = None
    video_height: int | None = None
    project_id: str = field(default_factory=lambda: uuid4().hex)

    @classmethod
    def open(cls, path: str | Path):
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_PROJECT_BYTES + 1)
        if len(raw) > MAX_PROJECT_BYTES:
            raise ValueError("电商项目超过 16 MiB。")
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (ValueError, RecursionError) as error:
            raise ValueError("请选择 UTF-8 编码的 电商项目。") from error
        if (not isinstance(payload, dict) or payload.get("format") != PROJECT_FORMAT
                or type(payload.get("version")) is not int or payload["version"] != PROJECT_VERSION):
            raise ValueError("电商项目格式或版本不兼容。")
        data = {key: value for key, value in payload.items() if key not in {"format", "version"}}
        if data.keys() - {entry.name for entry in fields(cls)} or "name" not in data:
            raise ValueError("电商项目字段无效。")
        data["shots"] = _read_shot_records(data.get("shots", []))
        project = cls(**data)
        project._validate_fields()
        return project

    def save(self, path: str | Path) -> None:
        payload = self._payload()
        content = json.dumps({"format": PROJECT_FORMAT, "version": PROJECT_VERSION, **payload},
                             ensure_ascii=False, indent=2) + "\n"
        if len(content.encode("utf-8")) > MAX_PROJECT_BYTES:
            raise ValueError("电商项目超过 16 MiB。")
        atomic_text(Path(path), content)

    def check_product(self) -> tuple[Path, ...]:
        """Allow reference inspection up front, and require verified product views to start production."""
        if not self.product_required and not any(shot.contains_product for shot in self.shots):
            return ()
        if not self.product_name.strip():
            raise ValueError("请先填写要制作的产品名称。")
        if not self.product_refs:
            raise ValueError("请先导入自己产品的清晰照片。包括剧情用到的角度、包装或手持状态。")
        paths = tuple(Path(path) for path in self.product_refs)
        for path in paths:
            validate_image(path)
        if not self.product_reviewed:
            raise ValueError("请确认已提供展示动作所需的产品角度和状态。缺少的角度需要补图。")
        return paths

    def groups(self, *, require_timing=False) -> list[AdGroup]:
        """Build independent groups under scene, source-span and panel limits."""
        shots = _validated_shots(self.shots)
        self.check_product()
        if not shots:
            raise ValueError("请先登记要纳入制作的分镜。")
        if self.product_required and not any(shot.contains_product for shot in shots):
            raise ValueError("请在实际出现产品的分镜标记 contains_product。")

        groups, pending, known_start, spoken, last_timed_end = [], [], None, False, None
        product_names = {name.strip().casefold() for name in (self.product_name, self.source_product_name) if name.strip()}
        for shot in shots:
            if not shot.scene.strip() or not shot.action.strip():
                raise ValueError(f"分镜 {shot.id} 缺少场景名称或画面动作。")
            if shot.contains_product and any(name.casefold() in product_names for name in shot.props):
                raise ValueError(f"分镜 {shot.id} 把产品列入了普通道具，请在 props 中移除产品名称。")
            if shot.start_ms is None:
                if require_timing:
                    raise ValueError(f"分镜 {shot.id} 缺少确认的起止时间。")
            else:
                if shot.end_ms - shot.start_ms > MAX_GROUP_MS:
                    raise ValueError(f"分镜 {shot.id} 超过 15 秒，请按实际动作切点手动拆分。")
                if last_timed_end is not None and shot.start_ms < last_timed_end:
                    raise ValueError(f"分镜 {shot.id} 的时间顺序与前镜重叠，请核对源视频。")
                if self.duration_ms is not None and shot.end_ms > self.duration_ms:
                    raise ValueError(f"分镜 {shot.id} 超出源视频时长。")
                last_timed_end = shot.end_ms

            # A silent entry can stand for unchecked audio when the source has a track.
            speech_possible = shot.has_dialogue or (self.video_has_audio and not shot.dialogue.strip())
            limit = MIXED_LIMIT if spoken or speech_possible else ACTION_LIMIT
            if pending and (
                shot.scene_cut or shot.scene != pending[-1].scene
                or (known_start is not None and shot.end_ms is not None and shot.end_ms - known_start > MAX_GROUP_MS)
                or len(pending) >= limit
            ):
                groups.append(_group(len(groups) + 1, pending))
                pending, known_start, spoken = [], None, False
            pending.append(shot)
            if known_start is None:
                known_start = shot.start_ms
            spoken = spoken or speech_possible
        groups.append(_group(len(groups) + 1, pending))
        return groups

    def dialogue_for(self, shot: EcommerceShot) -> str:
        """Keep source speech intact except for a configured literal product-name replacement."""
        old, new = self.source_product_name.strip(), self.product_name.strip()
        if not old or not new or old == new:
            return shot.dialogue
        pattern = re.escape(old)
        if old[0].isascii() and old[0].isalnum():
            pattern = r"(?<![A-Za-z0-9_])" + pattern
        if old[-1].isascii() and old[-1].isalnum():
            pattern += r"(?![A-Za-z0-9_])"
        return re.sub(pattern, lambda _match: new, shot.dialogue)

    def shot_key(self) -> str:
        """Bind shot approval to source revision, transcript, product references and exact shot content."""
        payload = self._payload()
        paths = self.check_product()
        for name in ("assets", "visual_approved", "shot_approval"):
            del payload[name]
        payload["product_ref_bytes"] = [(str(path), sha256_file(path)) for path in paths]
        if self.video_path:
            video = Path(self.video_path)
            stat = video.stat()
            if not video.is_file():
                raise ValueError("源视频文件不存在或已移动，请重新导入。")
            payload["video_revision"] = (stat.st_size, stat.st_mtime_ns)
        return _digest(payload)

    def review_key(self) -> str:
        """Bind visual approval to the exact imported output-asset bytes as well as the shot revision."""
        return _digest({"shots": self.shot_key(),
                        "assets": {key: sha256_file(Path(path)) for key, path in sorted(self.assets.items())}})

    def _payload(self) -> dict:
        shots = self._validate_fields()
        return {**asdict(self), "shots": [asdict(shot) for shot in shots]}

    def _validate_fields(self) -> list[EcommerceShot]:
        text = ("name", "video_path", "product_name", "continuity", "visual_approved", "source_product_name",
                "source_transcript", "shot_approval", "project_id")
        for key in text:
            value = getattr(self, key)
            if not isinstance(value, str) or "\0" in value:
                raise ValueError(f"电商项目的 {key} 字段无效。")
        if not self.name.strip() or any(mark in self.name for mark in "\r\n"):
            raise ValueError("请提供单行项目名称。")
        for key in ("product_name", "source_product_name"):
            if any(mark in getattr(self, key) for mark in "\r\n"):
                raise ValueError("产品名称请使用单行文字。")
        for key in ("video_width", "video_height", "duration_ms"):
            value = getattr(self, key)
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"电商项目的 {key} 必须是正整数。")
        for key in ("product_required", "product_reviewed", "video_has_audio"):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"电商项目的 {key} 必须是布尔值。")
        if not isinstance(self.product_refs, list) or not all(_valid_path(item) for item in self.product_refs):
            raise ValueError("产品参考图需要使用有效的本地文件路径。")
        if not isinstance(self.assets, dict) or not all(
            isinstance(key, str) and key.strip() and _valid_path(path) for key, path in self.assets.items()
        ):
            raise ValueError("交付资产需要使用有效的名称和本地文件路径。")
        return _validated_shots(self.shots)


def _valid_path(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and all(mark not in value for mark in "\0\r\n")


def _group(index: int, shots: list[EcommerceShot]) -> AdGroup:
    complete = all(shot.start_ms is not None for shot in shots)
    return AdGroup(f"SB{index:02d}", tuple(shots), shots[0].scene,
                   shots[0].start_ms if complete else None, shots[-1].end_ms if complete else None)


def _digest(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_image(path: Path) -> tuple[int, int]:
    """Verify a bounded single-frame color-capable reference image and return its size."""
    path = Path(path)
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_REFERENCE_BYTES:
            raise ValueError(f"图片不存在或超过 32 MiB。{path.name}")
        with Image.open(path) as image:
            if (image.format not in IMAGE_TYPES or image.width * image.height > MAX_REFERENCE_PIXELS
                    or getattr(image, "n_frames", 1) != 1):
                raise ValueError(f"请选择单帧 PNG、JPEG 或 WebP，最多 3200 万像素。{path.name}")
            image.load()
            return image.size
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError(f"无法完整读取图片：{path.name}") from error


def _validated_shots(shots) -> list[EcommerceShot]:
    if not isinstance(shots, (list, tuple)) or len(shots) > MAX_SHOTS:
        raise ValueError(f"分镜清单必须为数组，最多 {MAX_SHOTS} 条。")
    if any(not isinstance(item, EcommerceShot) for item in shots):
        raise ValueError("分镜请使用有效的分镜记录。")
    return _read_shot_records([asdict(item) for item in shots])


def _read_shot_records(records) -> list[EcommerceShot]:
    if not isinstance(records, list) or len(records) > MAX_SHOTS:
        raise ValueError(f"分镜清单必须为数组，最多 {MAX_SHOTS} 条。")
    known = {entry.name for entry in fields(EcommerceShot)}
    structured = {"start_ms", "end_ms", "contains_product", "scene_cut", "characters", "props"}
    seen, shots = set(), []
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict) or record.keys() - known or not isinstance(record.get("id"), str):
            raise ValueError(f"第 {index} 条分镜的字段或编号无效。")
        raw_id = record["id"]
        if not SHOT_ID.fullmatch(raw_id) or raw_id in seen:
            raise ValueError(f"第 {index} 条分镜编号重复或格式无效，请使用 01A 或 01A-01。")
        data = dict(record)
        for key, value in record.items():
            if key not in structured and (not isinstance(value, str) or "\0" in value or len(value) > 16_000):
                raise ValueError(f"分镜 {raw_id} 的 {key} 无效。")
        if any(mark in record.get("scene", "") for mark in "\r\n"):
            raise ValueError(f"分镜 {raw_id} 的场景名称需要单行文字。")
        start, end = record.get("start_ms"), record.get("end_ms")
        if (start is not None or end is not None) and (
            type(start) is not int or type(end) is not int or not 0 <= start < end
        ):
            raise ValueError(f"分镜 {raw_id} 的时间码必须同时提供非负毫秒起点及更晚的终点，或一起留空。")
        for key in ("contains_product", "scene_cut"):
            if key in record and type(record[key]) is not bool:
                raise ValueError(f"分镜 {raw_id} 的 {key} 必须是布尔值。")
        for key in ("characters", "props"):
            value = record.get(key, ())
            if not isinstance(value, (list, tuple)) or any(
                not isinstance(name, str) or not name.strip() or len(name) > 180
                or any(mark in name for mark in "\0\r\n") for name in value
            ):
                raise ValueError(f"分镜 {raw_id} 的 {key} 需要使用名称列表。")
            data[key] = tuple(dict.fromkeys(name.strip() for name in value))
        if "scene" in data:
            data["scene"] = data["scene"].strip()
        seen.add(raw_id)
        shots.append(EcommerceShot(**data))
    return shots


def parse_shots(text: str) -> list[EcommerceShot]:
    if len(text.encode("utf-8")) > MAX_PROJECT_BYTES:
        raise ValueError("分镜清单超过 16 MiB。")
    try:
        records = json.loads(text.removeprefix("\ufeff"))
    except (ValueError, RecursionError) as error:
        raise ValueError("分镜清单需要有效的 JSON 数组。") from error
    return _read_shot_records(records)


def render_shots(shots) -> str:
    return json.dumps([asdict(shot) for shot in _validated_shots(shots)], ensure_ascii=False, indent=2) + "\n"


def format_time(value: int) -> str:
    minutes, remainder = divmod(value, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def time_range(shot: EcommerceShot) -> str:
    if shot.start_ms is None or shot.end_ms is None:
        return "待剪辑"
    return f"{format_time(shot.start_ms)}-{format_time(shot.end_ms)}"
