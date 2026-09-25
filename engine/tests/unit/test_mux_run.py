# SPDX-License-Identifier: Apache-2.0
"""The M4B argument list is what ffmpeg actually receives."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from praelector.audio.ffmpeg import ToolResult
from praelector.errors import AppError, ErrorCode
from praelector.mux.m4b import m4b_args
from praelector.mux.run import run_ffmpeg


class _Tool:
    def __init__(self, result: ToolResult | None = None, error: AppError | None = None) -> None:
        self.argv: list[Sequence[str]] = []
        self._result = result or ToolResult(0, b"", b"")
        self._error = error

    def run(self, argv: Sequence[str]) -> ToolResult:
        self.argv.append(argv)
        if self._error is not None:
            raise self._error
        return self._result


def test_run_ffmpeg_drops_the_path_and_keeps_the_encode_flags(tmp_path: Path) -> None:
    args = m4b_args(
        ffmpeg=tmp_path / "ffmpeg.exe",
        concat_list=tmp_path / "list.txt",
        metadata=tmp_path / "meta.txt",
        output=tmp_path / "book.m4b",
    )
    tool = _Tool()

    result = run_ffmpeg(tool, args)

    assert result.returncode == 0
    assert tool.argv == [("ffmpeg", *args[1:])]
    assert tool.argv[0][1:5] == ("-y", "-f", "concat", "-safe")


def test_a_failed_encode_is_not_reported_as_a_missing_binary() -> None:
    tool = _Tool(ToolResult(1, b"", b"boom"))
    with pytest.raises(AppError) as excinfo:
        run_ffmpeg(tool, ["ffmpeg", "-version"])
    assert excinfo.value.code is ErrorCode.AUDIO_ENCODE_FAILED
    assert excinfo.value.detail["returncode"] == 1


def test_a_missing_binary_is_left_unchanged() -> None:
    missing = AppError(ErrorCode.AUDIO_FFMPEG_MISSING, detail={"reason": "not_found"})
    with pytest.raises(AppError) as excinfo:
        run_ffmpeg(_Tool(error=missing), ["C:/bin/ffmpeg.exe", "-y"])
    assert excinfo.value.code is ErrorCode.AUDIO_FFMPEG_MISSING
    assert excinfo.value.detail["reason"] == "not_found"


def test_an_exit_raised_by_the_tool_becomes_an_encode_failure() -> None:
    failed = AppError(
        ErrorCode.AUDIO_FFMPEG_MISSING,
        detail={"reason": "exit", "returncode": 1},
    )
    with pytest.raises(AppError) as excinfo:
        run_ffmpeg(_Tool(error=failed), ["ffmpeg", "-y"])
    assert excinfo.value.code is ErrorCode.AUDIO_ENCODE_FAILED
