# SPDX-License-Identifier: Apache-2.0
"""ffmpeg resolution prefers settings, then PATH, then the data directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from praelector.audio.resolve import resolve_tool
from praelector.errors import AppError, ErrorCode


def test_an_explicit_file_wins(tmp_path: Path) -> None:
    configured = tmp_path / "custom" / "ffmpeg"
    configured.parent.mkdir()
    configured.write_bytes(b"x")
    on_path = tmp_path / "from-path"
    on_path.write_bytes(b"y")
    found = resolve_tool(
        "ffmpeg",
        configured=str(configured),
        bin_dir=tmp_path / "bin",
        which=lambda _name: str(on_path),
    )
    assert found == configured


def test_path_is_used_when_settings_are_empty(tmp_path: Path) -> None:
    on_path = tmp_path / "ffmpeg"
    on_path.write_bytes(b"y")
    found = resolve_tool(
        "ffmpeg",
        configured=None,
        bin_dir=tmp_path / "bin",
        which=lambda _name: str(on_path),
    )
    assert found == on_path


def test_the_data_dir_binary_is_the_last_resort(tmp_path: Path) -> None:
    bundled = tmp_path / "bin" / "ffmpeg.exe"
    bundled.parent.mkdir()
    bundled.write_bytes(b"z")
    found = resolve_tool(
        "ffmpeg",
        configured=None,
        bin_dir=tmp_path / "bin",
        which=lambda _name: None,
        suffix=".exe",
    )
    assert found == bundled


def test_a_total_miss_is_ffmpeg_missing(tmp_path: Path) -> None:
    with pytest.raises(AppError) as caught:
        resolve_tool(
            "ffprobe",
            configured=None,
            bin_dir=tmp_path,
            which=lambda _name: None,
        )
    assert caught.value.code is ErrorCode.AUDIO_FFMPEG_MISSING
    assert caught.value.detail["tool"] == "ffprobe"
