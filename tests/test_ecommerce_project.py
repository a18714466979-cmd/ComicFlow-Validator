from dataclasses import replace

import pytest
from PIL import Image

from src.ecommerce_project import (
    EcommerceProject, EcommerceShot, parse_shots, render_shots, time_range,
)


def shot(number, start=None, end=None, **fields):
    return EcommerceShot(f"{number:02d}A", start_ms=start, end_ms=end,
                         action="转身拿到桌上物件", **{"scene": "室内", **fields})


def test_grouping_respects_duration_scene_and_explicit_cut():
    cuts = [
        shot(1, 0, 7000), shot(2, 7000, 15_000), shot(3, 15_000, 15_801),
        shot(4, 15_801, 16_000, scene="室外"), shot(5, 16_000, 16_500, scene="室外", scene_cut=True),
    ]
    groups = EcommerceProject("短片", product_required=False, duration_ms=16_500, shots=cuts).groups()
    assert [[item.id for item in group.shots] for group in groups] == [["01A", "02A"], ["03A"], ["04A"], ["05A"]]
    assert [group.duration_ms for group in groups] == [15_000, 801, 199, 500]
    assert groups[2].scene == groups[3].scene == "室外"


def test_action_only_and_speech_capacity_are_distinct_without_manufacturing_times():
    shots = [shot(index, dialogue="无") for index in range(1, 12)]
    project = EcommerceProject("短片", product_required=False, shots=shots, video_has_audio=True)
    assert [len(group.shots) for group in project.groups()] == [10, 1]
    assert project.groups()[0].duration_ms is None
    assert time_range(project.shots[0]) == "待剪辑"

    project.shots[2] = replace(project.shots[2], dialogue="Wait… no, look.")
    assert [len(group.shots) for group in project.groups()] == [6, 5]
    project.shots[2] = replace(project.shots[2], dialogue="")
    assert [len(group.shots) for group in project.groups()] == [6, 5]
    with pytest.raises(ValueError, match="确认的起止时间"):
        project.groups(require_timing=True)


def test_a_confirmed_oversized_shot_overlap_and_out_of_bounds_are_rejected():
    project = EcommerceProject("短片", product_required=False, shots=[shot(1, 1, 15_002)])
    with pytest.raises(ValueError, match="手动拆分"):
        project.groups()
    project.shots = [shot(1, 5_000, 6_000), shot(2, 5_900, 6_100)]
    with pytest.raises(ValueError, match="重叠"):
        project.groups()
    project.duration_ms = 5_999
    with pytest.raises(ValueError, match="源视频时长"):
        project.groups()


def test_commercial_product_gate_checks_file_coverage_and_marked_shots(tmp_path):
    project = EcommerceProject("短片", shots=[shot(1)])
    with pytest.raises(ValueError, match="产品名称"):
        project.check_product()
    project.product_name = "新产品"
    with pytest.raises(ValueError, match="清晰照片"):
        project.check_product()
    ref = tmp_path / "正面.png"
    ref.write_bytes(b"invalid PNG")
    project.product_refs = [str(ref)]
    with pytest.raises(ValueError, match="完整读取"):
        project.check_product()
    Image.new("RGB", (16, 9), "red").save(ref)
    with pytest.raises(ValueError, match="角度和状态"):
        project.check_product()
    project.product_reviewed = True
    assert project.check_product() == (ref,)
    with pytest.raises(ValueError, match="contains_product"):
        project.groups()
    project.shots[0] = replace(project.shots[0], contains_product=True)
    assert project.groups()[0].contains_product
    project.shots[0] = replace(project.shots[0], props=("新产品",))
    with pytest.raises(ValueError, match="普通道具"):
        project.groups()
    project.product_required = False
    project.product_refs.clear()
    with pytest.raises(ValueError, match="清晰照片"):
        project.groups()


def test_save_load_and_fingerprints_bind_approvals_to_exact_output_and_product_images(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"source spec fixture")
    reference = tmp_path / "ref.png"
    canvas = tmp_path / "board.png"
    Image.new("RGB", (16, 9), "red").save(reference)
    Image.new("RGB", (9, 16), "white").save(canvas)
    project = EcommerceProject("中文项目", video_path=str(video), product_name="替换款",
                               source_product_name="旧款", product_required=True, product_reviewed=True,
                               product_refs=[str(reference)], source_transcript="  旧款真的有吗？  ",
                               shots=[shot(1, 0, 1000, contains_product=True, dialogue="旧款真的有吗？",
                                           characters=("甲", " 乙 ", "甲"), props=("笔",))])
    project.assets["board:SB01"] = str(canvas)
    project.shot_approval = project.shot_key()
    project.visual_approved = project.review_key()
    path = tmp_path / "短片.cfecom"
    project.save(path)
    saved = EcommerceProject.open(path)
    assert saved.shot_key() == project.shot_approval
    assert saved.review_key() == project.visual_approved
    assert saved.source_transcript == "  旧款真的有吗？  "
    assert saved.dialogue_for(saved.shots[0]) == "替换款真的有吗？"
    assert saved.shots[0].dialogue == "旧款真的有吗？"
    assert saved.groups()[0].characters == ("甲", "乙")
    Image.new("RGB", (9, 16), "black").save(canvas)
    assert saved.shot_key() == project.shot_approval
    assert saved.review_key() != project.visual_approved
    Image.new("RGB", (16, 9), "green").save(reference)
    assert saved.shot_key() != project.shot_approval


def test_shot_json_preserves_source_words_and_rejects_bad_numbers():
    first = shot(1, 0, 1150, dialogue=" Ace! Wait… Acer?  This is Ace.  ")
    project = EcommerceProject("短片", source_product_name="Ace", product_name="Box")
    parsed = parse_shots(render_shots([first]))
    assert parsed == [first]
    assert time_range(first) == "00:00.000-00:01.150"
    assert project.dialogue_for(first) == " Box! Wait… Acer?  This is Box.  "
    with pytest.raises(ValueError, match="编号"):
        parse_shots('[{"id":"../wrong"}]')
    with pytest.raises(ValueError, match="编号"):
        parse_shots('[{"id":"01A"},{"id":"01A"}]')
    with pytest.raises(ValueError, match="时间码"):
        parse_shots('[{"id":"01A","start_ms":true,"end_ms":20}]')
