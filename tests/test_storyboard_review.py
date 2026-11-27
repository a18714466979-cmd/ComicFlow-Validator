from zipfile import ZipFile

from src.storyboard_review import ReviewIssue, read_preview, run_review


def test_review_locates_issues_in_validated_zip_copy(tmp_path):
    archive = tmp_path / "交付.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("EP004/SB05/SB05_shot_details.txt", "分镜：SB05-02\n对白：无\n")
        package.writestr("EP004/SB05/资产图.png", b"fixture")
    validator = tmp_path / "validator.py"
    output = (
        "ERROR: SB05/SB05_shot_details.txt: shot SB05-02: dialogue differs\n"
        "ERROR: SB05: SD2_prompt.txt is missing\n"
        "WARNING: SB05: low contrast: 资产图.png\n"
        "ERROR: SB05: 资产复用核对 approved local source is missing: /tmp/source/资产图.png\n"
        "RESULT: 3 error(s), 1 warning(s)\n"
    )
    validator.write_text(f"print({output!r}, end='')\nraise SystemExit(1)\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()

    result = run_review([str(archive), "--storyboard-validator", str(validator), "--review-missing-sources"], staging)

    assert result.exit_code == 1
    assert result.issues == [
        ReviewIssue("错误", "SB05", "SB05-02", "SB05_shot_details.txt",
                    "SB05/SB05_shot_details.txt: shot SB05-02: dialogue differs"),
        ReviewIssue("错误", "SB05", "", "SD2_prompt.txt", "SB05: SD2_prompt.txt is missing"),
        ReviewIssue("警告", "SB05", "", "资产图.png", "SB05: low contrast: 资产图.png"),
        ReviewIssue("未验证", "SB05", "", "", "SB05: 复用原图不可访问：/tmp/source/资产图.png"),
    ]
    assert "SB05/SD2_prompt.txt" not in result.members
    archive.unlink()
    assert read_preview(result, "SB05/SB05_shot_details.txt").decode() == "分镜：SB05-02\n对白：无\n"


def test_review_displays_a_bad_zip_as_report_only(tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_text("invalid", encoding="utf-8")
    validator = tmp_path / "validator.py"
    validator.write_text("raise SystemExit(0)\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()

    result = run_review([str(archive), "--storyboard-validator", str(validator)], staging)

    assert result.exit_code == 1
    assert "BadZipFile" in result.report
    assert result.members == {}
