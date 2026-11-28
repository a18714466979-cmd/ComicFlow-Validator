import hashlib
import json
from dataclasses import replace
from io import BytesIO
from shutil import copytree
from zipfile import ZipFile

import pytest

from src.batch_delivery import publish_episode, publish_series
from src.batch_workspace import BatchWorkspace
from src.bundled_validators import bundled_validator
from src.production_handoff import confirm_boundary
from src.production_project import ProductionProject
from src.production_rules import ENGLISH
from test_production_project import production


SCRIPT = "\n".join((
    "仓间空无一人。", "绿灯亮起。", "灯光落在左侧柜门上。", "值班员：The signal is green.",
    "右侧信号灯熄灭。", "门依然关闭。", "墙上的反光消失。", "室外光线渐暗。",
))


def reviewed_episode(workspace, episode, sample, groups=1):
    workspace.add_episode(episode, "灯号" + episode, "\n".join([SCRIPT] * groups))
    workspace.approve_plan(episode)
    template = ProductionProject.open(sample)
    prepared = []
    for path in workspace.group_paths(episode):
        project = ProductionProject.open(path)
        assert len(project.shots) == len(template.shots)
        copytree(sample.with_suffix(".assets"), path.with_suffix(".assets"))
        project.images = template.images
        project.notes = dict(template.notes, **{"本组进入状态": "仓间信号灯稳定"})
        project.prompt = template.prompt.copy()
        project.shots = [replace(shot, scene=source.scene, plate=source.plate,
                                 plate_note=source.plate_note, fields=source.fields)
                         for shot, source in zip(project.shots, template.shots)]
        project.structure_review = project.fingerprint()
        project.save(path)
        prepared.append((project, path))
    assert len(prepared) == groups
    for (left, path), (right, _) in zip(prepared, prepared[1:]):
        planner = bundled_validator(ENGLISH).with_name("plan_english_dialogue.py")
        confirm_boundary(left, right, planner, "合成测试项目已对照前后镜的门灯状态与光线")
        left.save(path)
    return prepared


def test_deliver_complete_series_with_real_group_zips_and_source_index(production, tmp_path):
    ws = BatchWorkspace.create(tmp_path / "灯光.cfbatch", "灯光", ENGLISH)
    reviewed_episode(ws, "EP01", production, groups=2)
    reviewed_episode(ws, "EP02", production)
    output = tmp_path / "整季.zip"
    validator = bundled_validator(ENGLISH)
    result = publish_series(ws, {ENGLISH: validator}, output)
    assert result == output
    with ZipFile(output) as series:
        assert series.testzip() is None
        entries = json.loads(series.read("剧集目录.json"))
        assert [r["集号"] for r in entries] == ["EP01", "EP02"]
        for record in entries:
            episode_data = series.read(record["文件"])
            assert hashlib.sha256(episode_data).hexdigest() == record["SHA256"]
            with ZipFile(BytesIO(episode_data)) as episode:
                assert episode.testzip() is None
                index = json.loads(episode.read("原稿覆盖.json"))
                assert len(index["原稿到分镜"]) == record["组数"] * 8
                assert len(index["相邻组交接"]) == record["组数"] - 1
                for group in index["交付组"]:
                    group_data = episode.read(group["文件"])
                    assert hashlib.sha256(group_data).hexdigest() == group["SHA256"]
                    with ZipFile(BytesIO(group_data)) as child:
                        assert child.testzip() is None
                        assert f"{group['组号']}/SD2_prompt.txt" in child.namelist()
                        assert any(name.endswith(".png") for name in child.namelist())
    with pytest.raises(ValueError, match="一次"):
        publish_series(ws, {ENGLISH: validator}, tmp_path / "second.zip", ["EP01", "EP01"])


def test_rejected_episode_keeps_previous_version_and_replacement_is_explicit(production, tmp_path):
    ws = BatchWorkspace.create(tmp_path / "灯光.cfbatch", "灯光", ENGLISH)
    [(project, path)] = reviewed_episode(ws, "EP01", production)
    validator = bundled_validator(ENGLISH)
    output = tmp_path / "episode.zip"
    output.write_bytes(b"previous delivery")
    with pytest.raises(FileExistsError):
        publish_episode(ws, "EP01", validator, output)
    project.shots.pop()
    project.structure_review = project.fingerprint()
    project.save(path)
    with pytest.raises(ValueError, match="覆盖"):
        publish_episode(ws, "EP01", validator, output, replace=True)
    assert output.read_bytes() == b"previous delivery"


def test_missing_boundary_and_stale_review_block_even_complete_storyboards(production, tmp_path):
    ws = BatchWorkspace.create(tmp_path / "sample.cfbatch", "灯光", ENGLISH)
    (left, path), _ = reviewed_episode(ws, "EP01", production, groups=2)
    validator = bundled_validator(ENGLISH)
    left.handoffs.clear()
    left.save(path)
    output = tmp_path / "episode.zip"
    with pytest.raises(ValueError, match="交接"):
        publish_episode(ws, "EP01", validator, output)
    left.notes["本组退出状态"] = "门打开"
    left.save(path)
    with pytest.raises(ValueError, match="确认当前版本"):
        publish_episode(ws, "EP01", validator, output)
    assert not output.exists()


def test_chinese_current_validator_two_groups_including_tail(tmp_path, monkeypatch):
    from pathlib import Path
    import os
    from scripts import windows_trial
    from src.production_project import Shot
    from src.production_rules import CHINESE

    setting = os.environ.get("COMICFLOW_TEST_CN_VALIDATOR")
    validator = Path(setting) if setting else bundled_validator(CHINESE)
    assert validator is not None
    workspace = BatchWorkspace.create(tmp_path / "中文验收.cfbatch", "信号站", CHINESE)
    script = "\n".join(f"值守室门灯发生第{index}次明暗变化。" for index in range(1, 20))
    workspace.add_episode("EP01", "灯光交接", script)
    workspace.approve_plan("EP01")
    files = workspace.group_paths("EP01")
    planned = [ProductionProject.open(p) for p in files]
    assert [len(p.shots) for p in planned] == [10, 9]
    complete = []
    for ordinal, (path, template_plan) in enumerate(zip(files, planned), 1):
        shots = iter(template_plan.shots)

        def aligned_shot(**kwargs):
            original = next(shots)
            return Shot(**{**kwargs, "id": original.id, "source": original.source, "anchor": original.anchor})

        monkeypatch.setattr(windows_trial, "Shot", aligned_shot)
        scratch = tmp_path / f"native{ordinal}"
        scratch.mkdir()
        project, _ = windows_trial.make_group(path.parent, scratch, ordinal, CHINESE)
        project.name = workspace.title
        project.sources = template_plan.sources
        project.structure_review = project.fingerprint()
        project.save(path)
        complete.append(project)
    confirm_boundary(*complete, None, "已对照两组测试板的末格、首格和灯光朝向")
    complete[0].save(files[0])
    archive = publish_episode(workspace, "EP01", validator, tmp_path / "中文整集.zip")
    with ZipFile(archive) as episode:
        assert episode.testzip() is None
        assert [r["组号"] for r in json.loads(episode.read("原稿覆盖.json"))["交付组"]] == ["SB01", "SB02"]
        with ZipFile(BytesIO(episode.read("SB02.zip"))) as child:
            assert child.testzip() is None and "SB02/SD2_prompt.txt" in child.namelist()
