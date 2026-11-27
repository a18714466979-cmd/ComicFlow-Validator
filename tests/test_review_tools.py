from zipfile import ZipFile

import pytest
from PIL import Image

from src.review_tools_dialog import boundary_type, inspect_image, nonconsecutive_groups, shot_fields
from src.shot_review import load_shots
from src.storyboard_review import ReviewResult, index_members


def test_image_inspection_reports_original_file_and_aspect(tmp_path):
    image = tmp_path / "wide.png"
    Image.new("RGB", (1600, 900), "red").save(image)
    facts, preview = inspect_image(image)

    assert (facts.width, facts.height, facts.ratio, facts.image_format) == (1600, 900, "16:9", "PNG")
    assert facts.size_bytes == image.stat().st_size and facts.is_wide
    assert preview.size == (1024, 576) and preview.getpixel((0, 0)) == (255, 0, 0, 255)

    image = tmp_path / "square.jpg"
    Image.new("RGB", (300, 300), "blue").save(image)
    facts, _ = inspect_image(image)
    assert facts.ratio == "1:1" and not facts.is_wide


def test_image_inspection_requires_decodable_static_images(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"preview")
    with pytest.raises(OSError):
        inspect_image(broken)

    animated = tmp_path / "animated.png"
    first = Image.new("RGB", (16, 9), "red")
    first.save(animated, save_all=True, append_images=[Image.new("RGB", (16, 9), "blue")])
    with pytest.raises(ValueError, match="静态图片"):
        inspect_image(animated)


def test_cut_review_uses_shot_records_and_marks_page_and_group_boundaries(tmp_path):
    archive = tmp_path / "review.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("SB01/SB01_shot_details.txt", (
            "分镜 SB01-01\n景别：近景\n机位/角度：平视\n可见范围：门口\n"
            "分镜 SB01-02\n景别：全景\n机位空间：门内\n动作起止：转身离开\n"
            "场景局部对应表：\n"
            "- SB01-01 | scene.png | 局部01 | 门口 | 向前\n"
            "- SB01-02 | scene.png | 局部02 | 门内 | 向后\n\n"
            "实际画面窗口：\n"
            "- SB01-01 | storyboard_1.png | 0,0,160,90 | scene.png | 0,0,160,90\n"
            "- SB01-02 | storyboard_2.png | 0,0,160,90 | scene.png | 0,0,160,90\n"
        ))
        package.writestr("SB01/SD2_prompt.txt", (
            "分镜编号：SB01-01\n景别：中景\n动作：打开门\n"
            "分镜编号：SB01-02\n动作：离开\n"
        ))
        package.writestr("SB01/scene.png", b"not required for record extraction")
        package.writestr("SB01/storyboard_1.png", b"first board page")
        package.writestr("SB01/storyboard_2.png", b"second board page")
        package.writestr("SB03/SB03_shot_details.txt", "分镜 SB03-01\n连续性：从户内转到户外。\n")
        members = index_members(package)

    first, second, third = load_shots(ReviewResult(0, "", archive, members, []))

    assert shot_fields(first) == {"景别": "近景", "机位/角度": "平视", "可见范围": "门口", "动作起止": "打开门"}
    assert shot_fields(second)["动作起止"] == "转身离开"
    assert first.board_box == (0, 0, 160, 90)
    assert boundary_type(first, second) == "page"
    assert boundary_type(second, third) == "group"
    assert nonconsecutive_groups(second, third)
