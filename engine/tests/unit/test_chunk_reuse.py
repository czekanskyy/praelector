# SPDX-License-Identifier: Apache-2.0
"""Chunk reuse needs a matching sidecar and WAV (JB-05)."""

from __future__ import annotations

import json
from pathlib import Path

from praelector.jobs.reuse import chunk_reusable


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_a_matching_wav_and_sidecar_are_reusable(tmp_path: Path) -> None:
    wav = tmp_path / "chunk.wav"
    wav.write_bytes(b"RIFF")
    sidecar = tmp_path / "chunk.json"
    _write(sidecar, {"size": 4, "duration_s": 1.5})
    assert chunk_reusable(wav, sidecar, probe=lambda _path: 1.5)


def test_a_missing_file_is_not_reusable(tmp_path: Path) -> None:
    wav = tmp_path / "chunk.wav"
    wav.write_bytes(b"RIFF")
    assert not chunk_reusable(wav, tmp_path / "missing.json", probe=lambda _path: 1.5)


def test_a_size_mismatch_is_not_reusable(tmp_path: Path) -> None:
    wav = tmp_path / "chunk.wav"
    wav.write_bytes(b"RIFF")
    sidecar = tmp_path / "chunk.json"
    _write(sidecar, {"size": 99, "duration_s": 1.5})
    assert not chunk_reusable(wav, sidecar, probe=lambda _path: 1.5)


def test_a_duration_mismatch_is_not_reusable(tmp_path: Path) -> None:
    wav = tmp_path / "chunk.wav"
    wav.write_bytes(b"RIFF")
    sidecar = tmp_path / "chunk.json"
    _write(sidecar, {"size": 4, "duration_s": 1.5})
    assert not chunk_reusable(wav, sidecar, probe=lambda _path: 2.0)


def test_a_broken_sidecar_is_not_reusable(tmp_path: Path) -> None:
    wav = tmp_path / "chunk.wav"
    wav.write_bytes(b"RIFF")
    sidecar = tmp_path / "chunk.json"
    sidecar.write_text("{", encoding="utf-8")
    assert not chunk_reusable(wav, sidecar, probe=lambda _path: 1.5)
