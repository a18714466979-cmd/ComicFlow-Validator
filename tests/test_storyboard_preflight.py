import json

import pytest

from src.storyboard_preflight import image_budget, plan_dialogue


@pytest.mark.parametrize(
    ("counts", "expected"),
    [((0, 0, 0, 0), (1, 8)), ((2, 2, 1, 3), (9, 0)), ((2, 2, 2, 3), (10, -1))],
)
def test_budget_counts_storyboard_and_only_image_files(counts, expected):
    assert image_budget(*counts) == expected


def test_budget_rejects_negative_count():
    with pytest.raises(ValueError, match="非负整数"):
        image_budget(0, 0, -1, 1)


def test_dialogue_preflight_passes_ordered_original_text_to_workflow_script(tmp_path):
    planner = tmp_path / "流程脚本.py"
    planner.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "source = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "assert [row['id'] for row in source] == ['D005', 'D003']\n"
        "frag = source[0]\n"
        "assert frag['text'] == \"She can't leave. Hold the door.\"\n"
        "assert (frag['start'], frag['end']) == (17, 31)\n"
        "print(json.dumps([{'words': 3, 'fragments': [dict(frag, cue='续说', text=frag['text'][17:31])]}]))\n",
        encoding="utf-8",
    )
    dialogues = [
        {"id": "D005", "speaker": "维拉", "text": "She can't leave. Hold the door.", "start": 17, "end": 31},
        {"id": "D003", "speaker": "凯尔", "text": "Go."},
    ]

    groups = plan_dialogue("\ufeff" + json.dumps(dialogues, ensure_ascii=False), planner)

    assert groups[0]["fragments"] == [dict(dialogues[0], cue="续说", text="Hold the door.")]


def test_dialogue_preflight_reports_workflow_sentence_error(tmp_path):
    planner = tmp_path / "planner.py"
    planner.write_text(
        "import argparse\nparser = argparse.ArgumentParser()\n"
        "parser.error('D010 (0:304): one sentence unit has 61 words, above the 60-word limit')\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="^D010 .*61 words"):
        plan_dialogue('[{"id":"D010"}]', planner)


def test_dialogue_preflight_reports_invalid_json_position(tmp_path):
    with pytest.raises(ValueError, match="第 2 行"):
        plan_dialogue('[\n  invalid\n]', tmp_path / "unused.py")
