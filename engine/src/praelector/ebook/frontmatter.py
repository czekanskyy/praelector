# SPDX-License-Identifier: Apache-2.0
"""Front-matter skip candidates (EB-08, PLAN.md §5.1 item 2).

The heuristics flag spans. They do not delete blocks: a skip is a suggestion
the reader can override, and the text stays in the working EPUB.

A block is a candidate when it is an ISBN line, a copyright line (``Copyright``,
``All rights reserved``, ``Wszelkie prawa zastrzeżone``), an original-title
line (``Tytuł oryginału``), an editorial credit (``Redakcja``, ``Korekta``,
``Skład``, ``Projekt okładki``), a bare page number, or a ``Spis treści``
heading followed by a run of at least five short blocks that match chapter
titles. Line-level signals only fire on a short block, so a narrative sentence
that happens to contain the word does not become a skip.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

_MAX_LINE_CHARS: Final = 400
_MAX_TOC_ENTRY_CHARS: Final = 120
_MIN_TOC_RUN: Final = 5

_PAGE_NUMBER = re.compile(r"\d{1,4}")
_ISBN = re.compile(r"(?i)\bISBN(?:-1[03])?\b\s*:?\s*[0-9][0-9Xx \t-]{8,24}[0-9Xx]")
_COPYRIGHT_WORD = re.compile(r"(?i)\bcopyright\b")
_EDITORIAL = re.compile(r"(?i)\b(?:redakcja|korekta|skład|sklad|projekt okładki|projekt okladki)\b")
_TOC_HEADINGS: Final = frozenset({"spis treści", "spis tresci", "table of contents"})
_ORIGINAL_TITLE: Final = ("tytuł oryginału", "tytul oryginalu")
_COPYRIGHT_PHRASES: Final = ("all rights reserved", "wszelkie prawa zastrzeżone")

REASON_ISBN: Final = "isbn"
REASON_COPYRIGHT: Final = "copyright"
REASON_ORIGINAL_TITLE: Final = "original_title"
REASON_EDITORIAL: Final = "editorial"
REASON_PAGE_NUMBER: Final = "page_number"
REASON_TOC: Final = "toc"


class TextCarrier(Protocol):
    """Anything with the block text the heuristics look at."""

    text: str


@dataclass(frozen=True, slots=True)
class SkipSpan:
    """A candidate skip covering ``blocks[block_index].text[start:end]``."""

    block_index: int
    start: int
    end: int
    reason: str


def skip_candidates(
    blocks: Sequence[str | TextCarrier],
    *,
    chapter_titles: Sequence[str] = (),
) -> list[SkipSpan]:
    """Skip spans for ``blocks``, in block order. The sequence itself is unchanged."""
    texts = [_text_of(block) for block in blocks]
    spans: list[SkipSpan] = []
    claimed: set[int] = set()
    for index, text in enumerate(texts):
        reason = _line_reason(text)
        if reason is None:
            continue
        spans.append(SkipSpan(block_index=index, start=0, end=len(text), reason=reason))
        claimed.add(index)
    spans.extend(_toc_spans(texts, _title_set(chapter_titles), claimed))
    spans.sort(key=lambda span: (span.block_index, span.start))
    return spans


def _text_of(block: str | TextCarrier) -> str:
    if isinstance(block, str):
        return block
    return block.text


def _title_set(titles: Sequence[str]) -> set[str]:
    return {_norm(title) for title in titles if _norm(title)}


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _line_reason(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    if _PAGE_NUMBER.fullmatch(stripped):
        return REASON_PAGE_NUMBER
    if len(stripped) > _MAX_LINE_CHARS:
        return None
    if _ISBN.search(stripped):
        return REASON_ISBN
    folded = stripped.casefold()
    if _COPYRIGHT_WORD.search(stripped) or any(phrase in folded for phrase in _COPYRIGHT_PHRASES):
        return REASON_COPYRIGHT
    if any(phrase in folded for phrase in _ORIGINAL_TITLE):
        return REASON_ORIGINAL_TITLE
    if _EDITORIAL.search(stripped):
        return REASON_EDITORIAL
    return None


def _toc_spans(texts: Sequence[str], titles: set[str], claimed: set[int]) -> list[SkipSpan]:
    spans: list[SkipSpan] = []
    index = 0
    while index < len(texts):
        if index in claimed or _norm(texts[index]) not in _TOC_HEADINGS:
            index += 1
            continue
        run: list[int] = []
        cursor = index + 1
        while cursor < len(texts) and cursor not in claimed and _toc_entry(texts[cursor], titles):
            run.append(cursor)
            cursor += 1
        if len(run) >= _MIN_TOC_RUN:
            spans.append(SkipSpan(index, 0, len(texts[index]), REASON_TOC))
            spans.extend(SkipSpan(item, 0, len(texts[item]), REASON_TOC) for item in run)
        index = cursor if run else index + 1
    return spans


def _toc_entry(text: str, titles: set[str]) -> bool:
    normalised = _norm(text)
    if not normalised or len(normalised) > _MAX_TOC_ENTRY_CHARS:
        return False
    if titles:
        return normalised in titles
    return normalised[-1] not in ".!?…"
