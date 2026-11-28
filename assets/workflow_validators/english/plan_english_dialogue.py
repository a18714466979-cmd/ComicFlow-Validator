#!/usr/bin/env python3
"""Plan SD2 dialogue capacity from approved sentence units, before assigning final shots."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAX_ENGLISH_WORDS = 60
# Keep contractions and hyphenated terms/IDs intact. Em dashes separate words.
WORD_PART = r"[^\W_](?:[^\W_]|[\u0300-\u036f])*"
WORD = re.compile(rf"{WORD_PART}(?:['’\-‐‑]{WORD_PART}|(?<=\d)[.,](?=\d)\d+)*")


def english_word_count(text: str) -> int:
    return sum(1 for _ in WORD.finditer(text))


def plan_dialogue(sentences: list[dict]) -> list[dict]:
    """Pack complete spoken sentence units without changing their source spans."""
    groups = []
    fragments = []
    group_words = 0
    previous = {}
    for sentence in sentences:
        source_id, speaker, text = (sentence[key] for key in ("id", "speaker", "text"))
        if not all(isinstance(value, str) for value in (source_id, speaker, text)):
            raise ValueError("id, speaker and text must be strings")
        text = text.strip()
        offset, limit = sentence.get("start", 0), sentence.get("end", len(text))
        if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", source_id) or not speaker.strip()
                or re.search(r"[\r\n\u3400-\u9fff]", text)):
            raise ValueError(f"{source_id}: provide a valid ID, speaker and single-line approved English")
        if type(offset) is not int or type(limit) is not int or not 0 <= offset < limit <= len(text):
            raise ValueError(f"{source_id}: invalid source span {offset}:{limit}")
        if source_id in previous and previous[source_id] != (speaker, text, offset):
            raise ValueError(f"{source_id}: continuation changed speaker/source or skipped/repeated a span")

        sentence_words = 0
        for word in WORD.finditer(text):
            if word.end() <= offset or word.start() >= limit:
                continue
            if word.start() < offset or word.end() > limit:
                raise ValueError(f"{source_id}: source span cuts a word")
            sentence_words += 1
        if not sentence_words:
            raise ValueError(f"{source_id}: source span contains no spoken words")
        if sentence_words > MAX_ENGLISH_WORDS:
            raise ValueError(
                f"{source_id} ({offset}:{limit}): one sentence unit has {sentence_words} words, "
                f"above the {MAX_ENGLISH_WORDS}-word limit; confirm the approved sentence boundaries"
            )
        previous[source_id] = (speaker, text, limit)

        if group_words + sentence_words > MAX_ENGLISH_WORDS:
            groups.append({"words": group_words, "fragments": fragments})
            fragments, group_words = [], 0
        fragments.append({
            "id": source_id, "speaker": speaker, "start": offset, "end": limit,
            "cue": "续说" if offset else "首说", "text": text[offset:limit].strip(),
        })
        group_words += sentence_words
    if fragments:
        groups.append({"words": group_words, "fragments": fragments})
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="JSON array of ordered approved sentence units with {id, speaker, text} and optional start/end")
    args = parser.parse_args()
    try:
        sentences = json.loads(args.source.read_text(encoding="utf-8-sig"))
        if not isinstance(sentences, list):
            raise ValueError("expected a JSON array of sentence units")
        plan = plan_dialogue(sentences)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
