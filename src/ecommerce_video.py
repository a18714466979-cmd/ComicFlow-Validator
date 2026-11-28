"""Inspect local commercial references and suggest timed visual cut points."""

import re
import sys
import shutil
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


MAX_DURATION_MS = 10 * 60 * 1000
MAX_PIXELS = 16_777_216
MAX_SHOT_SUGGESTIONS = 300
VIDEO_FILTER = "*.mp4 *.mov *.m4v *.mkv *.webm *.avi *.wmv *.mpg *.mpeg *.ts *.flv"
DEMUXERS = "mov,matroska,webm,avi,asf,mpegts,mpeg,mpegvideo,flv,m4v"
DURATION = re.compile(r"(?m)^  Duration: (\d+):(\d{2}):(\d{2}(?:\.\d+)?),")
SHOWINFO_SIZE = re.compile(r"(?m)^\[Parsed_showinfo_\d+ @ [^\]\r\n]+\][^\r\n]*\bs:(\d+)x(\d+)\b")
SHOWINFO_TIME = re.compile(r"(?m)^\[Parsed_showinfo_\d+ @ [^\]\r\n]+\][^\r\n]*\bpts_time:([+-]?[\d.]+(?:[eE][+-]?\d+)?)")
AUDIO_STREAM = re.compile(r"(?m)^  Stream #0:\d+(?:\[[^\r\n\]]+\])?(?:\([^\r\n\)]+\))?: Audio:")


class VideoError(ValueError):
    """Bad or unsupported media, or unavailable FFmpeg."""


@dataclass(frozen=True)
class VideoInfo:
    duration_ms: int
    width: int
    height: int
    has_audio: bool

    @property
    def is_vertical(self):
        return self.width * 16 == self.height * 9


@dataclass(frozen=True)
class VideoShot:
    start_ms: int
    end_ms: int

    @property
    def preview_ms(self):
        return (self.start_ms + self.end_ms - 1) // 2


@dataclass(frozen=True)
class VideoAnalysis:
    info: VideoInfo
    shots: tuple[VideoShot, ...]


def resolve_ffmpeg(explicit=None) -> str:
    """Resolve a local executable without installation or network access."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise VideoError("指定的 FFmpeg 程序不存在。")
        return str(path)
    if getattr(sys, "frozen", False):
        executable = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        bundled = Path(__file__).resolve().parents[1] / "tools" / executable
        if bundled.is_file():
            return str(bundled)
    installed = shutil.which("ffmpeg")
    if installed:
        return installed
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, OSError, RuntimeError) as exc:
        raise VideoError("找不到 FFmpeg。请完成软件安装，或选择电脑中的 ffmpeg.exe。") from exc


def _seconds(ms):
    return f"{ms // 1000}.{ms % 1000:03d}"


def format_timestamp(ms):
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, fraction = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{fraction:03d}"


def _run(path, ffmpeg, filters, *, seek=None, frames=False, timeout=30):
    path = Path(path).resolve()
    if not path.is_file():
        raise VideoError("请选择一个可以读取的本地参考视频。")
    cmd = [resolve_ffmpeg(ffmpeg), "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info",
           "-xerror", "-filter_threads", "2", "-threads", "2", "-max_pixels", str(MAX_PIXELS),
           "-protocol_whitelist", "file,pipe", "-format_whitelist", DEMUXERS]
    if seek is not None:
        cmd.extend(("-ss", _seconds(seek)))
    cmd.extend(("-i", str(path), "-map", "0:V:0", "-an", "-sn", "-dn", "-vf", filters))
    if frames:
        cmd.extend(("-frames:v", "1", "-c:v", "png", "-f", "image2pipe", "pipe:1"))
    else:
        cmd.extend(("-t", _seconds(MAX_DURATION_MS), "-fps_mode", "passthrough", "-f", "null", "-"))
    try:
        process = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise VideoError("视频解码超时。可先在本机导出较短的参考片段再导入。") from exc
    except OSError as exc:
        raise VideoError("无法启动 FFmpeg。请检查安装，或选择电脑中的 FFmpeg 程序。") from exc
    log = process.stderr.decode("utf-8", errors="replace")
    if process.returncode:
        if "matches no streams" in log:
            raise VideoError("此文件没有可播放的视频轨。")
        if "max_pixels" in log:
            raise VideoError("参考视频的像素尺寸超出解码上限。")
        raise VideoError("无法解码此参考视频。请检查文件能否正常播放，或转成 MP4 后重试。")
    return process.stdout, log


def _scale(maximum):
    width, height = maximum
    return f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"


def inspect_video(path, *, ffmpeg=None) -> VideoInfo:
    """Read source metadata and confirm at least one video frame decodes."""
    data, log = _run(path, ffmpeg, "showinfo," + _scale((32, 32)), frames=True)
    duration, size = DURATION.search(log), SHOWINFO_SIZE.search(log)
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or size is None:
        raise VideoError("未读到可用的视频画面。")
    if duration is None:
        raise VideoError("无法读取参考视频的时长。请转成有完整时间线的 MP4。")
    hours, minutes, seconds = duration.groups()
    total_ms = round(3_600_000 * int(hours) + 60_000 * int(minutes) + Decimal(seconds) * 1000)
    if not 0 < total_ms <= MAX_DURATION_MS:
        raise VideoError("参考视频时长须大于零且不超过 10 分钟。")
    width, height = map(int, size.groups())
    return VideoInfo(total_ms, width, height, bool(AUDIO_STREAM.search(log)))


def _ranges(duration_ms, cuts):
    points = [0]
    for point in sorted(set(cuts)):
        if point - points[-1] >= 120 and duration_ms - point >= 120:
            points.append(point)
    if len(points) > MAX_SHOT_SUGGESTIONS:
        raise VideoError("检测到的切点过多。请将参考视频切成较短片段再试。")
    points.append(duration_ms)
    return tuple(VideoShot(start, end) for start, end in zip(points, points[1:]))


def analyze_video(path, *, ffmpeg=None) -> VideoAnalysis:
    """Suggest hard cuts using decoded frame changes, before editorial review."""
    info = inspect_video(path, ffmpeg=ffmpeg)
    filter_graph = _scale((320, 320)) + ",select=gt(scene\\,0.34),showinfo"
    _, log = _run(path, ffmpeg, filter_graph, timeout=150)
    cuts = (round(Decimal(match) * 1000) for match in SHOWINFO_TIME.findall(log))
    return VideoAnalysis(info, _ranges(info.duration_ms, cuts))


def preview_frame(path, timestamp_ms, *, ffmpeg=None, maximum=(360, 640)) -> Image.Image:
    """Extract an uncropped, aspect-preserving preview within the requested bounds."""
    if type(timestamp_ms) is not int or not 0 <= timestamp_ms <= MAX_DURATION_MS:
        raise VideoError("预览时间无效。")
    if len(maximum) != 2 or any(type(size) is not int or not 16 <= size <= 1600 for size in maximum):
        raise VideoError("预览图片尺寸无效。")
    data, _ = _run(path, ffmpeg, _scale(maximum), seek=timestamp_ms, frames=True)
    if not data and timestamp_ms:
        data, _ = _run(path, ffmpeg, _scale(maximum), seek=max(0, timestamp_ms - 80), frames=True)
    try:
        with Image.open(BytesIO(data)) as image:
            return image.convert("RGB")
    except OSError as exc:
        raise VideoError("未能取得这个时间附近的视频画面。") from exc


def preview_sheet(path, shots, *, ffmpeg=None, maximum=12, labels=None) -> Image.Image:
    """Render a compact numbered preview sheet in the order of the supplied shots."""
    shots = tuple(shots)
    if labels is None:
        labels = [f"{number:02d}" for number in range(1, len(shots) + 1)]
    limit = min(maximum, 16)
    if not 1 <= len(shots) <= limit or len(labels) != len(shots):
        raise VideoError(f"一次请传入 1 至 {limit} 个有效镜头，并为每个镜头提供一个标签。")
    if any(not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", label) for label in labels):
        raise VideoError("预览标签须为不超过 24 个字符的分镜编号。")
    columns = min(4, len(shots))
    rows = (len(shots) + columns - 1) // columns
    tile_width, tile_height, header = 246, 300, 46
    background = Image.new("RGB", (columns * tile_width, rows * tile_height), "#17222e")
    draw = ImageDraw.Draw(background)
    font = ImageFont.load_default(size=15)
    for index, (shot, label) in enumerate(zip(shots, labels)):
        x, y = index % columns * tile_width, index // columns * tile_height
        timestamp = shot.preview_ms
        image = preview_frame(path, timestamp, ffmpeg=ffmpeg, maximum=(tile_width - 12, tile_height - header - 8))
        draw.rectangle((x + 3, y + 3, x + tile_width - 4, y + tile_height - 4), outline="#3d556c", width=1)
        draw.text((x + 8, y + 5), label, font=font, fill="#edf3f8")
        draw.text((x + 8, y + 24), format_timestamp(timestamp), font=font, fill="#c7d8eb")
        background.paste(image, (x + (tile_width - image.width) // 2, y + header + (tile_height - header - image.height) // 2))
    return background
