# SPDX-License-Identifier: Apache-2.0
"""Sentence segmentation with Polish abbreviation guards (D-18).

Provides SentenceSegmenter protocol, PysbdSentenceSegmenter using pysbd,
and a regex-based fallback segmenter with Polish abbreviation protections.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple, Protocol


class SentenceSegment(NamedTuple):
    """A sentence segment with character offsets in the source text."""

    start: int
    end: int
    text: str


class SentenceSegmenter(Protocol):
    """Protocol for sentence segmentation."""

    def segment(self, text: str) -> list[SentenceSegment]:
        """Split text into sentences with exact character offsets."""
        ...


# Polish abbreviations that should not trigger sentence boundaries
POLISH_ABBREVIATIONS = [
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
    "sw.",
    "tzw.",
    "hab.",
    "kol.",
    "mgr.",
    "gen.",
    "płk.",
    "kpt.",
    "red.",
    "lek.",
    "ks.",
    "doc.",
]

# Replacement character for periods inside guarded abbreviations
_GUARD_CHAR = "\u200b"


class PysbdSentenceSegmenter:
    """Sentence segmenter using pysbd with Polish language rules and abbreviation guards."""

    def __init__(self) -> None:
        try:
            import pysbd  # type: ignore[import-untyped]

            self._segmenter: Any = pysbd.Segmenter(language="pl", clean=False)
        except ImportError:
            self._segmenter = None
        self._fallback = RegexSentenceSegmenter()

    def segment(self, text: str) -> list[SentenceSegment]:
        if not text:
            return []

        if self._segmenter is None:
            return self._fallback.segment(text)

        # Protect known abbreviations
        protected_text = text
        for abbr in POLISH_ABBREVIATIONS:
            if "." in abbr:
                # Replace period in abbreviation when followed by space or punctuation
                guarded = abbr.replace(".", _GUARD_CHAR)
                pattern = r"\b" + re.escape(abbr)
                protected_text = re.sub(pattern, guarded, protected_text, flags=re.IGNORECASE)

        try:
            # pysbd segmentation
            raw_segments: list[str] = self._segmenter.segment(protected_text)
        except Exception:
            return self._fallback.segment(text)

        results: list[SentenceSegment] = []
        cur_pos = 0

        for raw_seg in raw_segments:
            seg_len = len(raw_seg)
            # Restore original substring from source text to guarantee character match
            end_pos = cur_pos + seg_len
            actual_text = text[cur_pos:end_pos]
            if actual_text:
                results.append(SentenceSegment(start=cur_pos, end=end_pos, text=actual_text))
            cur_pos = end_pos

        return results


class RegexSentenceSegmenter:
    """Fallback regex sentence segmenter for Polish text."""

    def __init__(self) -> None:
        # Sentence ending boundary: ., !, ?, … followed by whitespace and capital letter or dash or quote
        self._pattern = re.compile(r"([.!?…])\s+(?=[A-ZŁŚŻŹĆŃÓ„«—–\"])")

    def segment(self, text: str) -> list[SentenceSegment]:
        if not text:
            return []

        segments: list[SentenceSegment] = []
        cur = 0

        for match in self._pattern.finditer(text):
            split_point = match.start(1) + 1  # end right after punctuation
            prefix = text[cur:split_point].strip().lower()
            if any(prefix.endswith(abbr.lower()) for abbr in POLISH_ABBREVIATIONS):
                continue
            seg_text = text[cur:split_point]
            segments.append(SentenceSegment(start=cur, end=split_point, text=seg_text))
            cur = match.end()

        if cur < len(text):
            segments.append(SentenceSegment(start=cur, end=len(text), text=text[cur:]))

        return segments
