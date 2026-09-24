# SPDX-License-Identifier: Apache-2.0
"""Sentence segmentation behind ``SentenceSegmenter`` (D-18).

``PysbdSentenceSegmenter`` uses ``pysbd`` with ``language="pl"`` (MIT).
``RegexSentenceSegmenter`` is the fallback and the implementation tests use
when they do not want to import pysbd. Both apply the same abbreviation
guard: ``np.``, ``tzn.``, ``itd.``, ``itp.``, ``m.in.``, ``ok.``, ``godz.``,
``ul.``, ``dr.``, ``prof.``, ``r.``, ``w.``, and ``św.`` do not end a sentence.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol, cast

ABBREVIATIONS: tuple[str, ...] = (
    "np.",
    "tzn.",
    "itd.",
    "itp.",
    "m.in.",
    "ok.",
    "godz.",
    "ul.",
    "dr.",
    "prof.",
    "r.",
    "w.",
    "św.",
)

_PUNCT = re.compile(r"[.!?…]+")
_CLOSERS = frozenset("\"'”»)]}")
_OPENERS = frozenset("\"'„«“([")


@dataclass(frozen=True, slots=True)
class SentenceSpan:
    """``text`` is ``source[start:end]`` with surrounding whitespace trimmed."""

    start: int
    end: int
    text: str


class SentenceSegmenter(Protocol):
    """Split one block into sentences without changing the block."""

    def segment(self, text: str) -> list[SentenceSpan]:
        """Sentence spans in order. Gaps between them are whitespace."""


class _PysbdEngine(Protocol):
    def segment(self, text: str) -> list[object]:
        """pysbd's ``char_span`` records."""


class RegexSentenceSegmenter:
    """Rule fallback. Splits on ``.!?…`` before whitespace and an uppercase,
    digit, or dash, unless the dot belongs to an abbreviation.
    """

    def segment(self, text: str) -> list[SentenceSpan]:
        if text.strip() == "":
            return []
        abbrevs = _abbreviation_spans(text)
        starts: list[int] = []
        for match in _PUNCT.finditer(text):
            if _covered(match.start(), match.end(), abbrevs):
                continue
            nxt = _next_start(text, match.end())
            if nxt is not None:
                starts.append(nxt)
        return apply_abbreviation_guard(text, _cuts(text, starts))


class PysbdSentenceSegmenter:
    """``pysbd.Segmenter(language="pl", clean=False, char_span=True)`` plus the guard."""

    def __init__(self) -> None:
        self._engine = _load_pysbd()

    def segment(self, text: str) -> list[SentenceSpan]:
        parsed = _parse_pysbd(text, self._engine.segment(text))
        if parsed is None:
            return RegexSentenceSegmenter().segment(text)
        return apply_abbreviation_guard(text, parsed)


def sentence_segmenter() -> SentenceSegmenter:
    """pysbd when it imports, otherwise the regex fallback."""
    try:
        return PysbdSentenceSegmenter()
    except ImportError:
        return RegexSentenceSegmenter()


def apply_abbreviation_guard(text: str, spans: list[SentenceSpan]) -> list[SentenceSpan]:
    """Merge a split that landed on an abbreviation's final dot."""
    if len(spans) < 2:
        return list(spans)
    abbrevs = _abbreviation_spans(text)
    if not abbrevs:
        return list(spans)
    merged: list[SentenceSpan] = [spans[0]]
    for span in spans[1:]:
        previous = merged[-1]
        if _abbreviation_boundary(previous.end, span.start, abbrevs):
            merged[-1] = SentenceSpan(previous.start, span.end, text[previous.start : span.end])
            continue
        merged.append(span)
    return merged


def _load_pysbd() -> _PysbdEngine:
    import pysbd

    factory = cast(Callable[..., _PysbdEngine], pysbd.Segmenter)
    return factory(language="pl", clean=False, char_span=True)


def _parse_pysbd(text: str, raw: object) -> list[SentenceSpan] | None:
    if not isinstance(raw, list):
        return None
    if text.strip() and not raw:
        return None
    spans: list[SentenceSpan] = []
    cursor = 0
    for item in raw:
        bounds = _bounds(item)
        if bounds is None:
            return None
        start, end = bounds
        if not 0 <= start <= end <= len(text) or start < cursor:
            return None
        begin, stop = _trim(text, start, end)
        if begin < stop:
            spans.append(SentenceSpan(begin, stop, text[begin:stop]))
        cursor = end
    return spans


def _bounds(item: object) -> tuple[int, int] | None:
    start = getattr(item, "start", None)
    end = getattr(item, "end", None)
    if isinstance(start, int) and isinstance(end, int):
        return start, end
    return None


def _abbreviation_spans(text: str) -> list[tuple[int, int]]:
    lowered = text.casefold()
    found: list[tuple[int, int]] = []
    for abbreviation in ABBREVIATIONS:
        needle = abbreviation.casefold()
        start = 0
        while True:
            index = lowered.find(needle, start)
            if index < 0:
                break
            end = index + len(needle)
            before = index == 0 or not lowered[index - 1].isalnum()
            after = end == len(lowered) or not lowered[end].isalnum()
            if before and after:
                found.append((index, end))
            start = index + 1
    return found


def _covered(start: int, end: int, abbrevs: list[tuple[int, int]]) -> bool:
    return all(any(begin <= index < stop for begin, stop in abbrevs) for index in range(start, end))


def _abbreviation_boundary(
    previous_end: int, next_start: int, abbrevs: list[tuple[int, int]]
) -> bool:
    return any(begin < previous_end and previous_end <= end <= next_start for begin, end in abbrevs)


def _next_start(text: str, punct_end: int) -> int | None:
    cursor = punct_end
    while cursor < len(text) and text[cursor] in _CLOSERS:
        cursor += 1
    if cursor >= len(text) or not text[cursor].isspace():
        return None
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    content = cursor
    while cursor < len(text) and text[cursor] in _OPENERS:
        cursor += 1
    if cursor >= len(text):
        return None
    nxt = text[cursor]
    if nxt.isupper() or nxt.isdigit() or nxt in "\u2014\u2013-":
        return content
    return None


def _cuts(text: str, starts: list[int]) -> list[SentenceSpan]:
    first = _skip_ws(text, 0)
    if first >= len(text):
        return []
    bounds = [first, *[start for start in starts if start > first], len(text)]
    spans: list[SentenceSpan] = []
    for begin, end in pairwise(bounds):
        trimmed_begin, stop = _trim(text, begin, end)
        if trimmed_begin < stop:
            spans.append(SentenceSpan(trimmed_begin, stop, text[trimmed_begin:stop]))
    return spans


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index
