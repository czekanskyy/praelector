# SPDX-License-Identifier: Apache-2.0
"""Turn chapter blocks into spoken runs (PLAN.md §8.2, steps 1-2).

Skip spans drop out, pronunciation spans expand, and a pause becomes a
silence run. Adjacent speech with the same voice slot joins, so the
chunker can pack across paragraphs without crossing a slot.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from praelector.domain.enums import VoiceMode, VoiceSlot
from praelector.jobs.chunker import SpokenRun
from praelector.text.apply import AppliedSpan
from praelector.text.spoken import spoken_form
from praelector.voices.assignment import assign_slot

_STRUCTURAL = frozenset({"narration", "dialogue", "pause"})
_OVERLAY = frozenset({"pronunciation", "skip"})


@dataclass(frozen=True, slots=True)
class SourceBlock:
    """One block of the current revision, spans already applied."""

    chapter_id: str
    text: str
    spans: tuple[AppliedSpan, ...] = ()


def spoken_runs(
    blocks: Sequence[SourceBlock],
    *,
    mode: VoiceMode,
    filled: set[str],
    profiles: dict[str, tuple[str, str]],
) -> tuple[list[SpokenRun], list[str]]:
    """Runs in chapter order, plus slot-fallback warnings."""
    runs: list[SpokenRun] = []
    warnings: list[str] = []
    for block in blocks:
        for span in _cover(block.text, block.spans):
            if span.kind == "pause":
                _push_silence(runs, block.chapter_id, profiles)
                continue
            spoken = _speak(block.text, block.spans, span.start, span.end)
            if not spoken:
                continue
            _push_speech(
                runs,
                warnings,
                block.chapter_id,
                span,
                spoken,
                mode=mode,
                filled=filled,
                profiles=profiles,
            )
    return runs, warnings


def _cover(text: str, spans: Sequence[AppliedSpan]) -> list[AppliedSpan]:
    structural = sorted(
        (span for span in spans if span.kind in _STRUCTURAL),
        key=lambda span: (span.start, span.end),
    )
    if not structural:
        if not text:
            return []
        return [AppliedSpan("narration", 0, len(text))]
    covered: list[AppliedSpan] = []
    cursor = 0
    for span in structural:
        if span.start > cursor:
            covered.append(AppliedSpan("narration", cursor, span.start))
        if span.end <= cursor:
            continue
        start = max(span.start, cursor)
        covered.append(replace(span, start=start) if start != span.start else span)
        cursor = span.end
    if cursor < len(text):
        covered.append(AppliedSpan("narration", cursor, len(text)))
    return covered


def _speak(text: str, spans: Sequence[AppliedSpan], start: int, end: int) -> str:
    local: list[AppliedSpan] = []
    for span in spans:
        if span.kind not in _OVERLAY or span.start < start or span.end > end:
            continue
        local.append(
            AppliedSpan(span.kind, span.start - start, span.end - start, spoken=span.spoken)
        )
    return spoken_form(text[start:end], local).strip()


def _push_silence(
    runs: list[SpokenRun],
    chapter_id: str,
    profiles: dict[str, tuple[str, str]],
) -> None:
    profile_id, content_hash = profiles.get(VoiceSlot.NARRATOR, ("", ""))
    runs.append(
        SpokenRun(
            chapter_id=chapter_id,
            voice_slot=VoiceSlot.NARRATOR,
            kind="silence",
            text="",
            voice_profile_id=profile_id,
            voice_profile_content_hash=content_hash,
        )
    )


def _push_speech(
    runs: list[SpokenRun],
    warnings: list[str],
    chapter_id: str,
    span: AppliedSpan,
    spoken: str,
    *,
    mode: VoiceMode,
    filled: set[str],
    profiles: dict[str, tuple[str, str]],
) -> None:
    assignment = assign_slot(
        mode,
        kind=span.kind,
        gender=span.gender or None,
        filled=filled,
    )
    if assignment.warning and assignment.warning not in warnings:
        warnings.append(assignment.warning)
    profile_id, content_hash = profiles.get(assignment.slot, ("", ""))
    run = SpokenRun(
        chapter_id=chapter_id,
        voice_slot=assignment.slot,
        kind="tts",
        text=spoken,
        voice_profile_id=profile_id,
        voice_profile_content_hash=content_hash,
    )
    previous = runs[-1] if runs else None
    if (
        previous is not None
        and previous.kind == "tts"
        and previous.chapter_id == run.chapter_id
        and previous.voice_slot == run.voice_slot
    ):
        runs[-1] = replace(previous, text=f"{previous.text} {run.text}")
        return
    runs.append(run)
