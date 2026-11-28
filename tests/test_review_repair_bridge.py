from dataclasses import replace
from unittest.mock import Mock, patch
from zipfile import ZipFile

import pytest

from src.production_project import ProductionProject, ProjectImage, Shot
from src.production_rules import CHINESE
from src.review_repair_bridge import (
    RepairTarget, find_repair_project, open_review_repair, resolve_repair_target, review_location,
)
from src.storyboard_review import ReviewIssue, ReviewResult, index_members


def make_package(path, *, groups=("SB01",), traced=True):
    with ZipFile(path, "w") as package:
        for group in groups:
            package.writestr(f"{group}/SD2_prompt.txt", f"分镜编号：{group}-01")
        text = ["无镜头源 ID 的旧交付"] if not traced else [
            f"船舱 · EP02\n制作规则：14.10.4\n组号：{group}\n镜头与来源：\n"
            f"- {group}-01 | {group}-bow | approved R5 | source | 局部01\n"
            f"- {group}-02 | {group}-deck | approved R5 | source | 局部02\n"
            for group in groups if "_" not in group
        ]
        package.writestr("README.txt", "\n".join(text))
    with ZipFile(path) as package:
        return ReviewResult(1, "", path, index_members(package), [])


def make_project(path, *, group="SB01", episode="EP02", name="船舱", reverse=False, alternate=False):
    identities = [f"{group}-bow", f"{group}-deck"] if not alternate else ["different-id", "another-id"]
    if reverse:
        identities.reverse()
    ProductionProject(name=name, episode=episode, group=group, shots=[Shot(id=identity) for identity in identities]).save(path)


def test_routes_shot_by_stable_id_even_after_order_changes(tmp_path):
    archive = tmp_path / "交付.zip"
    result = make_package(archive, groups=("SB01", "SB02"))
    correct = tmp_path / "正确.cfproject"
    different_episode = tmp_path / "另一集.sb01.cfproject"
    different_project = tmp_path / "同名.cfproject"
    make_project(correct, reverse=True)
    make_project(different_episode, episode="EP01")
    make_project(different_project, alternate=True)
    issue = ReviewIssue("错误", "SB01", "02", "SB01_shot_details.txt", "dialogue differs")
    position = review_location(result, issue)
    assert find_repair_project(position, source_archive=archive, project_paths=(different_project,)) == correct.resolve()
    assert resolve_repair_target(position, correct) == RepairTarget(correct.resolve(), "shots", "SB01-deck")
    assert position.episode == "EP02"


def test_manual_choice_rejects_stable_id_and_rules_mismatch(tmp_path):
    result = make_package(tmp_path / "delivery.zip")
    position = review_location(result, selected_member="SB01/SD2_prompt.txt")
    path = tmp_path / "work.cfproject"
    make_project(path, alternate=True)
    with pytest.raises(ValueError, match="镜头源 ID"):
        resolve_repair_target(position, path)
    make_project(path)
    project = ProductionProject.open(path)
    replace(project, rules=CHINESE).save(path)
    with pytest.raises(ValueError, match="制作规则"):
        resolve_repair_target(position, path)


def test_ambiguous_projects_require_explicit_choice_and_legacy_does_not_guess_shot(tmp_path):
    archive = tmp_path / "export.zip"
    issue = ReviewIssue("错误", "SB01", "SB01-02", "", "camera cut")
    first, copy = tmp_path / "main.cfproject", tmp_path / "copy.cfproject"
    make_project(first, reverse=True)
    make_project(copy)
    position = review_location(make_package(archive), issue)
    assert find_repair_project(position, source_archive=archive) is None
    legacy = make_package(archive, traced=False)
    opened = Mock()
    with (patch("src.review_repair_bridge.filedialog.askopenfilename", return_value=str(first)) as picker,
          patch("src.review_repair_bridge.messagebox.askyesno", return_value=True)):
        assert open_review_repair(Mock(), legacy, issue, source_archive=archive, open_production=opened)
    picker.assert_called_once()
    opened.assert_called_once_with("shots", first.resolve(), shot_id="", asset_filename="")


def test_mixed_groups_require_selection_and_duplicate_group_numbers_provide_no_trace(tmp_path):
    path = tmp_path / "export.zip"
    mixed = make_package(path, groups=("SB01", "SB02"))
    with pytest.raises(ValueError, match="唯一"):
        review_location(mixed)
    selected = review_location(mixed, selected_member="SB02/SD2_prompt.txt")
    assert (selected.group, selected.stage, selected.shot_ids[1][1]) == ("SB02", "prompts", "SB02-deck")
    duplicate = make_package(path, groups=("SB01", "SB01_copy"))
    assert review_location(duplicate, selected_member="SB01_copy/SD2_prompt.txt").shot_ids == ()


def test_visual_issue_locates_approved_image_or_layout_without_redirecting_to_prompt(tmp_path):
    result = make_package(tmp_path / "delivery.zip")
    path = tmp_path / "work.cfproject"
    make_project(path)
    project = ProductionProject.open(path)
    project.images = [
        ProjectImage("first-ref", "r1", "storyboard_2panel.png", "test", 1920, 1080, "created",
                     "新生成", "test", "test"),
        ProjectImage("source-only", "r1", "earlier_board.png", "test", 1920, 1080, "created",
                     "新生成", "test", "test", reference_only=True),
    ]
    project.save(path)
    issue = ReviewIssue("错误", "SB01", "SB01-02", "storyboard_2panel.png", "image differs from prompt")
    assert resolve_repair_target(review_location(result, issue), path) == RepairTarget(
        path.resolve(), "assets", "SB01-deck", "storyboard_2panel.png",
    )
    assert resolve_repair_target(review_location(result, replace(issue, filename="earlier_board.png")), path) == (
        RepairTarget(path.resolve(), "assets", "SB01-deck")
    )
    assert review_location(result, replace(issue, message="plate mapping is missing")).stage == "layout"
