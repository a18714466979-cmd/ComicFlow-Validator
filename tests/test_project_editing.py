from copy import deepcopy

import pytest

from src.production_project import ProductionProject, Shot
from src.project_editing import ProjectEditConflict, merge_project_edits


def test_project_tabs_merge_unrelated_edits_on_the_same_shot_and_group():
    base = ProductionProject("制片", "EP01", "SB03", shots=[Shot(id="first", fields={"景别": "中景"})])
    shots = deepcopy(base)
    shots.shots[0].fields["人物站位"] = "甲在画左"
    images_and_prompt = deepcopy(base)
    images_and_prompt.shots[0].plate = "selected-asset"
    images_and_prompt.prompt["公共限制"] = "空间连续"
    merged = merge_project_edits(base, shots, images_and_prompt)
    assert merged.shots[0].fields == {"景别": "中景", "人物站位": "甲在画左"}
    assert merged.shots[0].plate == "selected-asset"
    assert merged.prompt == {"公共限制": "空间连续"}


def test_concurrent_new_images_or_candidates_keep_both_stable_ids():
    base = ProductionProject("制片", "EP01", "SB03")
    first, second = deepcopy(base), deepcopy(base)
    first.image_jobs.append({"id": "first", "status": "done"})
    second.image_jobs.append({"id": "second", "status": "pending"})
    assert merge_project_edits(base, first, second).image_jobs == second.image_jobs + first.image_jobs


def test_two_different_changes_to_one_setting_are_rejected():
    base = ProductionProject("制片", "EP01", "SB03", prompt={"公共限制": "原文"})
    first, second = deepcopy(base), deepcopy(base)
    first.prompt["公共限制"] = "甲的改动"
    second.prompt["公共限制"] = "乙的改动"
    with pytest.raises(ProjectEditConflict, match="公共限制"):
        merge_project_edits(base, first, second)
