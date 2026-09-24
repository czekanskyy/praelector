# SPDX-License-Identifier: Apache-2.0
"""ffmpeg and ffprobe as a swappable tool (D-06).

``argv[0]`` is the tool name (``ffmpeg`` or ``ffprobe``). A missing path
raises ``audio.ffmpeg_missing`` and does not spawn a process. The ingest
chain talks to this interface, so tests never need a binary.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from praelector.errors import AppError, ErrorCode


@dataclass(frozen=True, slots=True)
class ToolResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class MediaTool(Protocol):
    def run(self, argv: Sequence[str]) -> ToolResult:
        """Run one ffmpeg or ffprobe invocation. ``argv[0]`` is the tool name."""


class SubprocessMediaTool:
    """Shells out only when both binaries were configured."""

    def __init__(self, ffmpeg: str | None, ffprobe: str | None) -> None:
        self._paths = {"ffmpeg": ffmpeg, "ffprobe": ffprobe}

    def run(self, argv: Sequence[str]) -> ToolResult:
        tool = argv[0]
        path = self._paths.get(tool)
        if not path:
            raise AppError(
                ErrorCode.AUDIO_FFMPEG_MISSING,
                detail={"tool": tool, "reason": "not_found"},
                message="ffmpeg was not found",
            )
        completed = subprocess.run(
            [path, *argv[1:]],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AppError(
                ErrorCode.AUDIO_FFMPEG_MISSING,
                detail={"tool": tool, "reason": "exit", "returncode": completed.returncode},
                message="ffmpeg failed",
            )
        return ToolResult(
            returncode=0,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
