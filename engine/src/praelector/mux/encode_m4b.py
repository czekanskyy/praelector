# SPDX-License-Identifier: Apache-2.0
"""Write the M4B from a concat list and tags (MX-01).

The files land next to the output's directory under ``work_dir``. The
tool is injected, so this does not search for ffmpeg itself.
"""

from __future__ import annotations

from pathlib import Path

from praelector.audio.ffmpeg import MediaTool
from praelector.mux.m4b import m4b_args
from praelector.mux.metadata import AudiobookTags, ChapterMark, ffmetadata
from praelector.mux.run import run_ffmpeg


def encode_m4b(
    *,
    tool: MediaTool,
    ffmpeg: Path,
    work_dir: Path,
    concat_text: str,
    tags: AudiobookTags,
    chapters: list[ChapterMark],
    output: Path,
    cover: Path | None = None,
) -> None:
    """One ffmpeg invocation. ``concat_text`` is a concat-demuxer document."""
    work_dir.mkdir(parents=True, exist_ok=True)
    listing = work_dir / "concat.txt"
    metadata = work_dir / "ffmetadata.txt"
    listing.write_text(concat_text, encoding="utf-8", newline="\n")
    metadata.write_text(ffmetadata(tags, chapters), encoding="utf-8", newline="\n")
    run_ffmpeg(
        tool,
        m4b_args(
            ffmpeg=ffmpeg,
            concat_list=listing,
            metadata=metadata,
            output=output,
            cover=cover,
        ),
    )
