# SPDX-License-Identifier: Apache-2.0
"""Run an ffmpeg argument list built by this package (MX-01).

The lists in ``m4b.py`` start with a filesystem path. ``MediaTool`` wants
the tool name ``ffmpeg`` and resolves the binary itself, so that path is
dropped. A non-zero exit is an encode failure. A missing binary stays
``audio.ffmpeg_missing``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from praelector.audio.ffmpeg import MediaTool, ToolResult
from praelector.errors import AppError, ErrorCode


def run_ffmpeg(tool: MediaTool, args: Sequence[str]) -> ToolResult:
    """Invoke ffmpeg. ``args`` is what ``m4b_args`` or ``chapter_wav_args`` returned."""
    if len(args) < 2 or Path(args[0]).name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        raise AppError(ErrorCode.EXPORT_FAILED, detail={"reason": "not_ffmpeg"})
    try:
        result = tool.run(("ffmpeg", *args[1:]))
    except AppError as exc:
        if exc.code is ErrorCode.AUDIO_FFMPEG_MISSING and exc.detail.get("reason") == "exit":
            raise AppError(
                ErrorCode.AUDIO_ENCODE_FAILED,
                detail=exc.detail,
                message="ffmpeg failed",
            ) from exc
        raise
    if result.returncode != 0:
        raise AppError(
            ErrorCode.AUDIO_ENCODE_FAILED,
            detail={"reason": "exit", "returncode": result.returncode},
            message="ffmpeg failed",
        )
    return result
