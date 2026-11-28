import subprocess
from threading import Event

import pytest
from PIL import Image

from src.asset_registry import sha256_file
from src.ecommerce_video import VideoError, resolve_ffmpeg
from src.media_catalog import MediaItem
from src.media_preview import iter_video_frames, load_preview


def test_preview_preserves_shape_and_exif_orientation(tmp_path):
    source = tmp_path / "portrait.jpg"
    image = Image.new("RGB", (200, 120), (140, 15, 31))
    exif = image.getexif()
    exif[0x0112] = 6
    image.save(source, exif=exif.tobytes())
    before = source.read_bytes()
    preview = load_preview(MediaItem("portrait", source), 100)
    assert preview.image.size == (60, 100)
    assert preview.duration_ms == preview.time_ms == 0
    assert source.read_bytes() == before


def test_missing_and_corrupt_files_are_localized_without_decoding_others(tmp_path):
    path = tmp_path / "wrong.png"
    with pytest.raises(FileNotFoundError, match=path.name):
        load_preview(MediaItem("missing", path), (100, 100))
    path.write_text("not a picture", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot decode the image"):
        load_preview(MediaItem("broken", path), 100)


def test_native_preview_does_not_present_modified_bytes_as_approved(tmp_path):
    path = tmp_path / "approved.png"
    Image.new("RGB", (120, 80), "tan").save(path)
    native = MediaItem("confirmed", path, expected_digest=sha256_file(path))
    assert load_preview(native, 200).image.getpixel((20, 20)) == (210, 180, 140)
    Image.new("RGB", (120, 80), "pink").save(path)
    with pytest.raises(ValueError, match="differs from the approved asset"):
        load_preview(native, 200)


def test_video_poster_skips_black_intro_and_plays_in_the_right_order(tmp_path):
    try:
        ffmpeg = resolve_ffmpeg()
    except VideoError as exc:
        pytest.skip(str(exc))
    path = tmp_path / "电影参考.mp4"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
         "-f", "lavfi", "-i", "color=black:s=160x288:r=12:d=0.75",
         "-f", "lavfi", "-i", "color=steelblue:s=160x288:r=12:d=1.25",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0", "-c:v", "mpeg4",
         "-threads", "2", "-pix_fmt", "yuv420p", str(path)],
        timeout=15, check=True, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    item = MediaItem("motion", path, media_type="video")
    poster = load_preview(item, 150)
    assert poster.duration_ms == 2000 and poster.time_ms >= 750
    assert poster.image.height == 150 and 80 <= poster.image.width <= 86
    assert poster.image.getpixel((40, 40)) != (0, 0, 0)
    black = load_preview(item, 150, 0)
    assert black.time_ms == 0 and black.image.getpixel((40, 40)) == (0, 0, 0)
    stop = Event()
    positions = []
    for frame, timestamp in iter_video_frames(item, (150, 150), start_ms=500, stop=stop):
        assert frame.height == 150 and 80 <= frame.width <= 86
        positions.append(timestamp)
        if len(positions) == 4:
            stop.set()
    assert positions == [500, 583, 667, 750]
