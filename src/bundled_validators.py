"""Locate the production checks distributed with the workbench."""

from pathlib import Path

from .production_rules import CHINESE, ENGLISH


ENGLISH_VALIDATOR_DIRECTORY = Path("assets/workflow_validators/english")
ENGLISH_VALIDATOR_FILES = ("validate_storyboard_package.py", "plan_english_dialogue.py")
CHINESE_VALIDATOR_DIRECTORY = Path("assets/workflow_validators/chinese")
VALIDATOR_BUNDLES = {
    ENGLISH: (ENGLISH_VALIDATOR_DIRECTORY, ENGLISH_VALIDATOR_FILES),
    CHINESE: (CHINESE_VALIDATOR_DIRECTORY, ("validate_storyboard_package.py",)),
}


def bundled_validator(rules: str) -> Path | None:
    """Use only a complete bundle for the requested workflow."""
    if rules not in VALIDATOR_BUNDLES:
        return None
    directory, files = VALIDATOR_BUNDLES[rules]
    paths = [Path(__file__).resolve().parents[1] / directory / name for name in files]
    return paths[0] if all(path.is_file() for path in paths) else None


def bundled_planner() -> Path | None:
    validator = bundled_validator(ENGLISH)
    return validator.with_name(ENGLISH_VALIDATOR_FILES[1]) if validator is not None else None
