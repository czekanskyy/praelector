# SPDX-License-Identifier: Apache-2.0
"""Tests for the stdlib-only WAV writer."""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from praelector_tts.audio import (
    PCM16_MAX,
    float_to_pcm16,
    part_path,
    read_wav,
    sine,
    write_wav,
    write_wav_part,
)


def test_part_path_appends_the_suffix(tmp_path: Path) -> None:
    assert part_path(tmp_path / "ab" / "rk.wav") == tmp_path / "ab" / "rk.wav.part"
    assert part_path(str(tmp_path / "rk.wav")) == tmp_path / "rk.wav.part"


def test_quantisation_is_little_endian_pcm16() -> None:
    assert float_to_pcm16([0.0]) == b"\x00\x00"
    assert float_to_pcm16([1.0]) == PCM16_MAX.to_bytes(2, "little")
    assert float_to_pcm16([-1.0]) == (-PCM16_MAX).to_bytes(2, "little", signed=True)


def test_out_of_range_samples_clip_instead_of_wrapping() -> None:
    assert float_to_pcm16([4.0]) == float_to_pcm16([1.0])
    assert float_to_pcm16([-4.0]) == float_to_pcm16([-1.0])


def test_write_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "audio" / "chunks" / "ab" / "rk.wav"
    write_wav(target, sine(0.01, 8000, 440.0), 8000)
    assert target.exists()


def test_round_trip_preserves_rate_and_length(tmp_path: Path) -> None:
    samples = sine(0.25, 24000, 220.0, amplitude=0.5)
    target = write_wav(tmp_path / "a.wav", samples, 24000)
    recovered, rate = read_wav(target)
    assert rate == 24000
    assert len(recovered) == len(samples)
    assert recovered[0] == pytest.approx(samples[0], abs=1 / PCM16_MAX)


def test_the_header_is_pcm16_mono(tmp_path: Path) -> None:
    target = write_wav(tmp_path / "a.wav", sine(0.05, 16000, 440.0), 16000)
    with wave.open(str(target), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 16000


def test_write_wav_part_uses_the_temporary_name(tmp_path: Path) -> None:
    written = write_wav_part(tmp_path / "rk.wav", sine(0.05, 24000, 440.0), 24000)
    assert written.name == "rk.wav.part"
    assert not (tmp_path / "rk.wav").exists()


def test_empty_input_still_produces_a_valid_file(tmp_path: Path) -> None:
    target = write_wav(tmp_path / "empty.wav", [], 24000)
    samples, rate = read_wav(target)
    assert samples == []
    assert rate == 24000


def test_sine_length_follows_the_duration() -> None:
    assert len(sine(1.0, 24000, 440.0)) == 24000
    assert len(sine(0.0, 24000, 440.0)) == 0
    assert len(sine(-1.0, 24000, 440.0)) == 0


def test_sine_is_deterministic() -> None:
    assert sine(0.1, 24000, 440.0) == sine(0.1, 24000, 440.0)


def test_read_rejects_non_pcm16(tmp_path: Path) -> None:
    target = tmp_path / "wide.wav"
    with wave.open(str(target), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(4)
        out.setframerate(8000)
        out.writeframes(b"\x00" * 8)
    with pytest.raises(ValueError, match="PCM16"):
        read_wav(target)


def test_read_rejects_stereo(tmp_path: Path) -> None:
    target = tmp_path / "stereo.wav"
    with wave.open(str(target), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00" * 8)
    with pytest.raises(ValueError, match="mono"):
        read_wav(target)
