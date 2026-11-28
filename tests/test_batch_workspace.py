from pathlib import Path
from shutil import copytree

import pytest
from PIL import Image

from src.asset_registry import sha256_file
from src.batch_workspace import BatchWorkspace
from src.production_project import ProductionProject
from src.production_rules import CHINESE
from test_production_project import production, synthetic_sheet, validator


def sample(folder):
    workspace = BatchWorkspace.create(folder / "试用.cfbatch", "海边", CHINESE)
    text = "场景：走廊\n艾拉：我在门口。\n她望向窗外。\n" + "\n".join(f"门外的显示屏亮起数字 {i}。" for i in range(12))
    workspace.add_episode("EP01", "海边第一集", text)
    return workspace


def test_portable_multi_import_order_and_all_or_nothing(tmp_path):
    first = tmp_path / "第三集.md"
    second = tmp_path / "无编号.txt"
    third = tmp_path / "EP01-开场.txt"
    source = "场景：庭院\r\n艾拉：我在这里。\r\n"
    for path in (first, second, third):
        path.write_bytes(source.encode("utf-8-sig"))
    workspace = BatchWorkspace.create(tmp_path / "批次.cfbatch", "项目", CHINESE)
    result = workspace.add_scripts([first, second, third])
    assert [ep.id for ep in result] == ["EP03", "EP02", "EP01"]
    assert workspace.source_text("3") == source
    for path in (first, second, third):
        path.unlink()
    workspace.approve_plan("EP03")
    moved = tmp_path / "moved"
    moved.mkdir()
    (moved / workspace.path.name).write_bytes(workspace.path.read_bytes())
    copytree(workspace.root, moved / workspace.root.name)
    reopened = BatchWorkspace.open(moved / workspace.path.name)
    assert reopened.episodes == workspace.episodes
    assert reopened.plan_approved("3") and not reopened.plan_approved("2")
    assert ProductionProject.open(reopened.group_paths("3")[0]).sources[0].text == source
    first = tmp_path / "EP04.txt"
    first.write_text("室内 свет。", encoding="utf-8")
    second.write_text("  \n", encoding="utf-8")
    with pytest.raises(ValueError):
        reopened.add_scripts([first, second])
    assert reopened.episodes == result
    assert not list((reopened.root / "episodes" / "EP04").glob("*"))


def test_regroup_keeps_edited_groups_and_changes_generation_atomically(tmp_path):
    workspace = sample(tmp_path)
    plan = workspace.plan_for("1")
    ids = [s["id"] for s in plan["shots"]]
    paths = workspace.group_paths("1")
    workspace.approve_plan("1")
    old = paths[0].read_bytes()
    paths[0].write_bytes(old + b" ")
    regroup = [ids[:6], ids[6:]]
    with pytest.raises(ValueError, match="修改"):
        workspace.regroup("1", regroup)
    assert workspace.group_paths("1") == paths and paths[0].read_bytes() == old + b" "
    paths[0].write_bytes(old)
    workspace.regroup("1", regroup)
    assert workspace.group_paths("1")[0] != paths[0] and paths[0].exists()
    assert not workspace.plan_approved("1")
    assert [s.id for s in ProductionProject.open(workspace.group_paths("1")[0]).shots] == ids[:6]


def test_requirements_wait_by_group_and_bind_exact_approved_version(tmp_path):
    workspace = sample(tmp_path)
    other = workspace.group_paths("1")[1].stem
    key = ("人物：艾拉", "救援后", "R2")
    workspace.require_asset("1", other, *key)
    assert not workspace.required_asset_gaps("1", "SB01")
    assert workspace.resolve_required_assets("1", other) == [" · ".join(key)]
    path = tmp_path / "protagonist_Ella.png"
    Image.new("RGB", (64, 36), "ivory").save(path)
    workspace.approve_asset(key[0], key[1], "R1", path, "衣袖、脸和双手已确认")
    assert workspace.resolve_required_assets("1", other) and not workspace.group_reference_ids("1", other)
    asset = workspace.approve_asset(*key, path, "已确认服装和手部状态")
    assert workspace.approve_asset(*key, path, "重新浏览原图").id == asset.id
    Image.new("RGB", (64, 36), "purple").save(path)
    with pytest.raises(ValueError, match="另一张图"):
        workspace.approve_asset(*key, path, "变更造型")
    path.unlink()
    assert not workspace.resolve_required_assets("1", other)
    assert not workspace.resolve_required_assets("1", other)
    group_path = workspace.group_path("1", other)
    project = ProductionProject.open(group_path)
    assert len(project.images) == 1
    image = project.images[0]
    assert workspace.group_reference_ids("1", other) == [image.id]
    assert image.reference_only and sha256_file(project.checked_image(group_path, image)) == asset.digest
    workspace.require_asset("1", other, *key, deliver=True)
    assert workspace.required_asset_gaps("1", other)
    assert not workspace.resolve_required_assets("1", other)
    final = ProductionProject.open(group_path).images[0]
    assert not final.reference_only and final.id == image.id and final.filename == asset.filename
    workspace.remove_requirement("1", other, *key)
    assert not workspace.required_assets("1", other)


def test_wrong_manifest_unsafe_id_and_duplicate_input_leave_workspace_intact(tmp_path):
    first = sample(tmp_path)
    other = BatchWorkspace.create(tmp_path / "其他.cfbatch", "不同的项目", CHINESE)
    other.path.write_bytes(first.path.read_bytes())
    with pytest.raises(ValueError, match="不匹配"):
        BatchWorkspace.open(other.path)
    with pytest.raises(ValueError):
        first.add_episode("../EP02", "坏编号", "场景。")
    with pytest.raises(ValueError, match="已存在"):
        first.add_episode("01", "重复编号", "别的剧本。")
    assert [x.id for x in first.episodes] == ["EP01"]


def test_shared_formal_asset_is_embedded_in_standalone_group(tmp_path, production, validator):
    from shutil import copyfile
    from zipfile import ZipFile

    from src.production_export import publish_project
    from src.production_rules import ENGLISH

    base = ProductionProject.open(production)
    workspace = BatchWorkspace.create(tmp_path / "整集.cfbatch", base.name, ENGLISH)
    workspace.add_episode("EP01", "灯光", base.sources[0].text)
    path = workspace.group_path("EP01", "SB01")
    copyfile(production, path)
    copytree(production.with_suffix(".assets"), path.with_suffix(".assets"))
    source = tmp_path / "道具批准原图.png"
    synthetic_sheet(source, (320, 180), [(1, 0, 0, 2)])
    filename = "06_props_门闩_16x9.png"
    key = ("道具：门闩", "闭合", "R2")
    workspace.approve_asset(*key, source, "检查门闩及边缘", filename=filename)
    workspace.require_asset("1", "SB01", *key, deliver=True)
    assert workspace.resolve_required_assets("1", "SB01") == []
    project = ProductionProject.open(path)
    project.structure_review = project.fingerprint()
    result = publish_project(project, path, validator, tmp_path / "单组.zip")
    assert result.exit_code == 0, result.report
    with ZipFile(result.output) as archive:
        assert archive.testzip() is None
        assert archive.read("SB01/" + filename) == source.read_bytes()
