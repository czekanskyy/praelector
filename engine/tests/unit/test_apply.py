# SPDX-License-Identifier: Apache-2.0
"""Accepted suggestions rewrite artefacts and leave readings as spans."""

from __future__ import annotations

from praelector.domain.enums import SuggestionCategory
from praelector.text.apply import apply_block
from praelector.text.prepass import prepass
from praelector.text.suggestion import SegmentMark, make_suggestion


def test_a_whitespace_artifact_rewrites_and_a_later_reading_keeps_its_place() -> None:
    text = "Zegar.  Było 18:00."
    found = prepass([text])
    result = apply_block(text, found)
    assert result.conflicts == ()
    assert result.text == "Zegar. Było 18:00."
    spoken = next(span for span in result.spans if span.kind == "pronunciation")
    assert result.text[spoken.start : spoken.end] == "18:00"
    assert spoken.spoken == "osiemnastej"


def test_a_stale_original_is_a_conflict() -> None:
    text = "Anna."
    stale = make_suggestion(
        text="Anna  .",
        start=4,
        end=6,
        replacement=" ",
        kind=SuggestionCategory.CONVERSION_ARTIFACT,
        reason="whitespace",
        confidence=0.99,
    )
    result = apply_block(text, [stale])
    assert result.text == text
    assert result.spans == ()
    assert result.conflicts == (stale,)


def test_dialogue_and_gender_become_spans_without_editing_the_print() -> None:
    text = "— Nie zdążymy — powiedziała cicho."
    found = prepass([text])
    result = apply_block(text, found)
    assert result.text == text
    dialogue = next(span for span in result.spans if span.kind == "dialogue")
    assert text[dialogue.start : dialogue.end] == "Nie zdążymy"
    assert dialogue.gender == "female"
    assert dialogue.gender_confidence >= 0.95
    narration = next(span for span in result.spans if span.kind == "narration")
    assert text[narration.start : narration.end] == "powiedziała cicho."


def test_a_pronunciation_does_not_change_the_printed_token() -> None:
    text = "W IT nikt."
    found = [item for item in prepass([text]) if item.kind == SuggestionCategory.ACRONYM]
    result = apply_block(text, found)
    assert result.text == text
    assert result.spans[0].spoken == "aj ti"
    assert text[result.spans[0].start : result.spans[0].end] == "IT"


def test_segments_shift_when_an_earlier_rewrite_changes_length() -> None:
    text = "A  — Cześć — powiedziała."
    split = make_suggestion(
        text=text,
        start=0,
        end=len(text),
        replacement="",
        kind=SuggestionCategory.DIALOGUE_SPLIT,
        reason="dialogue",
        confidence=0.9,
        segments=(
            SegmentMark("narration", 0, 1),
            SegmentMark("dialogue", 5, 10),
            SegmentMark("narration", 13, len(text)),
        ),
    )
    rewrite = make_suggestion(
        text=text,
        start=1,
        end=3,
        replacement=" ",
        kind=SuggestionCategory.CONVERSION_ARTIFACT,
        reason="whitespace",
        confidence=0.99,
    )
    result = apply_block(text, [split, rewrite])
    assert result.conflicts == ()
    assert result.text == "A — Cześć — powiedziała."
    dialogue = next(span for span in result.spans if span.kind == "dialogue")
    assert result.text[dialogue.start : dialogue.end] == "Cześć"
