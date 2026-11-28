"""Decode bounded local image previews and visual video playback frames."""

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

from .asset_registry import sha256_file
from .ecommerce_video import DEMUXERS, MAX_PIXELS, VideoError, inspect_video, preview_frame, resolve_ffmpeg


MAX_IMAGE_PIXELS = 64_000_000
MAX_PREVIEW_SIDE = 1600
PLAYBACK_FPS = 12


@dataclass(frozen=True)
class Preview:
    image: Image.Image
    duration_ms: int = 0
    time_ms: int = 0


def _bounds(size):
    bounds = (size, size) if type(size) is int else tuple(size)
    if len(bounds) != 2 or any(type(side) is not int or side < 16 for side in bounds):
        raise ValueError("预览尺寸无效 / Invalid preview size.")
    return tuple(min(side, MAX_PREVIEW_SIDE) for side in bounds)


def _image(path, bounds):
    try:
        with Image.open(path) as original:
            if original.width * original.height > MAX_IMAGE_PIXELS:
                raise ValueError("图片尺寸超出预览上限 / Image dimensions exceed the preview limit.")
            original.draft("RGB", bounds)
            image = ImageOps.exif_transpose(original)
            image.thumbnail(bounds, Image.Resampling.LANCZOS)
            return image.convert("RGBA" if image.has_transparency_data else "RGB")
    except Image.DecompressionBombError as exc:
        raise ValueError("图片尺寸超出预览上限 / Image dimensions exceed the preview limit.") from exc
    except OSError as exc:
        raise ValueError("无法读取图片，请检查原件 / Cannot decode the image. Check the source file.") from exc


@lru_cache(maxsize=128)
def _video_info(path, signature):
    return inspect_video(path)


def _inspect(path):
    state = path.stat()
    return _video_info(path, (state.st_mtime_ns, state.st_size, state.st_ctime_ns))


def _source(item):
    path = Path(item.path)
    if not path.is_file():
        raise FileNotFoundError(f"找不到素材 / Media file is missing: {item.display_name}")
    if item.expected_digest and sha256_file(path) != item.expected_digest:
        raise ValueError(f"文件与批准原件不符 / File differs from the approved asset: {item.display_name}")
    return path


def _usable(image):
    sample = image.convert("L")
    sample.thumbnail((64, 64), Image.Resampling.BOX)
    light = ImageStat.Stat(sample)
    return 18 < light.mean[0] < 244 or light.stddev[0] > 12


def _video_frame(path, bounds, time_ms, duration):
    requested = min(max(0, int(time_ms)), duration - 1)
    try:
        return preview_frame(path, requested, maximum=bounds), requested
    except VideoError:
        # Video metadata describes the interval's end, past the last actual frame.
        if requested < duration - 1000:
            raise
        for candidate in (max(0, duration - delta) for delta in (250, 500, 1000)):
            if candidate >= requested:
                continue
            try:
                return preview_frame(path, candidate, maximum=bounds), candidate
            except VideoError:
                continue
        raise


def load_preview(item, size, time_ms=None) -> Preview:
    """Return an uncropped thumbnail and video timing, sampling beyond fades when useful."""
    bounds = _bounds(size)
    path = _source(item)
    if item.media_type == "image":
        return Preview(_image(path, bounds))
    if item.media_type != "video":
        raise ValueError("不支持此媒体类型 / Unsupported media type.")
    duration = _inspect(path).duration_ms
    if time_ms is not None:
        image, actual = _video_frame(path, bounds, time_ms, duration)
        return Preview(image, duration, actual)

    first = None
    for candidate in dict.fromkeys((0, duration // 5, duration // 2, duration * 4 // 5)):
        image, actual = _video_frame(path, bounds, candidate, duration)
        frame = Preview(image, duration, actual)
        if _usable(image):
            return frame
        if first is None:
            first = frame
    return first


def _playback_size(info, bounds):
    ratio = min(bounds[0] / info.width, bounds[1] / info.height, 1)
    return (max(1, round(info.width * ratio)), max(1, round(info.height * ratio)))


def iter_video_frames(item, size, start_ms=0, *, stop=None):
    """Yield scaled RGB video frames at 12 fps for the local preview transport."""
    if stop is not None and stop.is_set():
        return
    if item.media_type != "video":
        raise ValueError("请选择视频 / Choose a video file.")
    path = _source(item)
    info = _inspect(path)
    width, height = _playback_size(info, _bounds(size))
    seek = min(max(0, int(start_ms)), info.duration_ms - 1)
    maximum_ms = info.duration_ms - seek
    count = width * height * 3
    filters = f"fps={PLAYBACK_FPS},scale={width}:{height},setsar=1"
    cmd = [resolve_ffmpeg(), "-hide_banner", "-nostdin", "-nostats", "-loglevel", "error", "-xerror",
           "-filter_threads", "2", "-threads", "2", "-max_pixels", str(MAX_PIXELS),
           "-protocol_whitelist", "file,pipe", "-format_whitelist", DEMUXERS, "-ss", f"{seek / 1000:.3f}",
           "-i", str(path.resolve()), "-map", "0:V:0", "-an", "-sn", "-dn", "-vf", filters,
           "-t", f"{maximum_ms / 1000:.3f}", "-c:v", "rawvideo", "-threads:v", "1",
           "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    try:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
            try:
                index = 0
                while stop is None or not stop.is_set():
                    data = process.stdout.read(count)
                    if len(data) != count:
                        if process.wait(timeout=5) or not index:
                            raise VideoError("无法播放该视频片段 / Cannot play the selected video interval.")
                        break
                    time_ms = min(info.duration_ms - 1, seek + round(index * 1000 / PLAYBACK_FPS))
                    if stop is not None and stop.is_set():
                        break
                    yield Image.frombytes("RGB", (width, height), data), time_ms
                    index += 1
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoError("无法读取视频以供预览 / Cannot decode video for preview.") from exc
