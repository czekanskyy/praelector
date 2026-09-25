# SPDX-License-Identifier: Apache-2.0
"""Waveform peaks come from the PCM, and a non-wav still gets a flat pair."""

from __future__ import annotations

import json
import wave
from pathlib import Path

from praelector.voices.waveform import envelope, write_peaks


def _wav(path: Path, samples: list[int]) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(
            b"".join(int(sample).to_bytes(2, "little", signed=True) for sample in samples)
        )


def test_two_buckets_hold_the_min_and_max(tmp_path: Path) -> None:
    wav = tmp_path / "sample.wav"
    _wav(wav, [0, 32767, -32768, 0])
    pairs, rate = envelope(wav, buckets=2)
    assert rate == 8000
    assert pairs == [[0.0, 0.99997], [-1.0, 0.0]]


def test_a_canned_file_still_writes_a_flat_pair(tmp_path: Path) -> None:
    wav = tmp_path / "canned.wav"
    wav.write_bytes(b"RIFF-canned")
    dest = tmp_path / "peaks.json"
    write_peaks(wav, dest)
    body = json.loads(dest.read_text(encoding="utf-8"))
    assert body["peaks"] == [[0.0, 0.0]]
    assert body["sample_rate"] == 0
