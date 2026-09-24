# SPDX-License-Identifier: Apache-2.0
"""Pack spoken runs into plan items (TTS-07, PLAN.md §8.2).

Sentences pack up to ``max_input_chars`` and never cross a voice slot.
A short dialogue span stays one chunk. A sentence longer than the limit
breaks on clause punctuation, then on whitespace, never inside a word.
"""

from __future__ import annotations

from dataclasses import dataclass

from praelector.domain.hashing import render_key
from praelector.text.segment import RegexSentenceSegmenter, SentenceSegmenter

_CLAUSES = (";", ",", " \u2014 ", " \u2013 ", " - ")


@dataclass(frozen=True, slots=True)
class SpokenRun:
    """One narration or dialogue stretch already assigned to a slot."""

    chapter_id: str
    voice_slot: str
    kind: str
    text: str
    voice_profile_id: str
    voice_profile_content_hash: str


@dataclass(frozen=True, slots=True)
class PlanItem:
    """One TTS call or one silence. ``ordinal`` is the plan order."""

    ordinal: int
    chapter_id: str
    voice_slot: str
    spoken_text: str
    kind: str
    render_key: str


def plan_runs(
    runs: list[SpokenRun],
    *,
    max_input_chars: int,
    backend_id: str,
    adapter_version: str,
    model_revision: str,
    params: dict[str, object] | None = None,
    segmenter: SentenceSegmenter | None = None,
) -> list[PlanItem]:
    """Turn runs into ordered plan items. ``runs`` is not modified."""
    if max_input_chars < 1:
        raise ValueError("max input chars must be positive")
    cutter = segmenter or RegexSentenceSegmenter()
    audio_params = params or {}
    items: list[PlanItem] = []
    for run in runs:
        if run.kind == "silence":
            items.append(
                _item(
                    len(items),
                    run,
                    "",
                    "silence",
                    backend_id,
                    adapter_version,
                    model_revision,
                    audio_params,
                )
            )
            continue
        pieces = _pieces(run, max_input_chars, cutter)
        for piece in pieces:
            items.append(
                _item(
                    len(items),
                    run,
                    piece,
                    "tts",
                    backend_id,
                    adapter_version,
                    model_revision,
                    audio_params,
                )
            )
    return items


def _item(
    ordinal: int,
    run: SpokenRun,
    spoken: str,
    kind: str,
    backend_id: str,
    adapter_version: str,
    model_revision: str,
    params: dict[str, object],
) -> PlanItem:
    key = render_key(
        spoken_text=spoken,
        voice_slot=run.voice_slot,
        voice_profile_id=run.voice_profile_id,
        voice_profile_content_hash=run.voice_profile_content_hash,
        backend_id=backend_id,
        adapter_version=adapter_version,
        model_revision=model_revision,
        params=params,
    )
    return PlanItem(ordinal, run.chapter_id, run.voice_slot, spoken, kind, key)


def _pieces(run: SpokenRun, limit: int, segmenter: SentenceSegmenter) -> list[str]:
    text = run.text.strip()
    if text == "":
        return []
    if run.kind == "dialogue" and len(text) <= limit:
        return [text]
    sentences = [span.text.strip() for span in segmenter.segment(text) if span.text.strip()]
    if not sentences:
        sentences = [text]
    packed: list[str] = []
    current = ""
    for sentence in sentences:
        for piece in _split_oversized(sentence, limit):
            if current == "":
                current = piece
            elif len(current) + 1 + len(piece) <= limit:
                current = f"{current} {piece}"
            else:
                packed.append(current)
                current = piece
    if current:
        packed.append(current)
    return packed


def _split_oversized(text: str, limit: int) -> list[str]:
    text = text.strip()
    if text == "" or len(text) <= limit:
        return [text] if text else []
    for separator in _CLAUSES:
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) > 1:
                found: list[str] = []
                for part in parts:
                    found.extend(_split_oversized(part, limit))
                return found
    space = text.rfind(" ", 0, limit + 1)
    if space <= 0:
        space = text.find(" ")
        if space <= 0:
            return [text]
    head, tail = text[:space].strip(), text[space + 1 :].strip()
    return [head, *_split_oversized(tail, limit)] if head else _split_oversized(tail, limit)
