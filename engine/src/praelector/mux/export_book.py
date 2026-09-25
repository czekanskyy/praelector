# SPDX-License-Identifier: Apache-2.0
"""Partial or full export: chapter WAVs, then one M4B (MX-01, MX-03).

``duration_of`` is injected so a test can supply chapter lengths without
ffprobe. The ffmpeg tool is injected the same way.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from praelector.audio.ffmpeg import MediaTool
from praelector.jobs.chunker import PlanItem
from praelector.mux.chapters import (
    ChapterAudio,
    MuxMode,
    MuxPlan,
    chapter_marks,
    select_for_mux,
    write_partial_report,
)
from praelector.mux.encode_chapters import encode_chapters
from praelector.mux.encode_m4b import encode_m4b
from praelector.mux.metadata import AudiobookTags

Present = Callable[[PlanItem], bool]
DurationOf = Callable[[Path], float]


def export_book(
    chapters: Sequence[ChapterAudio],
    *,
    mode: MuxMode,
    present: Present,
    tool: MediaTool,
    ffmpeg: Path,
    work_dir: Path,
    output: Path,
    wav_for: Callable[[PlanItem], Path],
    silence_wav: Path,
    gap_ms: int,
    tags: AudiobookTags,
    duration_of: DurationOf,
    cover: Path | None = None,
) -> MuxPlan:
    """Encode the chapters ``mode`` allows and write ``partial_report.json``."""
    plan = select_for_mux(chapters, present=present, mode=mode)
    chapter_wavs = encode_chapters(
        plan,
        tool=tool,
        ffmpeg=ffmpeg,
        work_dir=work_dir,
        wav_for=wav_for,
        silence_wav=silence_wav,
        gap_ms=gap_ms,
    )
    marks = chapter_marks(plan.included, [duration_of(path) for path in chapter_wavs])
    lines = [_concat_line(path) for path in chapter_wavs]
    encode_m4b(
        tool=tool,
        ffmpeg=ffmpeg,
        work_dir=work_dir,
        concat_text="".join(lines),
        tags=tags,
        chapters=marks,
        output=output,
        cover=cover,
    )
    write_partial_report(work_dir / "partial_report.json", plan)
    return plan


def _concat_line(path: Path) -> str:
    text = path.as_posix().replace("'", r"'\''")
    return f"file '{text}'\n"
