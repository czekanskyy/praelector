# SPDX-License-Identifier: Apache-2.0
"""A chunk is reusable only after the partial is renamed and the sidecar matches."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from praelector.errors import AppError, ErrorCode
from praelector.jobs.commit import commit_chunk
from praelector.jobs.reuse import chunk_reusable


def test_a_matching_partial_becomes_a_reusable_chunk(tmp_path: Path) -> None:
    part = tmp_path / "a.wav.part"
    part.write_bytes(b"RIFF")
    wav = tmp_path / "aa" / "abcd.wav"
    sidecar = wav.with_suffix(".json")
    commit_chunk(
        part,
        wav,
        sidecar,
        duration_s=1.5,
        probe=lambda _path: 1.5,
        extra={"render_key": "abcd"},
    )
    assert not part.exists()
    assert wav.read_bytes() == b"RIFF"
    saved = json.loads(sidecar.read_text(encoding="utf-8"))
    assert saved["size"] == 4
    assert saved["duration_s"] == 1.5
    assert saved["render_key"] == "abcd"
    assert chunk_reusable(wav, sidecar, probe=lambda _path: 1.5)


def test_a_duration_mismatch_drops_the_partial(tmp_path: Path) -> None:
    part = tmp_path / "a.wav.part"
    part.write_bytes(b"RIFF")
    wav = tmp_path / "abcd.wav"
    with pytest.raises(AppError) as caught:
        commit_chunk(part, wav, wav.with_suffix(".json"), duration_s=1.5, probe=lambda _path: 9.0)
    assert caught.value.code is ErrorCode.AUDIO_PROBE_FAILED
    assert not part.exists()
    assert not wav.exists()


def test_an_empty_partial_is_rejected(tmp_path: Path) -> None:
    part = tmp_path / "a.wav.part"
    part.write_bytes(b"")
    wav = tmp_path / "abcd.wav"
    with pytest.raises(AppError) as caught:
        commit_chunk(part, wav, wav.with_suffix(".json"), duration_s=1.0, probe=lambda _path: 1.0)
    assert caught.value.code is ErrorCode.AUDIO_PROBE_FAILED
    assert not part.exists()
