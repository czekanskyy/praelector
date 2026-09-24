# SPDX-License-Identifier: Apache-2.0
"""Dialogue segmentation for one block (DG-01, DG-02, PLAN.md §5.2).

A paragraph-initial dash and a colon-plus-dash always open dialogue. A
whitespace-flanked dash opens narration only when the following words start
with a verb of saying, and opens dialogue when the next dash is that speech
tag. An unconfirmed dash stays inside the current span and yields a
review-only suggestion. A balanced quote without a speech verb in the same
or adjacent sentence stays narration at confidence 0.40. The block text is
not rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from praelector.domain.enums import SuggestionCategory
from praelector.text.segment import RegexSentenceSegmenter
from praelector.text.suggestion import SegmentMark, Suggestion, make_suggestion

_DASHES = frozenset("-\u2013\u2014")
_WORD_EXTRA = frozenset("-'\u2019")
_QUOTE_PAIRS = {
    "\u201e": "\u201d",
    "\u00ab": "\u00bb",
    "\u201c": "\u201d",
    '"': '"',
    "\u201d": "\u201d",
}
_PRONOUNS = frozenset(
    {
        "ja",
        "ty",
        "on",
        "ona",
        "ono",
        "my",
        "wy",
        "oni",
        "one",
        "mu",
        "jej",
        "go",
        "ją",
        "im",
        "ich",
    }
)
_HIGH = 0.90
_ASIDE = 0.45
_QUOTE = 0.40
_UNBALANCED = 0.35
_KIND = SuggestionCategory.DIALOGUE_SPLIT


@dataclass(frozen=True, slots=True)
class Segment:
    """``text[start:end]`` with the dash or quote marks left outside the span."""

    kind: str
    start: int
    end: int
    confidence: float

    def slice(self, text: str) -> str:
        return text[self.start : self.end]


@dataclass(frozen=True, slots=True)
class _Dash:
    start: int
    content: int
    kind: str


def speech_verbs() -> frozenset[str]:
    """Inflected forms from ``text/data/speech_verbs_pl.txt``."""
    path = Path(__file__).with_name("data") / "speech_verbs_pl.txt"
    words: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.split("#", 1)[0].strip().casefold()
        if word:
            words.append(word)
    return frozenset(words)


_VERBS = speech_verbs()


def segment_block(text: str) -> list[Segment]:
    """High-confidence tiling. Review-only candidates stay narration."""
    if text.strip() == "":
        return []
    tiling, _review = _analyse(text)
    return tiling


def dialogue_suggestions(text: str) -> list[Suggestion]:
    """One ``dialogue_split`` when the block has dialogue or a review candidate."""
    if text.strip() == "":
        return []
    tiling, review = _analyse(text)
    if review is not None:
        confidence, reason, proposed = review
        return [_suggestion(text, proposed, reason, confidence)]
    if not any(segment.kind == "dialogue" for segment in tiling):
        return []
    return [_suggestion(text, tiling, "dialogue", _HIGH)]


def _analyse(
    text: str,
) -> tuple[list[Segment], tuple[float, str, list[Segment]] | None]:
    dashes = _find_dashes(text)
    confirmed = _confirmed_indexes(text, dashes)
    if confirmed:
        tiling = _dash_tiling(text, dashes, confirmed)
        return tiling, None
    quotes, unbalanced = _find_quotes(text)
    if unbalanced or (dashes and len(dashes) % 2 == 1):
        proposed = _loose_pieces(text, dashes, quotes)
        reason = "unbalanced_quote" if unbalanced else "odd_dash"
        return _narration(text), (_UNBALANCED, reason, proposed)
    if dashes:
        proposed = _loose_pieces(text, dashes, quotes)
        return _narration(text), (_ASIDE, "unconfirmed_dash", proposed)
    spoken = [quote for quote in quotes if _quote_has_speech(text, quote)]
    if spoken:
        return _quote_tiling(text, quotes), None
    if quotes:
        proposed = _quote_tiling(text, quotes, confidence=_QUOTE)
        return _narration(text), (_QUOTE, "quote_without_verb", proposed)
    return _narration(text), None


def _suggestion(text: str, segments: list[Segment], reason: str, confidence: float) -> Suggestion:
    marks = tuple(SegmentMark(segment.kind, segment.start, segment.end) for segment in segments)
    return make_suggestion(
        text=text,
        start=0,
        end=len(text),
        replacement="",
        kind=_KIND,
        reason=reason,
        confidence=confidence,
        segments=marks,
    )


def _narration(text: str) -> list[Segment]:
    start, end = _trim(text, 0, len(text))
    if start >= end:
        return []
    return [Segment("narration", start, end, 1.0)]


def _find_dashes(text: str) -> list[_Dash]:
    found: list[_Dash] = []
    index = 0
    while index < len(text):
        if text[index] not in _DASHES:
            index += 1
            continue
        content = _skip_ws(text, index + 1)
        trailing = content >= len(text)
        followed = trailing or text[index + 1].isspace()
        if not followed:
            index += 1
            continue
        kind = _dash_kind(text, index)
        if kind is None and not trailing:
            index += 1
            continue
        if kind is None and trailing and _has_ws_before(text, index):
            kind = "trailing"
        if kind is None:
            index += 1
            continue
        found.append(_Dash(index, content, kind))
        index += 1
    return found


def _dash_kind(text: str, index: int) -> str | None:
    if text[:index].strip() == "":
        return "initial"
    if _colon_before(text, index):
        return "colon"
    if _has_ws_before(text, index):
        return "flanked"
    return None


def _colon_before(text: str, index: int) -> bool:
    cursor = index - 1
    while cursor >= 0 and text[cursor].isspace():
        cursor -= 1
    return cursor >= 0 and text[cursor] == ":"


def _has_ws_before(text: str, index: int) -> bool:
    return index > 0 and text[index - 1].isspace()


def _confirmed_indexes(text: str, dashes: list[_Dash]) -> list[int]:
    state = "narration"
    speech_narration = False
    chosen: list[int] = []
    for index, dash in enumerate(dashes):
        if dash.kind in {"initial", "colon"}:
            chosen.append(index)
            state = "dialogue"
            speech_narration = False
            continue
        if dash.kind == "trailing" and state == "dialogue":
            chosen.append(index)
            state = "narration"
            speech_narration = False
            continue
        if dash.kind == "flanked" and _starts_with_speech(text, dash.content):
            chosen.append(index)
            state = "narration"
            speech_narration = True
            continue
        opens = (
            dash.kind == "flanked"
            and state == "narration"
            and not speech_narration
            and _next_is_speech(text, dashes, index)
        )
        closes = dash.kind == "flanked" and state == "narration" and speech_narration
        if opens or closes:
            chosen.append(index)
            state = "dialogue"
            speech_narration = False
    return chosen


def _next_is_speech(text: str, dashes: list[_Dash], index: int) -> bool:
    if index + 1 >= len(dashes):
        return False
    nxt = dashes[index + 1]
    return nxt.kind == "flanked" and _starts_with_speech(text, nxt.content)


def _starts_with_speech(text: str, index: int) -> bool:
    tokens = _tokens(text, index, limit=3)
    for offset, surface in enumerate(tokens):
        if surface.casefold() in _VERBS:
            return all(_prefix(token) for token in tokens[:offset])
    return False


def _prefix(token: str) -> bool:
    return token.casefold() in _PRONOUNS or token[:1].isupper()


def _tokens(text: str, index: int, limit: int) -> list[str]:
    tokens: list[str] = []
    cursor = index
    while cursor < len(text) and len(tokens) < limit:
        while cursor < len(text) and not text[cursor].isalnum():
            if text[cursor] in _DASHES:
                return tokens
            cursor += 1
        start = cursor
        while cursor < len(text) and (text[cursor].isalnum() or text[cursor] in _WORD_EXTRA):
            cursor += 1
        if start == cursor:
            break
        tokens.append(text[start:cursor])
    return tokens


def _dash_tiling(text: str, dashes: list[_Dash], chosen: list[int]) -> list[Segment]:
    state = "narration"
    cursor = 0
    pieces: list[Segment] = []
    for index in chosen:
        dash = dashes[index]
        _append(pieces, text, state, cursor, dash.start)
        cursor = dash.content
        state = _state_after(text, dash, state)
    _append(pieces, text, state, cursor, len(text))
    return pieces


def _state_after(text: str, dash: _Dash, state: str) -> str:
    if dash.kind == "trailing":
        return "narration"
    if dash.kind == "flanked" and _starts_with_speech(text, dash.content):
        return "narration"
    if dash.kind in {"initial", "colon", "flanked"}:
        return "dialogue"
    return state


def _append(pieces: list[Segment], text: str, kind: str, start: int, end: int) -> None:
    begin, stop = _trim(text, start, end)
    if begin < stop:
        pieces.append(Segment(kind, begin, stop, _HIGH))


def _loose_pieces(text: str, dashes: list[_Dash], quotes: list[tuple[int, int]]) -> list[Segment]:
    if quotes and not dashes:
        return _quote_tiling(text, quotes, confidence=_QUOTE)
    cuts = [dash.start for dash in dashes]
    return _cut(text, cuts, confidence=_ASIDE)


def _cut(text: str, cuts: list[int], confidence: float) -> list[Segment]:
    bounds = [0, *cuts, len(text)]
    pieces: list[Segment] = []
    dialogue = False
    for start, end in pairwise(bounds):
        begin, stop = _trim(text, start, end)
        if begin >= stop:
            dialogue = not dialogue
            continue
        kind = "dialogue" if dialogue else "narration"
        pieces.append(Segment(kind, begin, stop, confidence))
        dialogue = not dialogue
    return pieces


def _find_quotes(text: str) -> tuple[list[tuple[int, int]], bool]:
    pairs: list[tuple[int, int]] = []
    index = 0
    while index < len(text):
        closer = _QUOTE_PAIRS.get(text[index])
        if closer is None:
            index += 1
            continue
        end = text.find(closer, index + 1)
        if end < 0:
            return pairs, True
        pairs.append((index + 1, end))
        index = end + 1
    return pairs, False


def _quote_has_speech(text: str, quote: tuple[int, int]) -> bool:
    sentences = RegexSentenceSegmenter().segment(text)
    qstart, qend = quote
    indexes = [i for i, span in enumerate(sentences) if span.end > qstart and span.start < qend]
    if not indexes and sentences:
        indexes = [0]
    for index in indexes:
        window = range(max(0, index - 1), min(len(sentences), index + 2))
        for neighbor in window:
            span = sentences[neighbor]
            if _verb_outside(text, span.start, span.end, qstart, qend):
                return True
    return False


def _verb_outside(text: str, start: int, end: int, qstart: int, qend: int) -> bool:
    for token_start, token in _token_spans(text, start, end):
        if qstart <= token_start < qend:
            continue
        if token.casefold() in _VERBS:
            return True
    return False


def _token_spans(text: str, start: int, end: int) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    cursor = start
    while cursor < end:
        while cursor < end and not text[cursor].isalnum():
            cursor += 1
        begin = cursor
        while cursor < end and (text[cursor].isalnum() or text[cursor] in _WORD_EXTRA):
            cursor += 1
        if begin < cursor:
            found.append((begin, text[begin:cursor]))
    return found


def _quote_tiling(
    text: str, quotes: list[tuple[int, int]], confidence: float = _HIGH
) -> list[Segment]:
    pieces: list[Segment] = []
    cursor = 0
    for qstart, qend in quotes:
        _append_conf(pieces, text, "narration", cursor, qstart - 1, 1.0)
        _append_conf(pieces, text, "dialogue", qstart, qend, confidence)
        cursor = qend + 1
    _append_conf(pieces, text, "narration", cursor, len(text), 1.0)
    return pieces


def _append_conf(
    pieces: list[Segment], text: str, kind: str, start: int, end: int, confidence: float
) -> None:
    begin, stop = _trim(text, start, end)
    if begin >= stop or _punctuation_only(text[begin:stop]):
        return
    pieces.append(Segment(kind, begin, stop, confidence))


def _punctuation_only(value: str) -> bool:
    return value.strip(" \t.?!,;:…\"'”»") == ""


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    start = max(0, start)
    end = min(len(text), end)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    while start < end and text[start] in _DASHES:
        start += 1
        while start < end and text[start].isspace():
            start += 1
    while end > start and text[end - 1] in _DASHES:
        end -= 1
        while end > start and text[end - 1].isspace():
            end -= 1
    return start, end


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index
