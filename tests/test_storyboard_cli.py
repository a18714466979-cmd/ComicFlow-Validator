import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest


def run_delivery(*args):
    return subprocess.run(
        [sys.executable, "-m", "src.delivery_checker", *map(str, args)],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )


def test_storyboard_mode_forwards_paths_and_exit_code(tmp_path):
    delivery = tmp_path / "故事板 交付"
    delivery.mkdir()
    archive = tmp_path / "故事板 交付.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("README.txt", "delivery notes")

    validator = tmp_path / "validator script.py"
    validator.write_text(
        "import json, sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(1)\n",
        encoding="utf-8",
    )
    result = run_delivery(delivery, "--storyboard-validator", validator, "--zip", archive)
    assert result.returncode == 1
    assert json.loads(result.stdout) == [str(delivery.resolve()), "--zip", str(archive.resolve())]

    legacy = run_delivery(delivery, "--storyboard-validator", validator, "--allow-legacy")
    assert json.loads(legacy.stdout) == [str(delivery.resolve()), "--allow-legacy"]


def test_storyboard_mode_rejects_failed_preflight_before_running_script(tmp_path):
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    rules = tmp_path / "rules.json"
    rules.write_text('{"required_files": ["README.txt"]}', encoding="utf-8")
    validator = tmp_path / "validator.py"
    validator.write_text('print("SCRIPT INVOKED")\n', encoding="utf-8")

    result = run_delivery(delivery, "--storyboard-validator", validator, "--rules", rules)

    assert result.returncode == 1
    assert "README.txt" in result.stdout
    assert "SCRIPT INVOKED" not in result.stdout


def test_storyboard_flags_require_a_validator(tmp_path):
    result = run_delivery(tmp_path, "--allow-legacy")

    assert result.returncode == 2
    assert "--storyboard-validator" in result.stderr


@pytest.mark.parametrize("wrapper", ["", "完整交付 复验/"])
def test_storyboard_mode_reads_zip_directly(tmp_path, wrapper):
    archive = tmp_path / "故事板.zip"
    with ZipFile(archive, "w") as package:
        package.writestr(wrapper + "README.txt", "notes")
        package.writestr(wrapper + "SB01/SD2_prompt.txt", "original prompt")
    original = archive.read_bytes()

    rules = tmp_path / "rules.json"
    rules.write_text('{"required_files": ["README.txt"]}', encoding="utf-8")
    validator = tmp_path / "validator.py"
    validator.write_text(
        "import json, sys\nfrom pathlib import Path\nfrom zipfile import ZipFile\n"
        "root = Path(sys.argv[1])\narchive = Path(sys.argv[3])\n"
        "prompt = root / 'SB01/SD2_prompt.txt'\n"
        "with ZipFile(archive) as package:\n"
        "    names = package.namelist()\n"
        "    prefix = root.name + '/' if all(name.startswith(root.name + '/') for name in names) else ''\n"
        "    assert package.read(prefix + 'SB01/SD2_prompt.txt') == prompt.read_bytes()\n"
        "print(json.dumps([str(root), str(archive), sys.argv[2:]]))\n",
        encoding="utf-8",
    )

    result = run_delivery(archive, "--storyboard-validator", validator, "--rules", rules)

    assert result.returncode == 0, result.stdout + result.stderr
    root, snapshot, flags = json.loads(result.stdout)
    assert flags == ["--zip", snapshot]
    assert not Path(root).exists()
    assert not Path(snapshot).exists()
    assert archive.read_bytes() == original


def test_storyboard_zip_rejects_non_zip_before_validator(tmp_path):
    archive = tmp_path / "invalid.zip"
    archive.write_text("plain text", encoding="utf-8")
    validator = tmp_path / "validator.py"
    validator.write_text('print("SCRIPT INVOKED")\n', encoding="utf-8")

    result = run_delivery(archive, "--storyboard-validator", validator)

    assert result.returncode == 1
    assert "BadZipFile" in result.stdout
    assert "SCRIPT INVOKED" not in result.stdout


@pytest.mark.parametrize(
    ("extra_errors", "summary_errors", "expected_code"),
    [([], 1, 3), (["ERROR: SB01: SD2_prompt.txt is missing"], 2, 1), ([], 2, 1)],
)
def test_storyboard_source_review(tmp_path, extra_errors, summary_errors, expected_code):
    source = tmp_path / "delivery.zip"
    with ZipFile(source, "w") as package:
        package.writestr("README.txt", "notes")
    missing = "ERROR: SB01: 资产复用核对 approved local source is missing: /old/source.png"
    report = "\n".join([missing, *extra_errors, f"RESULT: {summary_errors} error(s), 0 warning(s)"])
    validator = tmp_path / "validator.py"
    validator.write_text(f"print({report!r})\nraise SystemExit(1)\n", encoding="utf-8")

    strict = run_delivery(source, "--storyboard-validator", validator)
    review = run_delivery(source, "--storyboard-validator", validator, "--review-missing-sources")

    assert strict.returncode == 1 and strict.stdout == report + "\n"
    assert review.returncode == expected_code
    if summary_errors == 1 + len(extra_errors):
        assert "未验证: SB01: 复用原图不可访问：/old/source.png" in review.stdout
        assert f"{len(extra_errors)} 错误，1 条复用未验证" in review.stdout
        assert all(error in review.stdout for error in extra_errors)
    else:
        assert review.stdout == strict.stdout
