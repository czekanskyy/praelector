# SPDX-License-Identifier: Apache-2.0
"""The single ffmpeg invocation that writes an M4B (MX-01, MX-04).

This builds the argument list. It does not run ffmpeg.
"""

from __future__ import annotations

from pathlib import Path


def m4b_args(
    *,
    ffmpeg: Path,
    concat_list: Path,
    metadata: Path,
    output: Path,
    cover: Path | None = None,
) -> list[str]:
    """Concat demuxer, ffmetadata, AAC mono 44.1 kHz, faststart."""
    args = [
        str(ffmpeg),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-f",
        "ffmetadata",
        "-i",
        str(metadata),
        "-map",
        "0:a",
        "-map_metadata",
        "1",
    ]
    if cover is not None:
        args.extend(["-i", str(cover), "-map", "2:v", "-disposition:v", "attached_pic"])
    args.extend(
        [
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return args
