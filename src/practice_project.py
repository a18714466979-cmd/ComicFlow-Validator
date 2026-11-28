"""Prepare editable copies of the bundled, synthetic storyboard exercises."""

from pathlib import Path
from shutil import copy2, copytree, rmtree
from tempfile import mkdtemp

from .production_project import ProductionProject
from .production_rules import CHINESE


def practice_example(examples, rules):
    return (examples / "中文制作" if rules == CHINESE else examples) / "SB01.cfproject"


def make_practice(examples, destination, rules, *, existing):
    source = practice_example(examples, rules)
    project = ProductionProject.open(source)
    if not project.sources or not project.images:
        raise ValueError("练习项目缺少剧本或图像。")
    reference = next((image for image in project.images if not image.reference_only), project.images[0])
    reference_path = project.checked_image(source, reference)
    folder = Path(mkdtemp(prefix="Studio-Practice-", dir=destination))
    try:
        if existing:
            target = folder / source.name
            copy2(source, target)
            copytree(source.with_suffix(".assets"), target.with_suffix(".assets"))
        else:
            target = folder / "Approved-Script.txt"
            target.write_text(project.sources[0].text, encoding="utf-8")
            copy2(reference_path, folder / "Local-Reference.png")
    except BaseException:
        rmtree(folder, ignore_errors=True)
        raise
    return target
