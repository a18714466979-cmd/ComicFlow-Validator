"""Create independent copies of the bundled offline workbench exercises."""

from pathlib import Path
from shutil import copy2, copytree, rmtree
from tempfile import mkdtemp

from .ecommerce_project import EcommerceProject
from .ecommerce_video import inspect_video
from .production_export import register_project_assets
from .production_project import ProductionProject


PRACTICE_SOURCES = {
    "ecommerce": Path("Workbench/Ecommerce/Reference.mp4"),
    "batch": Path("Workbench/Batch/Signal-Station.cfbatch"),
    "review": Path("预览_信号站_相邻两组.zip"),
}
REVIEW_REGISTRY = "Practice-Assets.sqlite3"
REVIEW_GROUPS = ("SB01.cfproject", "SB02.cfproject")


def available_practices(examples):
    return {kind for kind, source in PRACTICE_SOURCES.items() if (examples / source).is_file()}


def make_workbench_practice(examples, destination, kind):
    source = examples / PRACTICE_SOURCES[kind]
    folder = Path(mkdtemp(prefix="Studio-Practice-", dir=destination))
    try:
        if kind == "ecommerce":
            return _copy_ecommerce(source, folder)
        if kind == "batch":
            copytree(source.parent, folder, dirs_exist_ok=True)
            return folder / source.name
        target = folder / source.name
        copy2(source, target)
        for filename in REVIEW_GROUPS:
            project = folder / filename
            original = examples / filename
            copy2(original, project)
            copytree(original.with_suffix(".assets"), project.with_suffix(".assets"))
            if original.with_suffix(".candidates").is_dir():
                copytree(original.with_suffix(".candidates"), project.with_suffix(".candidates"))
            register_project_assets(ProductionProject.open(project), project, folder / REVIEW_REGISTRY)
        return target
    except BaseException:
        rmtree(folder, ignore_errors=True)
        raise


def _copy_ecommerce(source, folder):
    video, product = folder / source.name, folder / "Product.png"
    copytree(source.parent, folder, dirs_exist_ok=True)
    info = inspect_video(video)
    project = EcommerceProject(
        "Luma · Practice", video_path=str(video), duration_ms=info.duration_ms,
        product_name="Luma", product_refs=[str(product)], video_has_audio=info.has_audio,
        video_width=info.width, video_height=info.height,
    )
    target = folder / "Practice.cfecom"
    project.save(target)
    return target
