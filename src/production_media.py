"""Show group assets in the media catalogue without rewriting project records."""

import re

from .media_catalog import MediaCatalog, MediaItem, category_for_filename


IMAGE_CATEGORIES = {
    "角色": "character",
    "场景": "scene",
    "道具 / HUD": "prop",
    "故事板": "storyboard",
    "净板": "clean_plate",
}


def project_media_catalog(project_path):
    return MediaCatalog(project_path.with_suffix(".assets") / "media-catalog.json")


def project_media_items(project, project_path, *, english=False):
    """Return approved items by stable ID, without a geometry or hash read."""
    folder = project_path.with_suffix(".assets")
    kinds = {
        job["approved_image"]: IMAGE_CATEGORIES[job["kind"]]
        for job in project.image_jobs
        if job.get("status") == "approved" and job.get("approved_image") and job.get("kind") in IMAGE_CATEGORIES
    }
    kinds.update({shot.plate: "clean_plate" for shot in project.shots if shot.plate})
    for row in project.layout.get("inputs", {}).values():
        for key, category in (("board", "storyboard"), ("plate", "clean_plate")):
            image_id = row.get(key, {}).get("image")
            if image_id:
                kinds[image_id] = category
    for sheet in project.layout.get("output", {}).get("sheets", ()):
        if sheet.get("asset") and sheet.get("kind") in {"board", "plate"}:
            kinds[sheet["asset"]] = "storyboard" if sheet["kind"] == "board" else "clean_plate"

    originals = (
        ("Reference only", "Delivery image", "Costume reference", "Pose reference") if english else
        ("仅作参考", "正式交付", "服装参考", "动作参考")
    )
    items = []
    for image in project.images:
        filename = image.filename.casefold()
        category = kinds.get(image.id) or category_for_filename(filename)
        purpose = originals[0] if image.reference_only else originals[1]
        if image.reference_only and filename.startswith("costume_reference_"):
            category, purpose = "character", originals[2]
        if image.reference_only and filename.startswith("pose_reference_"):
            category, purpose = "motion_reference", originals[3]
        # Match the approved image resolver's digest grammar. The gallery can
        # display the missing-file state without accepting a path from bad data.
        stored = image.digest + ".png" if re.fullmatch(r"[0-9a-f]{64}", image.digest) else "unavailable"
        items.append(MediaItem(image.id, folder / stored, category, f"{purpose} · {image.version}",
                               name=image.filename, expected_digest=image.digest))
    return tuple(items)
