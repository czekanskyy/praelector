# SPDX-License-Identifier: Apache-2.0
"""Apply accepted suggestions to one block (AI-07).

Conversion artefacts rewrite the printed text. Readings become pronunciation
spans and leave the print alone. Dialogue splits tile the block, and a gender
mark lands on the matching dialogue span. A suggestion whose ``original`` is
no longer in the text is a conflict and is not applied.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from praelector.domain.enums import SuggestionCategory
from praelector.text.suggestion import SegmentMark, Suggestion

_REWRITE = SuggestionCategory.CONVERSION_ARTIFACT
_PRONUNCIATION = frozenset(
    {
        SuggestionCategory.FOREIGN_WORD,
        SuggestionCategory.ACRONYM,
        SuggestionCategory.TOPONYM,
        SuggestionCategory.NUMERAL,
        SuggestionCategory.ORDINAL_HEADING,
        SuggestionCategory.DICT_HIT,
    }
)


@dataclass(frozen=True, slots=True)
class AppliedSpan:
    """One span in the text after rewrites. Offsets refer to ``ApplyResult.text``."""

    kind: str
    start: int
    end: int
    spoken: str = ""
    gender: str = ""
    gender_confidence: float = 0.0
    speaker_id: str = ""


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """The block after the batch. ``conflicts`` were skipped."""

    text: str
    spans: tuple[AppliedSpan, ...]
    conflicts: tuple[Suggestion, ...]


def apply_block(text: str, suggestions: Sequence[Suggestion]) -> ApplyResult:
    """Apply ``suggestions`` to ``text``. The input string is not mutated."""
    rewrites = [item for item in suggestions if item.kind == _REWRITE]
    others = [item for item in suggestions if item.kind != _REWRITE]
    conflicts: list[Suggestion] = []
    current = text
    for item in sorted(rewrites, key=lambda entry: entry.start, reverse=True):
        if current[item.start : item.end] != item.original:
            conflicts.append(item)
            continue
        replacement = item.replacement
        current = current[: item.start] + replacement + current[item.end :]
        shifted: list[Suggestion] = []
        for other in others:
            moved = _shift_suggestion(other, item.start, item.end, replacement)
            if moved is None:
                conflicts.append(other)
            else:
                shifted.append(moved)
        others = shifted

    spans: list[AppliedSpan] = []
    genders: list[Suggestion] = []
    for item in others:
        if current[item.start : item.end] != item.original:
            conflicts.append(item)
            continue
        if item.kind in _PRONUNCIATION:
            spans.append(
                AppliedSpan("pronunciation", item.start, item.end, spoken=item.replacement)
            )
        elif item.kind == SuggestionCategory.DIALOGUE_SPLIT and item.segments:
            spans.extend(_dialogue_spans(item, len(current)))
        elif item.kind == "skip":
            spans.append(AppliedSpan("skip", item.start, item.end))
        elif item.kind == SuggestionCategory.SPEAKER_GENDER:
            genders.append(item)
        else:
            conflicts.append(item)

    spans = _paint_gender(spans, genders)
    spans.sort(key=lambda span: (span.start, span.end, span.kind))
    return ApplyResult(current, tuple(spans), tuple(conflicts))


def _dialogue_spans(item: Suggestion, length: int) -> list[AppliedSpan]:
    spans: list[AppliedSpan] = []
    for mark in item.segments:
        if not 0 <= mark.start <= mark.end <= length:
            continue
        if mark.kind not in {"narration", "dialogue"}:
            continue
        spans.append(AppliedSpan(mark.kind, mark.start, mark.end))
    return spans


def _paint_gender(spans: list[AppliedSpan], genders: Sequence[Suggestion]) -> list[AppliedSpan]:
    painted: list[AppliedSpan] = []
    for span in spans:
        if span.kind != "dialogue":
            painted.append(span)
            continue
        match = next(
            (item for item in genders if item.start == span.start and item.end == span.end),
            None,
        )
        if match is None:
            painted.append(span)
            continue
        painted.append(
            replace(
                span,
                gender=match.replacement,
                gender_confidence=match.confidence,
                speaker_id=match.speaker_id,
            )
        )
    return painted


def _shift_suggestion(
    item: Suggestion, rewrite_start: int, rewrite_end: int, replacement: str
) -> Suggestion | None:
    delta = len(replacement) - (rewrite_end - rewrite_start)
    if item.end <= rewrite_start:
        return item
    if item.start >= rewrite_end:
        return _slide(item, delta)
    if item.start <= rewrite_start and item.end >= rewrite_end:
        return _rewrite_inside(item, rewrite_start, rewrite_end, replacement, delta)
    return None


def _slide(item: Suggestion, delta: int) -> Suggestion:
    if delta == 0:
        return item
    segments = tuple(
        replace(mark, start=mark.start + delta, end=mark.end + delta) for mark in item.segments
    )
    return replace(item, start=item.start + delta, end=item.end + delta, segments=segments)


def _rewrite_inside(
    item: Suggestion, rewrite_start: int, rewrite_end: int, replacement: str, delta: int
) -> Suggestion | None:
    local_start = rewrite_start - item.start
    local_end = rewrite_end - item.start
    original = item.original[:local_start] + replacement + item.original[local_end:]
    moved: list[SegmentMark] = []
    for mark in item.segments:
        if mark.end <= rewrite_start:
            moved.append(mark)
        elif mark.start >= rewrite_end:
            moved.append(replace(mark, start=mark.start + delta, end=mark.end + delta))
        else:
            return None
    return replace(
        item,
        end=item.end + delta,
        original=original,
        segments=tuple(moved),
    )
