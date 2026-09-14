# SPDX-License-Identifier: Apache-2.0
"""Dialogue segmentation state machine for Polish text (DG-01, DG-02).

Detects paragraph-initial dashes, mid-paragraph dashes with speech tags,
colon-dash transitions, and quotation marks according to section 5.2 of the
master specification.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field

from praelector.domain.enums import (
    DetectorKind,
    Gender,
    GenderDetector,
    SpanKind,
    SuggestionCategory,
    SuggestionStatus,
)
from praelector.domain.models import SuggestionCreate

# Dash characters recognised in Polish typography:
# — (U+2014 em dash), – (U+2013 en dash), ― (U+2015 horizontal bar), - (U+002D hyphen-minus)
DASH_CHARS: Final[str] = "—–―-"
DASH_PATTERN: Final[re.Pattern[str]] = re.compile(rf"[{re.escape(DASH_CHARS)}]")

# Quotation mark pairs (opening, closing)
QUOTE_PAIRS: Final[list[tuple[str, str]]] = [
    ("„", "”"),  # Polish standard: low double quote -> right double quotation mark
    ("«", "»"),  # French guillemets
    ("“", "”"),  # Left double quotation mark -> right double quotation mark
    ('"', '"'),  # Straight double quotes
]

OPENING_QUOTES: Final[frozenset[str]] = frozenset(q[0] for q in QUOTE_PAIRS)
CLOSING_QUOTES: Final[frozenset[str]] = frozenset(q[1] for q in QUOTE_PAIRS)


def _load_speech_verbs() -> frozenset[str]:
    """Load Polish inflected speech verbs from text/data/speech_verbs_pl.txt."""
    path = Path(__file__).parent / "data" / "speech_verbs_pl.txt"
    if not path.is_file():
        # Fallback in case of missing resource
        return frozenset(
            {
                "powiedział",
                "powiedziała",
                "mruknął",
                "mruknęła",
                "zapytał",
                "zapytała",
                "odparł",
                "odparła",
                "rzekł",
                "rzekła",
                "krzyknął",
                "krzyknęła",
                "dodał",
                "dodała",
                "szepnął",
                "szepnęła",
            }
        )
    verbs: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                verbs.add(line.lower())
    return frozenset(verbs)


SPEECH_VERBS: Final[frozenset[str]] = _load_speech_verbs()

# Pronouns that frequently precede speech verbs in Polish speech tags
SPEECH_TAG_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "on",
        "ona",
        "ono",
        "oni",
        "one",
        "ja",
        "ty",
        "my",
        "wy",
        "ten",
        "ta",
        "to",
    }
)

# Words regex for tokenizing Polish text
WORD_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-zżźćńółęąśŻŹĆĄŚĘŁÓŃ]+")


class DialogueSegment(BaseModel):
    """A semantic span resulting from dialogue segmentation."""

    kind: SpanKind
    start: int
    end: int
    text: str
    confidence: float = 0.90
    gender: Gender | None = None
    gender_confidence: float | None = None
    gender_detector: GenderDetector | None = None
    speaker_id: str | None = None


class DialogueSplitResult(BaseModel):
    """Result of running dialogue segmentation on a block of text."""

    segments: list[DialogueSegment] = Field(default_factory=list)
    has_dialogue: bool = False
    confidence: float = 0.90
    rationale: str = "Deterministic dialogue split"
    unconfirmed_aside: bool = False
    unbalanced_quotes: bool = False
    quote_without_verb: bool = False


def _has_speech_verb_ahead(text_after: str) -> bool:
    """Check if the text starts, within its first three tokens, with a speech verb.

    Allows the verb of saying to be optionally preceded by a pronoun or capitalized name.
    """
    tokens = WORD_RE.findall(text_after)
    if not tokens:
        return False

    first_three = tokens[:3]
    for idx, token in enumerate(first_three):
        t_lower = token.lower()
        if t_lower in SPEECH_VERBS:
            # If it's the very first token, e.g. "powiedziała cicho"
            if idx == 0:
                return True
            # If preceded by pronoun or capitalized name, e.g. "Anna powiedziała", "on powiedział", "cicho rzekła"
            preceding = first_three[:idx]
            if all(
                p.lower() in SPEECH_TAG_PRONOUNS or p[0].isupper() or len(p) >= 3 for p in preceding
            ):
                return True
    return False


def _contains_speech_verb(text: str) -> bool:
    """Check if any token in text is in SPEECH_VERBS."""
    return any(token.lower() in SPEECH_VERBS for token in WORD_RE.findall(text))


def _find_quote_spans(text: str) -> list[tuple[int, int, str, str]]:
    """Locate balanced quote pairs in text. Returns (start, end, opener, closer)."""
    spans: list[tuple[int, int, str, str]] = []
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        matched_closer: str | None = None
        for op, cl in QUOTE_PAIRS:
            if char == op:
                matched_closer = cl
                break
        if matched_closer:
            # For straight quotes ("...") opener == closer, so search starting at i+1
            start_search = i + 1
            idx = text.find(matched_closer, start_search)
            if idx != -1:
                spans.append((i, idx + 1, char, matched_closer))
                i = idx + 1
                continue
        i += 1
    return spans


def split_dialogue(text: str) -> DialogueSplitResult:
    """Segment a block of text into narration and dialogue spans (DG-01, DG-02).

    Follows the 5-step state machine from §5.2:
    1. Determine split candidates (paragraph dash, dash flanked by whitespace, colon-dash, quote pairs).
    2. Walk candidates left to right, alternating state on confirmed boundaries.
    3. Confirm candidate boundary only if the following segment starts with a speech verb
       within 3 tokens, or closes a narration insertion.
    4. Quote regions without a speech verb stay narration and yield 0.40 suggestion.
    5. Unbalanced quotes or odd dash count yield 0.35 suggestion.
    """
    cleaned = text.strip()
    if not cleaned:
        return DialogueSplitResult(
            segments=[
                DialogueSegment(
                    kind=SpanKind.NARRATION, start=0, end=len(text), text=text, confidence=1.0
                )
            ],
            has_dialogue=False,
            confidence=1.0,
        )

    # Check for paragraph-initial dash (Rule 1a)
    init_dash_match = re.match(rf"^(\s*[{re.escape(DASH_CHARS)}]\s*)", text)
    has_initial_dash = init_dash_match is not None

    # Check for quotes in the text
    quote_spans = _find_quote_spans(text)
    has_quotes = any(c in OPENING_QUOTES or c in CLOSING_QUOTES for c in text)

    # -----------------------------------------------------------------------
    # Case A: Paragraph starts with dash (DG-01)
    # -----------------------------------------------------------------------
    if has_initial_dash:
        assert init_dash_match is not None
        segments: list[DialogueSegment] = []
        state = SpanKind.DIALOGUE
        pos = init_dash_match.end()
        cur_start = pos
        unconfirmed_aside = False

        # Find candidate dashes inside paragraph
        dash_candidates = list(re.finditer(rf"(\s+[{re.escape(DASH_CHARS)}]\s*)", text[pos:]))

        in_narration_insertion = False

        for m in dash_candidates:
            cand_start = pos + m.start()
            cand_end = pos + m.end()

            if cand_start < cur_start:
                continue

            text_before = text[cur_start:cand_start].strip()
            text_after = text[cand_end:]

            if not text_after.strip():
                # Trailing dash at end of paragraph / interrupted speech
                break

            if state == SpanKind.DIALOGUE:
                # Check if this dash opens a narration insertion (Rule 3)
                if _has_speech_verb_ahead(text_after):
                    # Confirmed boundary -> transition to NARRATION
                    if text_before:
                        # Find actual slice without whitespace
                        s_offset = text.find(text_before, cur_start, cand_start)
                        segments.append(
                            DialogueSegment(
                                kind=SpanKind.DIALOGUE,
                                start=s_offset,
                                end=s_offset + len(text_before),
                                text=text_before,
                                confidence=0.90,
                            )
                        )
                    state = SpanKind.NARRATION
                    in_narration_insertion = True
                    cur_start = cand_end
                else:
                    # Not confirmed -> pause / aside within dialogue (e.g. — choć trudna —)
                    unconfirmed_aside = True
                    # Do not transition state; dialogue continues
            elif state == SpanKind.NARRATION and in_narration_insertion:
                # Dash that closes such a narration insertion -> next = DIALOGUE (Rule 3 bullet 2)
                if text_before:
                    s_offset = text.find(text_before, cur_start, cand_start)
                    segments.append(
                        DialogueSegment(
                            kind=SpanKind.NARRATION,
                            start=s_offset,
                            end=s_offset + len(text_before),
                            text=text_before,
                            confidence=0.90,
                        )
                    )
                state = SpanKind.DIALOGUE
                in_narration_insertion = False
                cur_start = cand_end

        # Trailing segment
        trailing_text = text[cur_start:].strip()
        # Strip any trailing dash if it ends the paragraph (e.g. — Myślałem, że ty —)
        trailing_text = re.sub(rf"\s*[{re.escape(DASH_CHARS)}]\s*$", "", trailing_text).strip()
        if trailing_text:
            s_offset = text.find(trailing_text, cur_start)
            segments.append(
                DialogueSegment(
                    kind=state,
                    start=s_offset,
                    end=s_offset + len(trailing_text),
                    text=trailing_text,
                    confidence=0.90,
                )
            )

        if not segments:
            segments = [
                DialogueSegment(
                    kind=SpanKind.DIALOGUE,
                    start=pos,
                    end=len(text),
                    text=text[pos:],
                    confidence=0.90,
                )
            ]

        confidence = 0.45 if unconfirmed_aside and len(segments) == 1 else 0.90
        return DialogueSplitResult(
            segments=segments,
            has_dialogue=True,
            confidence=confidence,
            rationale="Paragraph-initial dialogue with speech tags"
            if len(segments) > 1
            else "Paragraph-initial dialogue",
            unconfirmed_aside=unconfirmed_aside,
        )

    # -----------------------------------------------------------------------
    # Case B: Colon + dash mid-paragraph (Rule 1c: " : " + dash -> DIALOGUE)
    # -----------------------------------------------------------------------
    colon_dash_match = re.search(rf":\s*([{re.escape(DASH_CHARS)}]\s*)", text)
    if colon_dash_match is not None:
        c_start = colon_dash_match.start() + 1  # includes ':' in narration
        c_end = colon_dash_match.end()

        narration_text = text[:c_start].strip()
        dialogue_text = text[c_end:].strip()

        segments = [
            DialogueSegment(
                kind=SpanKind.NARRATION,
                start=0,
                end=c_start,
                text=narration_text,
                confidence=0.90,
            ),
            DialogueSegment(
                kind=SpanKind.DIALOGUE,
                start=text.find(dialogue_text, c_end),
                end=text.find(dialogue_text, c_end) + len(dialogue_text),
                text=dialogue_text,
                confidence=0.90,
            ),
        ]
        return DialogueSplitResult(
            segments=segments,
            has_dialogue=True,
            confidence=0.90,
            rationale="Mid-paragraph colon and dash dialogue split",
        )

    # -----------------------------------------------------------------------
    # Case C: Mid-paragraph dash after narration (DG-02)
    # Example: Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz.
    # -----------------------------------------------------------------------
    # Look for dash preceded by terminal punctuation (. ? ! …)
    mid_dash_matches = list(re.finditer(rf"([.?!…])\s*([{re.escape(DASH_CHARS)}]\s+)", text))
    if mid_dash_matches:
        m0 = mid_dash_matches[0]
        narr_end = m0.start(1) + 1  # include sentence-ending punctuation in narration
        pos = m0.end()

        # We now enter DIALOGUE state
        segments = []
        narration_intro = text[:narr_end].strip()
        segments.append(
            DialogueSegment(
                kind=SpanKind.NARRATION,
                start=0,
                end=narr_end,
                text=narration_intro,
                confidence=0.90,
            )
        )

        cur_start = pos
        dash_candidates = list(re.finditer(rf"(\s+[{re.escape(DASH_CHARS)}]\s*)", text[pos:]))
        state = SpanKind.DIALOGUE
        in_narration_insertion = False

        for m in dash_candidates:
            cand_start = pos + m.start()
            cand_end = pos + m.end()
            text_before = text[cur_start:cand_start].strip()
            text_after = text[cand_end:]

            if state == SpanKind.DIALOGUE and _has_speech_verb_ahead(text_after):
                if text_before:
                    s_offset = text.find(text_before, cur_start, cand_start)
                    segments.append(
                        DialogueSegment(
                            kind=SpanKind.DIALOGUE,
                            start=s_offset,
                            end=s_offset + len(text_before),
                            text=text_before,
                            confidence=0.90,
                        )
                    )
                state = SpanKind.NARRATION
                in_narration_insertion = True
                cur_start = cand_end
            elif state == SpanKind.NARRATION and in_narration_insertion:
                if text_before:
                    s_offset = text.find(text_before, cur_start, cand_start)
                    segments.append(
                        DialogueSegment(
                            kind=SpanKind.NARRATION,
                            start=s_offset,
                            end=s_offset + len(text_before),
                            text=text_before,
                            confidence=0.90,
                        )
                    )
                state = SpanKind.DIALOGUE
                in_narration_insertion = False
                cur_start = cand_end

        trailing = text[cur_start:].strip()
        trailing = re.sub(rf"\s*[{re.escape(DASH_CHARS)}]\s*$", "", trailing).strip()
        if trailing:
            s_offset = text.find(trailing, cur_start)
            segments.append(
                DialogueSegment(
                    kind=state,
                    start=s_offset,
                    end=s_offset + len(trailing),
                    text=trailing,
                    confidence=0.90,
                )
            )

        return DialogueSplitResult(
            segments=segments,
            has_dialogue=True,
            confidence=0.90,
            rationale="Mid-paragraph dialogue after narration",
        )

    # -----------------------------------------------------------------------
    # Case D: Quotation marks (Rule 1d, 4, 5)
    # -----------------------------------------------------------------------
    if has_quotes:
        # Check if quotes are balanced
        if not quote_spans:
            # Unbalanced quote (Rule 5: confidence 0.35, never applied)
            return DialogueSplitResult(
                segments=[
                    DialogueSegment(
                        kind=SpanKind.NARRATION, start=0, end=len(text), text=text, confidence=0.35
                    )
                ],
                has_dialogue=False,
                confidence=0.35,
                rationale="Unbalanced quotation marks",
                unbalanced_quotes=True,
            )

        # Quotes are balanced. Check for speech verb in sentence or adjacent context (Rule 4)
        has_speech_verb = _contains_speech_verb(text)
        if not has_speech_verb:
            # Rule 4: Quote without speech verb stays narration and yields a 0.40 suggestion
            return DialogueSplitResult(
                segments=[
                    DialogueSegment(
                        kind=SpanKind.NARRATION, start=0, end=len(text), text=text, confidence=1.0
                    )
                ],
                has_dialogue=False,
                confidence=0.40,
                rationale="Quoted text without speech verb stays narration",
                quote_without_verb=True,
            )

        # Confirmed dialogue in quotes! (e.g. Anna powiedziała: „Musimy kończyć”.)
        segments = []
        last_idx = 0
        for q_start, q_end, _op, _cl in quote_spans:
            if q_start > last_idx:
                narr_text = text[last_idx:q_start].strip()
                if narr_text:
                    s_off = text.find(narr_text, last_idx, q_start)
                    segments.append(
                        DialogueSegment(
                            kind=SpanKind.NARRATION,
                            start=s_off,
                            end=s_off + len(narr_text),
                            text=narr_text,
                            confidence=0.90,
                        )
                    )
            # Inside quotes
            inner_text = text[q_start + 1 : q_end - 1].strip()
            if inner_text:
                s_off = text.find(inner_text, q_start, q_end)
                segments.append(
                    DialogueSegment(
                        kind=SpanKind.DIALOGUE,
                        start=s_off,
                        end=s_off + len(inner_text),
                        text=inner_text,
                        confidence=0.90,
                    )
                )
            last_idx = q_end

        if last_idx < len(text):
            trailing_narr = text[last_idx:].strip()
            if trailing_narr:
                s_off = text.find(trailing_narr, last_idx)
                segments.append(
                    DialogueSegment(
                        kind=SpanKind.NARRATION,
                        start=s_off,
                        end=s_off + len(trailing_narr),
                        text=trailing_narr,
                        confidence=0.90,
                    )
                )

        return DialogueSplitResult(
            segments=segments,
            has_dialogue=True,
            confidence=0.90,
            rationale="Quotation dialogue with confirmed speech verb",
        )

    # -----------------------------------------------------------------------
    # Case E: Unconfirmed aside / dashes in pure narration (Rule 3 bullet 3)
    # Example: Wszyscy — nawet Anna — milczeli.
    # -----------------------------------------------------------------------
    dash_in_narr = re.search(rf"\s+[{re.escape(DASH_CHARS)}]\s+", text)
    if dash_in_narr:
        # Dash in narration without sentence terminal or colon before it, and no speech verb
        return DialogueSplitResult(
            segments=[
                DialogueSegment(
                    kind=SpanKind.NARRATION, start=0, end=len(text), text=text, confidence=1.0
                )
            ],
            has_dialogue=False,
            confidence=0.45,
            rationale="Unconfirmed dash aside in narration",
            unconfirmed_aside=True,
        )

    # -----------------------------------------------------------------------
    # Case F: Default pure narration
    # -----------------------------------------------------------------------
    return DialogueSplitResult(
        segments=[
            DialogueSegment(
                kind=SpanKind.NARRATION, start=0, end=len(text), text=text, confidence=1.0
            )
        ],
        has_dialogue=False,
        confidence=1.0,
        rationale="Pure narration",
    )


def detect_dialogue_suggestions(
    text: str,
    project_id: str,
    chapter_id: str,
    block_id: str,
    base_revision: int = 0,
) -> tuple[DialogueSplitResult, list[SuggestionCreate]]:
    """Execute dialogue segmentation and return the result along with any review suggestions."""
    result = split_dialogue(text)
    suggestions: list[SuggestionCreate] = []

    if result.has_dialogue:
        payload = {
            "segments": [
                {
                    "kind": s.kind.value,
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "gender": s.gender.value if s.gender else None,
                    "speaker_id": s.speaker_id,
                }
                for s in result.segments
            ]
        }
        suggestions.append(
            SuggestionCreate(
                project_id=project_id,
                chapter_id=chapter_id,
                block_id=block_id,
                start=0,
                end=len(text),
                category=SuggestionCategory.DIALOGUE_SPLIT,
                original=text,
                proposed=None,
                payload_json=json.dumps(payload, ensure_ascii=False),
                rationale=result.rationale,
                confidence=result.confidence,
                detector=DetectorKind.HEURISTIC,
                status=SuggestionStatus.PENDING,
                base_revision=base_revision,
            )
        )
    elif result.quote_without_verb:
        # Rule 4: Quote without speech verb yields 0.40 suggestion (stays narration)
        suggestions.append(
            SuggestionCreate(
                project_id=project_id,
                chapter_id=chapter_id,
                block_id=block_id,
                start=0,
                end=len(text),
                category=SuggestionCategory.DIALOGUE_SPLIT,
                original=text,
                proposed=None,
                rationale=result.rationale,
                confidence=0.40,
                detector=DetectorKind.HEURISTIC,
                status=SuggestionStatus.PENDING,
                base_revision=base_revision,
            )
        )
    elif result.unconfirmed_aside:
        # Rule 3 bullet 3: Unconfirmed aside yields 0.45 suggestion
        suggestions.append(
            SuggestionCreate(
                project_id=project_id,
                chapter_id=chapter_id,
                block_id=block_id,
                start=0,
                end=len(text),
                category=SuggestionCategory.DIALOGUE_SPLIT,
                original=text,
                proposed=None,
                rationale=result.rationale,
                confidence=0.45,
                detector=DetectorKind.HEURISTIC,
                status=SuggestionStatus.PENDING,
                base_revision=base_revision,
            )
        )
    elif result.unbalanced_quotes:
        # Rule 5: Unbalanced quotes yields 0.35 suggestion
        suggestions.append(
            SuggestionCreate(
                project_id=project_id,
                chapter_id=chapter_id,
                block_id=block_id,
                start=0,
                end=len(text),
                category=SuggestionCategory.DIALOGUE_SPLIT,
                original=text,
                proposed=None,
                rationale=result.rationale,
                confidence=0.35,
                detector=DetectorKind.HEURISTIC,
                status=SuggestionStatus.PENDING,
                base_revision=base_revision,
            )
        )

    return result, suggestions
