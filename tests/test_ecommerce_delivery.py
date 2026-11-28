from hashlib import sha256
from zipfile import ZipFile

from PIL import Image
import pytest

from src.ecommerce_delivery import (
    PRODUCT_FILE, asset_audit, board_layout, compose_product_sheet, label_board_sheet,
    publish_ecommerce_delivery, stage_ecommerce_delivery,
)
from src.ecommerce_project import EcommerceProject, EcommerceShot


def _image(path, color, size=(320, 180)):
    Image.new("RGB", size, color).save(path)
    return str(path)


def _project(folder):
    project = EcommerceProject(
        "产品演示", product_name="Our Model", source_product_name="Original Model",
        product_reviewed=True, video_has_audio=True,
        product_refs=[
            _image(folder / "front.png", "darkorange"),
            _image(folder / "back.png", "navy", (180, 320)),
        ],
        shots=[
            EcommerceShot("01A", 0, 4_000, "工作台", size="中景", angle="正视", camera="固定",
                          action="打开包装", positions="人物画左", axis="朝画右", performance="克制",
                          dialogue="Here is Original Model. 中文对白 is a label.", sound="拆盒声",
                          continuity="盒子在人物左手", constraints="维持包装形状", characters=("顾客",),
                          props=("玻璃标本盘",), contains_product=True),
            EcommerceShot("02A-01", 4_000, 9_000, "展柜", size="近景", angle="俯视", camera="固定",
                          action="保持商品原装状态", dialogue="无", axis="朝下",
                          characters=("顾客",), contains_product=True),
        ],
        assets={
            "character:顾客": _image(folder / "customer.png", "cadetblue"),
            "scene:工作台": _image(folder / "bench.png", "orange"),
            "scene:展柜": _image(folder / "cabinet.png", "darkgreen"),
            "props:SB01": _image(folder / "tray.png", "salmon"),
            "board:SB01": _image(folder / "board.png", "darkgreen", (1080, 1920)),
            "panel:02A-01": _image(folder / "book.png", "tomato", (540, 960)),
        },
    )
    return project


def test_pack_stages_independent_groups_and_binds_approval_to_preview_bytes(tmp_path):
    project = _project(tmp_path)
    assert [(item.key, item.status) for item in asset_audit(project) if item.kind == "board"] == [
        ("board:SB01", "reuse"), ("board:SB02", "derive")
    ]
    with pytest.raises(ValueError, match="确认当前分镜清单"):
        stage_ecommerce_delivery(project, tmp_path / "preview")
    project.shot_approval = project.shot_key()
    staged = stage_ecommerce_delivery(project, tmp_path / "preview")
    output = tmp_path / "delivery.zip"
    with pytest.raises(ValueError, match="最新预览"):
        publish_ecommerce_delivery(staged, output, visual_approval="")
    result = publish_ecommerce_delivery(staged, output, visual_approval=staged.fingerprint)
    assert result.output == output
    assert result.sha256 == sha256(output.read_bytes()).hexdigest()
    with ZipFile(output) as package:
        assert package.testzip() is None
        groups = [name for name in package.namelist() if name.endswith("/" + PRODUCT_FILE)]
        assert len(groups) == 2
        assert package.read(groups[0]) == package.read(groups[1])
        group = groups[0].split("/")[0]
        txt = package.read(f"{group}/SB01_shot_details.txt").decode("utf-8-sig")
        prompt = package.read(f"{group}/prompts/SD2_prompt.txt").decode("utf-8-sig")
        for content in (txt, prompt):
            assert "对白：Here is Our Model. 中文对白 is a label." in content
            assert "视线/轴线：朝画右" in content
        assert "人物资产核对" in txt and "人物资产核对" not in prompt
        assert "产品入画：Our Model" in prompt
        assert len([item for item in package.namelist() if "_storyboard_sheet_" in item]) == 2
        assert not any(item.endswith("/book.png") for item in package.namelist())
        assert all(path.is_file() for path in staged.visuals)
    staged.visuals[0].write_bytes(b"new unapproved bytes")
    another = tmp_path / "another.zip"
    with pytest.raises(ValueError, match="最新预览"):
        publish_ecommerce_delivery(staged, another, visual_approval=staged.fingerprint)
    assert not another.exists()


def test_product_composite_does_not_crop_or_invent_views_and_board_labels_use_grid(tmp_path):
    single = Image.new("RGB", (80, 40), "orange")
    single.putpixel((0, 0), (255, 0, 0))
    single.putpixel((79, 39), (0, 0, 255))
    source = tmp_path / "original.png"
    single.save(source)
    out = compose_product_sheet([source], tmp_path / PRODUCT_FILE)
    with Image.open(out) as image:
        assert image.size == (1920, 1080)
        assert image.crop((920, 520, 1000, 560)).tobytes() == single.tobytes()
    assert board_layout(10) == (3, 4)
    board = tmp_path / "board.png"
    _image(board, "peru", (1080, 1920))
    labeled = label_board_sheet(board, tmp_path / "labeled.png", ["01A", "02A"])
    with Image.open(labeled) as image:
        assert image.getpixel((1, 1)) == (233, 237, 241)
        assert image.getpixel((541, 1)) == (233, 237, 241)
        assert image.getpixel((209, 307)) == (205, 133, 63)
    with pytest.raises(ValueError, match="格号"):
        label_board_sheet(board, tmp_path / "bad.png", ["01A", "01A"])


def test_confirm_each_dialogue_before_stage_from_audio_source(tmp_path):
    project = _project(tmp_path)
    project.shots[1] = EcommerceShot("02A-01", 4_000, 9_000, "展柜", action="放下",
                                     contains_product=True)
    project.shot_approval = project.shot_key()
    with pytest.raises(ValueError, match="02A-01"):
        stage_ecommerce_delivery(project, tmp_path / "preview")
