"""Local preflight for approved dialogue and the nine-image budget."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


IMAGE_LIMIT = 9


def plan_dialogue(source: str, planner: Path) -> list[dict]:
    """Run the current production workflow's planner without changing the source."""
    # Legacy Windows editors may include a BOM when the JSON is pasted or loaded.
    source = source.removeprefix("\ufeff")
    try:
        approved = json.loads(source)
    except json.JSONDecodeError as exc:
        raise ValueError(f"对白 JSON 第 {exc.lineno} 行、第 {exc.colno} 列格式有误。") from None
    if not isinstance(approved, list):
        raise ValueError("对白 JSON 需要是按说话顺序排列的数组。")
    if not approved:
        return []
    if not planner.is_file():
        raise ValueError("请先选择故事板校验脚本，并确认同目录有 plan_english_dialogue.py。")

    with TemporaryDirectory(prefix="comicflow-dialogue-") as temporary:
        dialogue = Path(temporary) / "approved.json"
        dialogue.write_text(source, encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(planner.resolve()), str(dialogue)],
            check=False, capture_output=True, encoding="utf-8", errors="replace", timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    if completed.returncode:
        lines = completed.stderr.strip().splitlines()
        reason = lines[-1].partition(": error: ")[-1] if lines else "对白预排脚本未返回结果。"
        raise ValueError(reason)
    try:
        groups = json.loads(completed.stdout)
        if not isinstance(groups, list):
            raise ValueError
        for group in groups:
            if type(group["words"]) is not int or not group["fragments"]:
                raise ValueError
            for fragment in group["fragments"]:
                for key in ("id", "speaker", "text", "cue", "start", "end"):
                    fragment[key]
    except (ValueError, TypeError, KeyError):
        raise ValueError("预排脚本输出的格式不兼容，请检查所选工作流版本。") from None
    return groups


def image_budget(leads: int, supporting: int, props: int, scenes: int) -> tuple[int, int]:
    """Count actual planned image files, with the storyboard always occupying one slot."""
    if any(type(count) is not int or count < 0 for count in (leads, supporting, props, scenes)):
        raise ValueError("图片张数需为非负整数。")
    total = 1 + leads + supporting + props + scenes
    return total, IMAGE_LIMIT - total
