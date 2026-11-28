"""A portable, local project for authoring one SD2 storyboard group."""

import json
import re
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import ntpath
from pathlib import Path, PureWindowsPath
from shutil import copyfile
from tempfile import NamedTemporaryFile
from uuid import uuid4

from PIL import Image

from .asset_registry import Asset, sha256_file
from .production_rules import CAMERA_ACTION_FIELD, CHINESE, ENGLISH, rule_revision


RULE_VERSION = ENGLISH
GROUP_FIELDS = (
    "分组状态", "覆盖段落", "内容类型", "打斗节奏依据", "对白规格", "本组进入状态", "本组退出状态",
    "连续性锁定", "场景资产模式", "场景清单", "场景身份判定", "人物判定", "人物资产表",
    "补充正打核对", "场景拼接对应表", "尾组说明", "对白容量拆组说明", "图片预算核对",
    "武器轴线核对", "镜头节奏核对", "空间合理性核对", "群像差异化核对", "追击节奏核对",
    "动作辅助标注", "资产清单",
)
GROUP_OPTIONAL = {"打斗节奏依据", "补充正打核对", "场景拼接对应表", "尾组说明", "对白容量拆组说明", "图片预算核对", "动作辅助标注", "资产清单"}
CHINESE_TEXT_REQUIRED = ("分组状态", "覆盖段落", "对白规格", "本组进入状态", "本组退出状态", "连续性锁定")
CHINESE_TEXT_FOLLOWUP = (
    "组间镜头衔接核对", "景别衔接核对", "尾组说明", "主角判定", "武器轴线核对",
    "镜头节奏核对", "空间合理性核对", "群像差异化核对", "追击节奏核对",
)
CHINESE_TEXT_FIELDS = CHINESE_TEXT_REQUIRED + CHINESE_TEXT_FOLLOWUP
CHINESE_TEXT_OPTIONAL = set(CHINESE_TEXT_FOLLOWUP)
CHINESE_CHARACTER_FIELDS = (
    "主角清单", "主角资产映射", "混合人物资产映射", "人物资产核对", "人物资产分表", "其他人物合集",
)
PROMPT_FIELDS = ("场景/总体状态", "公共限制")
SHOT_FIELDS = (
    "景别", "机位/角度", "机位空间", "可见范围", "运镜", "画面/事件", "人物站位", "动作起止",
    "唯一角色数量锁定", "本格新增叙事功能", "情绪/表演", "环境威胁/视觉副线", "声音", "声源位置",
    "连续性", "视频模型约束", "成片动作", "场景/环境", "成片声音", CAMERA_ACTION_FIELD,
)
OPTIONAL_SHOT_FIELDS = {"成片动作", "成片声音", CAMERA_ACTION_FIELD}
ACTIONS = ("直接复用", "必要规范排版", "局部补缺/修复", "新生成")


def identifier() -> str:
    return uuid4().hex


def checked_name(name: str) -> str:
    invalid = [char for char in name if char in '<>:"/\\|?*' or ord(char) < 32]
    reserved = ntpath.isreserved(name) if hasattr(ntpath, "isreserved") else PureWindowsPath(name).is_reserved()
    if not name or invalid or name.endswith((".", " ")) or reserved:
        raise ValueError(f"交付文件名不适用于 Windows：{name}")
    return name


def atomic_text(path: Path, content: str) -> None:
    with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class ApprovedSource:
    id: str
    name: str
    version: str
    text: str


@dataclass(frozen=True)
class ApprovedLine:
    id: str
    speaker: str
    text: str
    source: str
    sentence_ends: tuple[int, ...] = ()


@dataclass
class Shot:
    id: str = field(default_factory=identifier)
    source: str = ""
    anchor: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    dialogue: list[tuple[str, int, int]] = field(default_factory=list)
    plate: str = ""
    scene: str = ""
    plate_note: str = ""


@dataclass(frozen=True)
class ProjectImage:
    id: str
    version: str
    filename: str
    digest: str
    width: int
    height: int
    origin: str
    action: str
    reason: str
    inspection: str
    originals: tuple[str, ...] = ()
    reference_only: bool = False


@dataclass
class ProductionProject:
    name: str
    episode: str
    group: str
    sources: list[ApprovedSource] = field(default_factory=list)
    lines: list[ApprovedLine] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    images: list[ProjectImage] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)
    prompt: dict[str, str] = field(default_factory=dict)
    structure_review: str = ""
    version: int = 1
    rules: str = RULE_VERSION
    dialogue_scope: dict[str, list[int]] | None = None
    previous_group: str = ""
    text_drafts: list[dict] = field(default_factory=list)
    image_jobs: list[dict] = field(default_factory=list)
    layout: dict = field(default_factory=dict)
    pending_shots: list[Shot] = field(default_factory=list)
    handoffs: dict[str, dict] = field(default_factory=dict)
    action_cards: list[dict] = field(default_factory=list)

    @classmethod
    def open(cls, path: Path):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if payload.get("version") != 1 or payload.get("rules") not in (ENGLISH, CHINESE):
            raise ValueError("项目格式或制作规则版本不兼容。")
        payload["sources"] = [ApprovedSource(**item) for item in payload.get("sources", [])]
        payload["lines"] = [ApprovedLine(**{**item, "sentence_ends": tuple(item.get("sentence_ends", ()))})
                            for item in payload.get("lines", [])]
        payload["shots"] = [Shot(**item) for item in payload.get("shots", [])]
        payload["pending_shots"] = [Shot(**item) for item in payload.get("pending_shots", [])]
        payload["images"] = [ProjectImage(**item) for item in payload.get("images", [])]
        project = cls(**payload)
        project.check_identity()
        return project

    @property
    def group_fields(self):
        if self.rules == CHINESE:
            return tuple(dict.fromkeys((*CHINESE_TEXT_FIELDS, "场景资产模式", "场景清单",
                                        *CHINESE_CHARACTER_FIELDS,
                                        *(key for key in GROUP_FIELDS if key in self.notes))))
        return GROUP_FIELDS

    def check_identity(self) -> None:
        if self.rules not in (ENGLISH, CHINESE):
            raise ValueError("项目的制作规则版本不兼容。")
        if not re.fullmatch(r"SB\d{2,}", self.group):
            raise ValueError("组号请使用 SB01 这类格式。")
        if any(char in self.name + self.episode for char in "|\r\n"):
            raise ValueError("项目名和集次需要使用单行文本。")
        for label, records in (("镜头", self.shots + self.pending_shots), ("对白", self.lines), ("剧本", self.sources), ("图像", self.images)):
            ids = [item.id for item in records]
            if len(ids) != len(set(ids)):
                raise ValueError(f"项目有重复的{label} ID。")
        names = [checked_name(image.filename).casefold() for image in self.images]
        if len(names) != len(set(names)):
            raise ValueError("交付图像文件名重复。")

    def save(self, path: Path) -> None:
        self.check_identity()
        payload = asdict(self)
        if not self.action_cards:
            del payload["action_cards"]
        atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def import_source(self, name: str, version: str, text: str) -> ApprovedSource:
        if not version.strip() or not text.strip() or any(char in name + version for char in "|\r\n"):
            raise ValueError("请填写剧本版本并导入有内容的批准剧本。")
        old = next((item for item in self.sources if (item.name, item.version) == (name, version.strip())), None)
        if old:
            if old.text != text:
                raise ValueError("此剧本版本已有不同内容，请填写新版本号。")
            return old
        source = ApprovedSource(identifier(), name, version.strip(), text)
        self.sources.append(source)
        return source

    def import_dialogue(self, source: ApprovedSource, content: str, *, replace_source_lines: bool = False) -> None:
        entries = json.loads(content.removeprefix("\ufeff"))
        if not isinstance(entries, list):
            raise ValueError("批准对白 JSON 必须是数组，每条包含 id、speaker 和完整原文 text。")
        before = {item.id: item for item in self.lines}
        updated = before.copy()
        supplied = {}
        for item in entries:
            if not isinstance(item, dict) or not all(isinstance(item.get(key), str) for key in ("id", "speaker", "text")):
                raise ValueError("对白记录必须填写 id、speaker 和 text。")
            line = ApprovedLine(item["id"], item["speaker"].strip(), item["text"].strip(), source.id)
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", line.id) or not line.speaker or not line.text:
                raise ValueError(f"对白缺少有效的 ID、说话人或原文：{line.id}")
            if (any(char in line.speaker for char in "|：:\r\n") or "\r" in line.text or "\n" in line.text
                    or not re.search(r"[\u3400-\u9fff]", line.speaker)):
                raise ValueError(f"{line.id} 需要中文说话人和单行原文。")
            if line.text not in source.text:
                raise ValueError(f"{line.id} 原文未在所选批准剧本中找到。")
            if line.id in supplied:
                raise ValueError(f"{line.id} 重复了。同一源 ID 的多句请使用 sentence_ends。")
            ends = item.get("sentence_ends", [])
            if (not isinstance(ends, list) or any(type(end) is not int for end in ends)
                    or ends and (ends != sorted(set(ends)) or ends[0] <= 0 or ends[-1] != len(line.text))):
                raise ValueError(f"{line.id} 的整句终点需按字符位置递增，最后一项为完整原文长度。")
            old = updated.get(line.id)
            if old and (old.speaker, old.text, old.source) != (line.speaker, line.text, line.source):
                raise ValueError(f"{line.id} 已绑定不同的批准原文或来源版本，请分配新对白 ID。")
            supplied[line.id] = ApprovedLine(line.id, line.speaker, line.text, line.source, tuple(ends))
            updated[line.id] = supplied[line.id]
        if replace_source_lines:
            removed = {item.id for item in self.lines if item.source == source.id} - supplied.keys()
            if any(identity in removed for shot in self.shots + self.pending_shots for identity, _, _ in shot.dialogue):
                raise ValueError("请先移除镜头里对这些对白 ID 的引用，再更新本组对白清单。")
            for identity in removed:
                del updated[identity]
        chosen_order = iter(supplied.values())
        self.lines = [next(chosen_order) if replace_source_lines and item.source == source.id else item
                      for item in updated.values()]
        if self.lines != list(before.values()):
            self.dialogue_scope = None
            self.previous_group = ""

    def import_image(self, project_path: Path, path: Path, filename: str, *, action: str,
                     reason: str, inspection: str, version: str = "1", approved: Asset | None = None,
                     originals: tuple[str, ...] = (), reference_only: bool = False, origin_label: str = "") -> ProjectImage:
        filename = checked_name(filename.strip())
        if Path(filename).suffix.lower() != ".png" or action not in ACTIONS or not version.strip():
            raise ValueError("请选择 PNG、批准版本和正式素材处理方式。")
        if not re.fullmatch(r"[^@|；;\s]+", approved.version if approved else version.strip()):
            raise ValueError("素材版本号请使用 R1、V2 这类无空格的单一标记。")
        if any(image.filename.casefold() == filename.casefold() for image in self.images):
            raise ValueError("该交付文件名已存在，请先移除旧绑定。")
        if approved and sha256_file(path) != approved.sha256:
            raise ValueError("登记库中的原图已变化，请按指纹找回批准版本。")
        with Image.open(path) as image:
            if image.format != "PNG" or image.width * image.height > 32_000_000:
                raise ValueError("请导入可复核的正式 PNG，最多 3200 万像素。")
            image.verify()
        with Image.open(path) as image:
            image.load()
            width, height = image.size
        digest = sha256_file(path)
        if approved and digest != approved.sha256:
            raise ValueError("原文件内容与已批准版本不一致。")
        if action in {"必要规范排版", "局部补缺/修复"} and not originals:
            raise ValueError("排版或局部修复需要指向项目内已导入的批准原图。")
        if any(key not in {image.id for image in self.images} for key in originals):
            raise ValueError("引用的项目原图不存在。")

        data_path = project_path.with_suffix(".assets")
        data_path.mkdir(exist_ok=True)
        stored = data_path / (digest + ".png")
        if not stored.exists():
            with NamedTemporaryFile(dir=data_path, delete=False) as file:
                temporary = Path(file.name)
            try:
                copyfile(path, temporary)
                if sha256_file(temporary) != digest:
                    raise ValueError("导入时原图发生变化，请重新导入。")
                temporary.replace(stored)
            finally:
                temporary.unlink(missing_ok=True)
        if sha256_file(stored) != digest:
            raise ValueError("项目内的原图副本与指纹不符。")

        asset = ProjectImage(identifier(), approved.version if approved else version.strip(), filename, digest,
                             width, height, approved.origin if approved else origin_label or str(path.resolve()),
                             action, reason.strip(), inspection.strip(), originals, reference_only)
        self.images.append(asset)
        return asset

    def checked_image(self, project_path: Path, image: ProjectImage) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", image.digest):
            raise ValueError("图片指纹格式无效。")
        path = project_path.with_suffix(".assets") / (image.digest + ".png")
        if not path.is_file() or sha256_file(path) != image.digest:
            raise ValueError(f"无法核对批准图像：{image.filename}")
        return path

    def move_shot(self, index: int, offset: int) -> int:
        target = index + offset
        if not (0 <= index < len(self.shots) and 0 <= target < len(self.shots)):
            return index
        self.shots[index], self.shots[target] = self.shots[target], self.shots[index]
        return target

    def fingerprint(self) -> str:
        payload = asdict(self)
        if self.rules == ENGLISH:
            payload["delivery_rule_revision"] = rule_revision(self.rules)
        del payload["structure_review"]
        del payload["text_drafts"]
        del payload["handoffs"]
        del payload["action_cards"]
        for key in ("layout", "pending_shots"):
            if not payload[key]:
                del payload[key]
        jobs = payload.pop("image_jobs")
        published = [job for job in jobs if job.get("approved_image")]
        if published:
            payload["image_jobs"] = published
        if self.dialogue_scope is None:
            del payload["dialogue_scope"]
        if not self.previous_group:
            del payload["previous_group"]
        for line in payload["lines"]:
            if not line["sentence_ends"]:
                del line["sentence_ends"]
        return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def impacts(self) -> tuple[str, ...]:
        if self.structure_review == self.fingerprint():
            return ()
        linked = {shot.plate for shot in self.shots}
        media = [image.filename for image in self.images if not image.reference_only
                 and ("storyboard" in image.filename.lower() or image.id in linked)]
        deferred = ("待制作分镜.txt",) if self.pending_shots else ()
        return (*media, f"{self.group}_shot_details.txt", "SD2_prompt.txt", "README.txt", *deferred)
