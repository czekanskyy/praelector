# SPDX-License-Identifier: Apache-2.0
"""Which chapters can be muxed, and the concat list for one of them (MX-03, TTS-08).

A full export refuses a book that still has a missing chunk. A partial
export drops those chapters and keeps the original chapter numbers.
Inter-sentence silence is a file between speech chunks. A pause item is
already that gap, so it does not get a second one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from praelector.errors import AppError, ErrorCode
from praelector.jobs.chunker import PlanItem

MuxMode = Literal["full", "partial"]
Present = Callable[[PlanItem], bool]


@dataclass(frozen=True, slots=True)
class ChapterAudio:
    """One chapter in book order. ``number`` is the original chapter number."""

    chapter_id: str
    number: int
    title: str
    items: tuple[PlanItem, ...]


@dataclass(frozen=True, slots=True)
class MuxPlan:
    """Chapters that will be encoded, and those left out."""

    included: tuple[ChapterAudio, ...]
    omitted: tuple[dict[str, Any], ...]


def select_for_mux(
    chapters: Sequence[ChapterAudio],
    *,
    present: Present,
    mode: MuxMode,
) -> MuxPlan:
    """Keep complete chapters. Full mode fails if any speech chunk is missing."""
    included: list[ChapterAudio] = []
    omitted: list[dict[str, Any]] = []
    for chapter in chapters:
        if _complete(chapter, present):
            included.append(chapter)
            continue
        omitted.append(
            {
                "chapter_id": chapter.chapter_id,
                "number": chapter.number,
                "title": chapter.title,
                "reason": "incomplete",
            }
        )
    if mode == "full" and omitted:
        raise AppError(
            ErrorCode.EXPORT_INCOMPLETE,
            detail={"missing_chapters": [row["number"] for row in omitted]},
        )
    if not included:
        raise AppError(ErrorCode.EXPORT_NOTHING_TO_EXPORT)
    return MuxPlan(tuple(included), tuple(omitted))


def concat_list(
    items: Sequence[PlanItem],
    *,
    wav_for: Callable[[PlanItem], Path],
    silence_wav: Path,
    gap_ms: int,
) -> str:
    """ffmpeg concat-demuxer text. ``gap_ms`` of 0 inserts nothing."""
    lines: list[str] = []
    previous_speech = False
    for item in items:
        speech = item.kind != "silence"
        if speech and previous_speech and gap_ms > 0:
            lines.append(_file_line(silence_wav))
        lines.append(_file_line(wav_for(item)))
        previous_speech = speech
    return "\n".join(lines) + ("\n" if lines else "")


def _complete(chapter: ChapterAudio, present: Present) -> bool:
    return all(present(item) for item in chapter.items if item.kind != "silence")


def _file_line(path: Path) -> str:
    text = path.as_posix().replace("'", r"'\''")
    return f"file '{text}'"
