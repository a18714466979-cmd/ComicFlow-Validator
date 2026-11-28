import json
from dataclasses import replace
from zipfile import ZipFile

import pytest

from src.action_reference_library import (
    ReferenceError, filter_references, make_reference, refs_from_records, refs_to_records,
)
from src.action_reference_starters import STARTER_LINKS
from src.image_api import TEXT
from src.production_drafting import SD2_TASK, build_context
from src.production_export import publish_project
from src.production_images import image_prompt
from src.production_project import ProductionProject
from test_production_project import production, validator


YT = "https://www.youtube.com/watch?v=Abcd_123-Xy"
YOUKU = "https://v.youku.com/v_show/id_XMTIzNDU2==.html"
TENCENT = "https://v.qq.com/x/page/k0089abc123.html"


@pytest.mark.parametrize("url,canonical,platform", [
    ("https://youtu.be/Abcd_123-Xy?si=example", YT, "YouTube"),
    ("https://m.youtube.com/shorts/Abcd_123-Xy", YT, "YouTube"),
    ("https://v.youku.com/v_show/id_XMTIzNDU2%3D%3D.html?spm=example", YOUKU, "Youku"),
    ("https://m.v.qq.com/x/m/play?vid=k0089abc123&share_ref=sample", TENCENT, "Tencent Video"),
    ("https://v.qq.com/x/cover/abc123/k0089abc123.html", "https://v.qq.com/x/cover/abc123/k0089abc123.html", "Tencent Video"),
])
def test_bookmark_only_keeps_recognized_playback_page(url, canonical, platform):
    ref = make_reference("示例", url, "42", "00:53")
    assert ref.url == canonical and ref.platform == platform
    assert (ref.start, ref.end) == ("00:42", "00:53")
    assert ref.playback_url() == (canonical + "&t=42s" if platform == "YouTube" else canonical)


@pytest.mark.parametrize("url", [
    "http://youtu.be/Abcd_123-Xy",
    "file:///a.mp4",
    "https://youtube.com.example/watch?v=Abcd_123-Xy",
    "https://example.com@youtube.com/watch?v=Abcd_123-Xy",
    "https://youtu.be:8443/Abcd_123-Xy",
    "https://www.youtube.com/redirect?q=other",
    YT + "&v=other",
    "https://v.qq.com/redirect?target=other",
    "https://v.youku.com/movie.mp4",
    "https://v.qq.com\\@other.com/x/page/k0089abc123.html",
])
def test_bookmark_and_playback_reject_unknown_routes(url):
    with pytest.raises(ReferenceError):
        make_reference("片段", url)
    with pytest.raises(ReferenceError):
        replace(make_reference("片段", YT), url=url).playback_url()


def test_shared_start_and_editing_preserve_id_and_range():
    from_share = make_reference("Sample", "https://youtu.be/Abcd_123-Xy?t=1h2m3s", end="01:03:00")
    assert from_share.start == "01:02:03"
    assert from_share.playback_url() == YT + "&t=3723s"
    edited = make_reference("剪辑点", from_share.url, "00:20", "00:45", "留出反应镜头", ref_id=from_share.id)
    assert edited.id == from_share.id and edited.playback_url() == YT + "&t=20s"
    assert make_reference("片段", YT, end="12").start == "00:00"
    assert make_reference("片段", YT).start == ""


@pytest.mark.parametrize("start,end", [("12:60", ""), ("1:60:00", ""), ("-1", ""), ("10", "9"), ("", "0"), ("0.5", "")])
def test_invalid_ranges_have_bilingual_errors(start, end):
    with pytest.raises(ReferenceError) as caught:
        make_reference("片段", YT, start, end)
    assert str(caught.value) and caught.value.english


def test_library_roundtrip_is_private_to_project_and_searchable(tmp_path):
    path = tmp_path / "试用.cfproject"
    project = ProductionProject("试用", "EP01", "SB01")
    project.save(path)
    assert "action_references" not in json.loads(path.read_text(encoding="utf-8"))
    baseline = project.fingerprint()
    project.structure_review = baseline
    refs = [make_reference("走廊转场", YT, "0:03", notes="Reverse angle 反应镜头"),
            make_reference("动作场面", YOUKU, notes="走廊逆光")]
    project.action_references = refs_to_records(refs)
    project.save(path)
    opened = ProductionProject.open(path)
    assert refs_from_records(opened.action_references) == refs
    assert opened.structure_review == opened.fingerprint() == baseline
    assert opened.action_cards == opened.shots == []
    assert filter_references(refs, "走廊") == refs
    assert filter_references(refs, "reverse 走廊") == [refs[0]]
    assert filter_references(refs, "走廊", "Youku") == [refs[1]]
    assert filter_references(refs, "00:03") == [refs[0]]


def test_invalid_persisted_entries_fail_before_overwriting_project(tmp_path):
    path = tmp_path / "sample.cfproject"
    project = ProductionProject("demo", "EP01", "SB01")
    ref = make_reference("镜头", TENCENT)
    project.action_references = refs_to_records([ref])
    project.save(path)
    original = path.read_bytes()
    project.action_references *= 2
    with pytest.raises(ReferenceError, match="重复"):
        project.save(path)
    assert path.read_bytes() == original
    data = json.loads(original)
    data["action_references"][0]["url"] = "https://example.com/other"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ReferenceError):
        ProductionProject.open(path)


def test_curated_links_are_unique_bilingual_official_playback_pages():
    refs = [make_reference(zh, url) for zh, en, url in STARTER_LINKS]
    assert refs and all(zh.strip() and en.strip() for zh, en, _ in STARTER_LINKS)
    assert len({ref.url for ref in refs}) == len(refs)
    assert all(ref.url == url for ref, (_, _, url) in zip(refs, STARTER_LINKS))


def test_private_notes_and_urls_stay_out_of_model_inputs_and_delivery_zip(production, validator, tmp_path):
    project = ProductionProject.open(production)
    project.structure_review = project.fingerprint()
    reference = make_reference("PRIVATE_SOURCE_TITLE", YT, "42", notes="PRIVATE_CAMERA_NOTE")
    project.action_references = refs_to_records([reference])
    project.save(production)
    project = ProductionProject.open(production)
    shot = project.shots[0]
    _, text_input = build_context(project, project.sources[0], SD2_TASK, 1, 1, shot.id)
    visual_input = image_prompt(project, "故事板", shot.id, TEXT)
    private = [reference.title, reference.url, reference.notes, reference.id]
    assert all(item not in text_input and item not in visual_input for item in private)

    result = publish_project(project, production, validator, tmp_path / "storyboard.zip")
    assert result.exit_code == 0, result.report
    with ZipFile(result.output) as archive:
        assert archive.testzip() is None
        assert not any("action_reference" in name or name.endswith(".cfproject") for name in archive.namelist())
        for name in archive.namelist():
            data = archive.read(name)
            assert all(item.encode() not in data for item in private)
