# SPDX-License-Identifier: Apache-2.0
"""Deterministic pre-pass for one chapter's blocks (AI-02, PLAN.md §5.1).

Order, per the plan: normalise, then front-matter skip candidates, then
dialogue, then numerals, then acronyms (with toponyms and English-looking
tokens). Skip spans come from ``praelector.ebook.frontmatter``. Later
detectors do not overlap a skip span or an earlier numeral. A block that is
entirely a skip span is not scanned for dialogue. Nothing in the block
sequence is mutated.

Gender uses the dialogue tiling and may look one block either side for a
pronoun. A lexicon hit then replaces an overlapping numeral, acronym, toponym,
or foreign-word mark.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from praelector.domain.enums import BlockKind
from praelector.ebook.frontmatter import TextCarrier, skip_candidates
from praelector.text.acronyms import lexical_suggestions
from praelector.text.dialogue import dialogue_suggestions
from praelector.text.gender import gender_suggestions
from praelector.text.lexicon import LexiconRule, lexicon_suggestions
from praelector.text.normalize import normalization_suggestions
from praelector.text.numerals_pl import numeral_suggestions
from praelector.text.suggestion import Suggestion

SKIP_KIND = "skip"
_SKIP_CONFIDENCE = 0.92


_LEXICON_WINS = frozenset(
    {
        "foreign_word",
        "acronym",
        "toponym",
        "numeral",
        "ordinal_heading",
    }
)


def prepass(
    blocks: Sequence[str | TextCarrier],
    *,
    chapter_titles: Sequence[str] = (),
    lexicon: Sequence[LexiconRule] = (),
) -> list[Suggestion]:
    """Combined suggestions. ``blocks`` and each ``text`` are left as they were."""
    texts = [_text_of(block) for block in blocks]
    suggestions: list[Suggestion] = []
    blocked: dict[int, list[tuple[int, int]]] = {}
    for span in skip_candidates(blocks, chapter_titles=chapter_titles):
        text = texts[span.block_index]
        suggestions.append(
            Suggestion(
                kind=SKIP_KIND,
                start=span.start,
                end=span.end,
                original=text[span.start : span.end],
                replacement="",
                reason=span.reason,
                confidence=_SKIP_CONFIDENCE,
                block_index=span.block_index,
            )
        )
        blocked.setdefault(span.block_index, []).append((span.start, span.end))

    for index, text in enumerate(texts):
        suggestions.extend(_at(index, normalization_suggestions(text)))
        claimed = list(blocked.get(index, ()))
        if not _covers_all(len(text), claimed):
            suggestions.extend(_at(index, dialogue_suggestions(text)))
        heading = _is_heading(blocks[index])
        for item in numeral_suggestions(text, heading=heading):
            if _overlaps(item.start, item.end, claimed):
                continue
            suggestions.append(replace(item, block_index=index))
            claimed.append((item.start, item.end))
        for item in lexical_suggestions(text):
            if _overlaps(item.start, item.end, claimed):
                continue
            suggestions.append(replace(item, block_index=index))
    suggestions.extend(gender_suggestions(texts))
    hits: list[Suggestion] = []
    for index, text in enumerate(texts):
        if _covers_all(len(text), blocked.get(index, ())):
            continue
        hits.extend(_at(index, lexicon_suggestions(text, lexicon)))
    if hits:
        suggestions = [
            item
            for item in suggestions
            if item.kind not in _LEXICON_WINS
            or not any(
                item.block_index == hit.block_index
                and _overlaps(item.start, item.end, [(hit.start, hit.end)])
                for hit in hits
            )
        ]
        suggestions.extend(hits)
    suggestions.sort(
        key=lambda item: (item.block_index, item.start, item.end, item.kind, item.reason)
    )
    return suggestions


def _text_of(block: str | TextCarrier) -> str:
    if isinstance(block, str):
        return block
    return block.text


def _is_heading(block: object) -> bool:
    kind = getattr(block, "kind", None)
    if isinstance(kind, BlockKind):
        return kind is BlockKind.HEADING
    return kind == BlockKind.HEADING


def _at(block_index: int, items: Sequence[Suggestion]) -> list[Suggestion]:
    return [replace(item, block_index=block_index) for item in items]


def _covers_all(length: int, spans: Sequence[tuple[int, int]]) -> bool:
    return length > 0 and any(begin <= 0 and stop >= length for begin, stop in spans)


def _overlaps(start: int, end: int, spans: Sequence[tuple[int, int]]) -> bool:
    return any(start < stop and end > begin for begin, stop in spans)
