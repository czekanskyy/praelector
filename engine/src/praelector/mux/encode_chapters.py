# SPDX-License-Identifier: Apache-2.0
"""Write one WAV per included chapter (MX-01).

The concat list is text. ``run_ffmpeg`` is what actually invokes the tool,
so a test can pass a fake and still see the arguments.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from praelector.audio.ffmpeg import MediaTool
from praelector.jobs.chunker import PlanItem
from praelector.mux.chapters import MuxPlan, concat_list
from praelector.mux.m4b import chapter_wav_args
from praelector.mux.run import run_ffmpeg


def encode_chapters(
    plan: MuxPlan,
    *,
    tool: MediaTool,
    ffmpeg: Path,
    work_dir: Path,
    wav_for: Callable[[PlanItem], Path],
    silence_wav: Path,
    gap_ms: int,
) -> list[Path]:
    """Copy each included chapter to ``NNN.wav``. Chapter numbers are kept."""
    work_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for chapter in plan.included:
        listing = work_dir / f"{chapter.number:03d}.txt"
        listing.write_text(
            concat_list(
                chapter.items,
                wav_for=wav_for,
                silence_wav=silence_wav,
                gap_ms=gap_ms,
            ),
            encoding="utf-8",
            newline="\n",
        )
        output = work_dir / f"{chapter.number:03d}.wav"
        run_ffmpeg(
            tool,
            chapter_wav_args(ffmpeg=ffmpeg, concat_list=listing, output=output),
        )
        written.append(output)
    return written
