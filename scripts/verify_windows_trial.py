"""Exercise all three delivery paths from the exact unpacked trial archive."""

import argparse
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image, ImageChops

from src.asset_registry import sha256_file
from src.production_export import publish_batch, publish_project
from src.production_handoff import confirm_boundary
from src.production_images import approve_candidate
from src.production_project import ProductionProject
from src.shot_review import load_shots
from src.storyboard_review import ReviewResult, index_members


def check_archive(result, count):
    if result.exit_code or not result.output:
        raise ValueError(result.report)
    with ZipFile(result.output) as archive:
        assert archive.testzip() is None and sha256_file(result.output) == result.sha256
        members = index_members(archive)
        rows = load_shots(ReviewResult(0, "", result.output, members, []))
        assert len(rows) == count and all(row.board_box and row.plate_box and not row.notices for row in rows)
        for filename in members:
            if filename.endswith(".png"):
                with Image.open(BytesIO(archive.read(filename))) as image:
                    image.load()
                    assert image.width * 9 == image.height * 16
            elif filename.endswith(".txt"):
                assert archive.read(filename).startswith(b"\xef\xbb\xbf")
    print(f"Reopened {result.output.name}, {count} shots, CRC and SHA-256 verified.")


def fixture_validator(folder):
    path = folder / "fixture_validator.py"
    path.write_text(
        'import re, sys\nfrom pathlib import Path\n'
        'groups = sorted(Path(sys.argv[1]).glob("SB*"))\n'
        'assert 1 <= len(groups) <= 2\n'
        'for group in groups:\n'
        '    production = (group / (group.name + "_shot_details.txt")).read_text(encoding="utf-8-sig")\n'
        '    prompt = (group / "SD2_prompt.txt").read_text(encoding="utf-8-sig")\n'
        '    assert re.findall(r"^分镜 (SB\\d+-\\d+)", production, re.M) == [f"{group.name}-{n:02d}" for n in range(1, 10)]\n'
        '    assert re.findall(r"^分镜编号：(SB\\d+-\\d+)", prompt, re.M) == [f"{group.name}-{n:02d}" for n in range(1, 10)]\n'
        'print("RESULT: 0 error(s), 0 warning(s)")\n',
        encoding="utf-8",
    )
    return path


def verify(archive_path, validator=None, install=False):
    with TemporaryDirectory(prefix="ComicFlow 试用 ") as directory:
        base = Path(directory)
        with ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            archive.extractall(base)
        folder = base / "ComicFlow-Windows"
        python = sys.executable
        if install:
            result = subprocess.run(["cmd.exe", "/d", "/c", "ComicFlow-Setup.bat", "--no-pause"], cwd=folder,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    check=False, timeout=150)
            print(result.stdout, end="")
            assert result.returncode == 0 and "COMICFLOW_SETUP_OK" in result.stdout, result.stderr
            python = str(folder / ".venv" / "Scripts" / "python.exe")
            smoke = Path(__file__).resolve().parents[1] / "tests" / "windows_smoke.py"
            subprocess.run([python, str(smoke), str(folder)], cwd=folder, check=True, timeout=150)
        validator = validator or fixture_validator(base)
        run_in_kit = (
            "import runpy, sys; from pathlib import Path; "
            "sys.path.insert(0, str(Path.cwd())); "
            "runpy.run_path(sys.argv[1])['exercise'](Path.cwd(), Path(sys.argv[2]))"
        )
        subprocess.run([python, "-I", "-c", run_in_kit, str(Path(__file__).resolve()), str(validator)],
                       cwd=folder, check=True, timeout=90)


def exercise(folder, validator):
    base = folder.parent
    print(f"Validator used for this run: {validator.name}")
    left_path, right_path = (folder / "Examples" / f"SB{number:02d}.cfproject" for number in (1, 2))
    left, right = (ProductionProject.open(path) for path in (left_path, right_path))
    assert not left.structure_review and not right.structure_review
    baseline = left.shots[0].id
    for project, path in ((left, left_path), (right, right_path)):
        project.structure_review = project.fingerprint()
        project.save(path)
    left, right = (ProductionProject.open(path) for path in (left_path, right_path))
    assert left.shots[0].id == baseline
    single = publish_project(left, left_path, validator, base / "single.zip")
    check_archive(single, 9)
    confirm_boundary(left, right, validator.with_name("plan_english_dialogue.py"), "合成试用，门和绿灯在前末后首延续")
    batch = publish_batch([(left, left_path), (right, right_path)], validator, base / "pair.zip")
    check_archive(batch, 18)

    job = left.image_jobs[0]
    original = next(asset for asset in left.images if asset.id == job["references"][0]["id"])
    original_path = left.checked_image(left_path, original)
    old_digest = sha256_file(original_path)
    new = approve_candidate(left, left_path, job, 0, original.filename, "R2", "局部修改合成灯罩",
                            "核对选区、边缘及原图尺寸", replace_original=True)
    assert sha256_file(original_path) == old_digest
    with Image.open(original_path) as previous, Image.open(left.checked_image(left_path, new)) as revised:
        actual = ImageChops.difference(previous.convert("RGBA"), revised.convert("RGBA")).getbbox(alpha_only=False)
        assert tuple(job["box"]) == actual
    left.structure_review = left.fingerprint()
    repaired = publish_project(left, left_path, validator, base / "repair.zip", single.output)
    check_archive(repaired, 9)
    assert set(repaired.changed) == {"SB01/SB01_shot_details.txt", f"SB01/{original.filename}"}
    print("Original SHA-256 and every pixel outside the edit box verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--validator", type=Path)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    verify(args.archive.resolve(), args.validator.resolve() if args.validator else None, args.install)
