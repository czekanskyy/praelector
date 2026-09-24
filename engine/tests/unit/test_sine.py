# SPDX-License-Identifier: Apache-2.0
"""The fake voice lasts one second per fourteen characters."""

from __future__ import annotations

import wave
from pathlib import Path

from praelector.audio.sine import SAMPLE_RATE, spoken_seconds, write_sine


def test_fourteen_characters_are_one_second(tmp_path: Path) -> None:
    text = "a" * 14
    path = tmp_path / "chunk.wav"
    assert spoken_seconds(text) == 1.0
    assert write_sine(path, text) == 1.0
    with wave.open(str(path), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == SAMPLE_RATE
        assert handle.getnframes() == SAMPLE_RATE


def test_an_empty_line_writes_no_frames(tmp_path: Path) -> None:
    path = write_sine(tmp_path / "empty.wav", "")
    assert path == 0.0
    with wave.open(str(tmp_path / "empty.wav"), "rb") as handle:
        assert handle.getnframes() == 0


def test_the_same_text_is_byte_stable(tmp_path: Path) -> None:
    first = tmp_path / "a.wav"
    second = tmp_path / "b.wav"
    write_sine(first, "Cześć")
    write_sine(second, "Cześć")
    assert first.read_bytes() == second.read_bytes()
