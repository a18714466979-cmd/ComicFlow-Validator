"""Build the language-neutral illustration strips distributed with the action-card catalog."""

import argparse
from pathlib import Path

from PIL import Image

from scripts.action_art.drawing import Canvas, HEIGHT, WIDTH

from src.action_card_catalog import ACTION_PREVIEW_DIRECTORY, ACTION_PRESETS


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ACTION_PREVIEW_DIRECTORY
EXPECTED = tuple(preset.id for preset in ACTION_PRESETS)

def load_scenes():
    from scripts.action_art.everyday import SCENES as everyday
    from scripts.action_art.other_props import SCENES as other_props
    from scripts.action_art.stage_blades import SCENES as stage_blades

    all_scenes = {}
    for module in (everyday, stage_blades, other_props):
        duplicates = all_scenes.keys() & module.keys()
        if duplicates:
            raise ValueError(f"Duplicated card previews: {', '.join(sorted(duplicates))}")
        all_scenes.update(module)

    missing = set(EXPECTED) - all_scenes.keys()
    unknown = all_scenes.keys() - set(EXPECTED)
    if missing or unknown:
        raise ValueError(f"Preview catalog mismatch. Missing: {sorted(missing)}; unknown: {sorted(unknown)}")
    return all_scenes


def render_strip(frames):
    if len(frames) != 3:
        raise ValueError("Each card preview needs three frames.")
    strip = Image.new("RGB", (WIDTH * len(frames), HEIGHT))
    for index, illustration in enumerate(frames):
        canvas = Canvas()
        illustration(canvas)
        strip.paste(canvas.finish(), (WIDTH * index, 0))
    return strip


def build(output, selected=()):
    scenes = load_scenes()
    output.mkdir(parents=True, exist_ok=True)
    for identifier in selected or EXPECTED:
        strip = render_strip(scenes[identifier])
        strip.save(output / f"{identifier}.webp", format="WEBP", quality=82, method=6)
    return len(selected or EXPECTED)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--only", nargs="+", choices=EXPECTED, metavar="CARD")
    args = parser.parse_args()
    count = build(args.output, args.only or ())
    print(f"Rendered {count} action-card preview strips into {args.output}")


if __name__ == "__main__":
    main()
