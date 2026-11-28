"""Locate the English workflow checks distributed with the workbench."""

from pathlib import Path

from .production_rules import ENGLISH


ENGLISH_VALIDATOR_DIRECTORY = Path("assets/workflow_validators/english")
ENGLISH_VALIDATOR_FILES = ("validate_storyboard_package.py", "plan_english_dialogue.py")


def bundled_validator(rules: str) -> Path | None:
    """Return the English validator only when its complete script pair is present."""
    if rules != ENGLISH:
        return None
    directory = Path(__file__).resolve().parents[1] / ENGLISH_VALIDATOR_DIRECTORY
    validator, planner = (directory / name for name in ENGLISH_VALIDATOR_FILES)
    return validator if validator.is_file() and planner.is_file() else None


def bundled_planner() -> Path | None:
    validator = bundled_validator(ENGLISH)
    return validator.with_name(ENGLISH_VALIDATOR_FILES[1]) if validator is not None else None
