# SPDX-License-Identifier: Apache-2.0
"""Silence files are mono 16-bit and the requested length."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from praelector.mux.silence import write_silence


def test_three_hundred_milliseconds_at_44k(tmp_path: Path) -> None:
    path = write_silence(tmp_path / "gap.wav", duration_ms=300, sample_rate=44100)
    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 44100
        assert handle.getnframes() == 44100 * 300 // 1000


def test_zero_duration_writes_no_frames(tmp_path: Path) -> None:
    path = write_silence(tmp_path / "gap.wav", duration_ms=0)
    with wave.open(str(path), "rb") as handle:
        assert handle.getnframes() == 0


def test_a_negative_duration_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_silence(tmp_path / "gap.wav", duration_ms=-1)
