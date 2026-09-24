# SPDX-License-Identifier: Apache-2.0
"""A fake render is reusable once the sidecar matches the wav."""

from __future__ import annotations

from pathlib import Path

from praelector.audio.render_fake import render_chunk, wav_seconds
from praelector.jobs.reuse import chunk_reusable


def test_a_rendered_line_can_be_reused(tmp_path: Path) -> None:
    part = tmp_path / "a.wav.part"
    wav = tmp_path / "aa" / "abcd.wav"
    sidecar = wav.with_suffix(".json")
    duration = render_chunk("a" * 14, part, wav, sidecar)
    assert duration == 1.0
    assert not part.exists()
    assert chunk_reusable(wav, sidecar, probe=wav_seconds)
