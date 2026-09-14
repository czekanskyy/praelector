# SPDX-License-Identifier: Apache-2.0
"""Front-matter and skip candidates detection (EB-08).

Identifies ISBN lines, bare page numbers, copyright notices, and publishing imprints
that should be skipped during audiobook narration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SkipMatch:
    """A detected skip candidate region in text."""

    start: int
    end: int
    original: str
    proposed: str | None = None  # None for structural/skip spans
    category: str = "skip"
    rationale: str = ""
    confidence: float = 0.95


RE_ISBN = re.compile(
    r"\bISBN(?:-1[03])?:?\s*(?:97[89][-\s]?)?[0-9][0-9-\s]{8,15}[0-9xX]\b",
    re.IGNORECASE,
)

RE_BARE_PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")

RE_COPYRIGHT = re.compile(
    r"\b(copyright|\(c\)|©|wszelkie prawa zastrzeżone|all rights reserved)\b",
    re.IGNORECASE,
)

RE_PUBLISHING_IMPRINT = re.compile(
    r"\b(tytuł oryginału|redakcja|korekta|skład i łamanie|projekt okładki|druk i oprawa|wydanie [IVXLCDM\d]+|wydawnictwo)\b",
    re.IGNORECASE,
)

RE_TOC_HEADER = re.compile(r"^\s*(spis treści|table of contents)\s*$", re.IGNORECASE)


def detect_skip_candidates(text: str) -> list[SkipMatch]:
    """Detect regions or whole blocks that are candidates for skip spans."""
    matches: list[SkipMatch] = []
    stripped = text.strip()

    # 1. Bare page numbers (e.g. "12")
    if RE_BARE_PAGE_NUMBER.fullmatch(stripped):
        return [
            SkipMatch(
                start=0,
                end=len(text),
                original=text,
                category="skip",
                rationale="Bare page number",
                confidence=0.98,
            )
        ]

    # 2. ISBN lines
    isbn_match = RE_ISBN.search(text)
    if isbn_match:
        # If the block is largely the ISBN line (or starts with ISBN)
        if len(stripped) <= len(isbn_match.group(0)) + 15:
            return [
                SkipMatch(
                    start=0,
                    end=len(text),
                    original=text,
                    category="skip",
                    rationale="ISBN line",
                    confidence=0.98,
                )
            ]
        else:
            matches.append(
                SkipMatch(
                    start=isbn_match.start(),
                    end=isbn_match.end(),
                    original=isbn_match.group(0),
                    category="skip",
                    rationale="ISBN pattern match",
                    confidence=0.95,
                )
            )

    # 3. Copyright / Imprint entire blocks
    if RE_COPYRIGHT.search(stripped) or RE_PUBLISHING_IMPRINT.search(stripped):
        matches.append(
            SkipMatch(
                start=0,
                end=len(text),
                original=text,
                category="skip",
                rationale="Copyright / publication imprint metadata",
                confidence=0.92,
            )
        )
        return matches

    # 4. Table of contents header
    if RE_TOC_HEADER.fullmatch(stripped):
        matches.append(
            SkipMatch(
                start=0,
                end=len(text),
                original=text,
                category="skip",
                rationale="Table of contents header block",
                confidence=0.95,
            )
        )

    return matches
