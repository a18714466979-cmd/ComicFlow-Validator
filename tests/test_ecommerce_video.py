import subprocess

import pytest

from src.ecommerce_video import (
    VideoError, VideoShot, analyze_video, format_timestamp, inspect_video, preview_frame, preview_sheet,
    resolve_ffmpeg,
)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    try:
        ffmpeg = resolve_ffmpeg()
    except VideoError as exc:
        pytest.skip(str(exc))
    folder = tmp_path_factory.mktemp("ecommerce-video")
    reference = folder / "电商 参考.mp4"
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=white:s=180x320:d=1",
        "-f", "lavfi", "-i", "color=black:s=180x320:d=1", "-f", "lavfi", "-i", "color=cyan:s=180x320:d=1",
        "-f", "lavfi", "-i", "sine=duration=3", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-map", "3:a", "-c:v", "mpeg4", "-c:a", "aac", str(reference),
    ], check=True, timeout=30)
    return ffmpeg, reference


def test_commercial_video_cuts_and_previews_match_source_order(media):
    ffmpeg, reference = media
    result = analyze_video(reference, ffmpeg=ffmpeg)
    assert result.info.has_audio and result.info.is_vertical and result.info.duration_ms == 3000
    assert (result.info.width, result.info.height) == (180, 320)
    assert result.shots == (VideoShot(0, 1000), VideoShot(1000, 2000), VideoShot(2000, 3000))
    assert format_timestamp(result.shots[1].preview_ms) == "00:00:01.499"
    assert preview_frame(reference, 500, ffmpeg=ffmpeg).size == (360, 640)

    palette = preview_sheet(reference, result.shots, ffmpeg=ffmpeg, labels=("01A", "01B", "01C"))
    first, second, third = [palette.getpixel((x, 165)) for x in (123, 369, 615)]
    assert min(first) > 230 and max(second) < 25
    assert third[0] < 25 and min(third[1:]) > 230
    with pytest.raises(VideoError, match="1 至 2"):
        preview_sheet(reference, result.shots, ffmpeg=ffmpeg, maximum=2)


def test_video_metadata_reads_display_rotation_and_rejects_invalid_clip(media):
    ffmpeg, reference = media
    rotated = reference.with_name("旋转.mp4")
    flags = subprocess.run([ffmpeg, "-hide_banner", "-h", "full"], capture_output=True, check=True, timeout=30)
    input_flags = ["-display_rotation:v:0", "90"] if b"-display_rotation" in flags.stdout else []
    output_flags = [] if input_flags else ["-metadata:s:v:0", "rotate=90"]
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", *input_flags, "-i", str(reference),
                    *output_flags, "-c", "copy", str(rotated)], check=True, timeout=30)
    info = inspect_video(rotated, ffmpeg=ffmpeg)
    assert info.has_audio and not info.is_vertical and (info.width, info.height) == (320, 180)
    invalid = reference.with_name("无效.mp4")
    invalid.write_bytes(b"not a media container")
    with pytest.raises(VideoError, match="无法解码"):
        inspect_video(invalid, ffmpeg=ffmpeg)
