import json
import os
import subprocess
import sys
from zipfile import ZipFile


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
