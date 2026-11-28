from zipfile import ZipFile

from src.bundled_validators import bundled_validator
from src.production_drafting import SD2_TASK, SHOT_TASK, instructions_for
from src.production_rules import CHINESE, ENGLISH
from src.shot_review import package_camera_errors
from src.storyboard_review import run_review
from src.vision import review_instructions


def write_group(root, number, shots, review=""):
    group = f"SB{number:02d}"
    directory = root / group
    directory.mkdir(exist_ok=True)
    text = [f"分组：{group}", f"景别衔接核对：{review}", "内容类型：对话"]
    for index, (stable_id, size, angle) in enumerate(shots, 1):
        text.extend((f"分镜 {group}-{index:02d}", f"源镜ID：{stable_id}", f"景别：{size}", f"机位/角度：{angle}"))
    path = directory / f"{group}_shot_details.txt"
    path.write_text("\n".join(text), encoding="utf-8-sig")
    return path


def test_two_rules_review_actual_imported_records_across_adjacent_groups_only(tmp_path):
    first = [("A", "远景", "平视"), ("B", "中景", "俯拍")]
    second = [("C", "中景", "平视"), ("D", "中景", "平视")]
    write_group(tmp_path, 1, first)
    write_group(tmp_path, 2, second)
    write_group(tmp_path, 4, [("E", "中景", "平视")])
    english = package_camera_errors(tmp_path, ENGLISH)
    assert len(english) == 1 and "SB02-01 → SB02-02" in english[0]
    chinese = package_camera_errors(tmp_path, CHINESE)
    assert len(chinese) == 2
    assert any("SB01-02 → SB02-01" in message for message in chinese)
    write_group(tmp_path, 2, second, "值班员转向门口\n- 批准镜对：SB01/B → SB02/C | 监视器画面承接")
    remaining = package_camera_errors(tmp_path, CHINESE)
    assert len(remaining) == 1 and "SB02-01 → SB02-02" in remaining[0]
    write_group(tmp_path, 2, second, "已审核\n其他备注：\n- 批准镜对：SB01/B → SB02/C | 非批准栏目")
    assert len(package_camera_errors(tmp_path, CHINESE)) == 2


def test_zip_review_lists_both_thin_package_and_declared_camera_failures(tmp_path):
    group = write_group(tmp_path, 1, [("shot-a", "中景", "平视"), ("shot-b", "中景", "俯拍")])
    archive = tmp_path / "交付.zip"
    with ZipFile(archive, "w") as package:
        package.write(group, group.relative_to(tmp_path))
    staging = tmp_path / "check"
    staging.mkdir()
    result = run_review([str(archive), "--storyboard-validator", str(bundled_validator(CHINESE))], staging)
    assert result.exit_code == 1
    assert any(issue.group == "SB01" and issue.shot == "SB01-02" and
               "登记景别相同" in issue.message for issue in result.issues)
    assert "SD2_prompt.txt is missing" in result.report


def test_chinese_rules_apply_to_each_request_without_leaking_into_english_prompts():
    assert "稳定母镜 ID" in instructions_for(SHOT_TASK, CHINESE)
    assert "未提供最终实图时" in instructions_for(SD2_TASK, CHINESE)
    assert "缺少第6→7格" in review_instructions(CHINESE)
    assert "缺少第6→7格" not in review_instructions(ENGLISH)
