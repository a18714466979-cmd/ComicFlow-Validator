from zipfile import ZipFile

from src.shot_review import load_shots, pixel_selection, shot_summary
from src.storyboard_review import ReviewResult, index_members


def test_shot_review_links_records_by_shot_not_prompt_position(tmp_path):
    archive = tmp_path / "review.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("EP/SB09_a/SB09_shot_details.txt", (
            "分镜 1\n动作起止：前进后停住\n分镜 SB09-02\n动作起止：转身\n"
            "场景局部对应表：\n"
            "- SB09-01 | 场景.png | 局部01 | 门边 | 向内看\n"
            "- SB09-02 | 场景.png | 局部02 | 门边 | 向外看\n"
        ))
        package.writestr("EP/SB09_a/SD2_prompt.txt", "分镜编号：02\n动作：转身\n分镜编号：01\n动作：停住\n")
        package.writestr("EP/SB09_a/storyboard_2panel.png", b"test image")
        package.writestr("EP/SB09_a/场景.png", b"test image")
        package.writestr("EP/SB10/SB10_shot_details.txt", "分镜 SB10-01\n动作起止：跨门。\n")
        members = index_members(package)
    result = ReviewResult(1, "", archive, members, [])

    shots = load_shots(result)

    assert [shot.shot for shot in shots] == ["SB09-01", "SB09-02", "SB10-01"]
    assert shots[0].storyboard == "SB09_a/storyboard_2panel.png"
    assert shots[0].plate.slot == "局部01" and shots[1].plate.slot == "局部02"
    assert "动作：停住" in shots[0].sd2 and "动作：转身" in shots[1].sd2
    assert "场景局部对应表" not in shots[1].production
    assert shot_summary(shots[2]) == "跨门。"


def test_shot_review_leaves_duplicate_or_missing_bindings_explicit(tmp_path):
    archive = tmp_path / "review.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("SB05/SB05_shot_details.txt", (
            "分镜 SB05-01\n动作：启动\n\n分镜 SB05-02\n动作：离开\n\n"
            "场景局部对应表：\n"
            "- SB05-01 | H.png | 局部01 | 门边 | 向内\n"
            "- SB05-01 | J.png | 局部02 | 门边 | 向外\n"
            "- SB05-02 | K.png | 局部03 | 过道 | 平视\n"
        ))
        package.writestr("SB05/SD2_prompt.txt", "分镜编号：SB05-01\n动作：启动\n分镜编号：01\n动作：等待\n")
        members = index_members(package)

    first, second = load_shots(ReviewResult(1, "", archive, members, []))

    assert first.plate is None and first.sd2 == ""
    assert any("多条" in item for item in first.notices)
    assert second.plate.filename == "K.png" and second.sd2 == ""
    assert any("未在本组" in item for item in second.notices)


def test_zoom_selection_uses_preview_offsets_and_original_pixels():
    bounds = (10, 20, 400, 225)
    assert pixel_selection((210, 120), (10, 20), bounds, (1600, 900)) == (0, 0, 800, 400)
    assert pixel_selection((210, 120), (900, 500), bounds, (1600, 900)) == (800, 400, 1600, 900)
    assert pixel_selection((210, 120), (211, 123), bounds, (1600, 900)) is None
