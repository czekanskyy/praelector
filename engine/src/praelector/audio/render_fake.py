# SPDX-License-Identifier: Apache-2.0
"""Render one plan line with the fake voice and publish it (JB-02, §10.3).

The sine is written to a partial, probed, and committed. A test can
reuse the chunk afterwards without a GPU.
"""

from __future__ import annotations

import wave
from pathlib import Path

from praelector.audio.sine import write_sine
from praelector.jobs.commit import commit_chunk


def wav_seconds(path: Path) -> float:
    """Duration from the WAV header. An empty file is zero."""
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        if rate <= 0:
            return 0.0
        return handle.getnframes() / rate


def render_chunk(text: str, part: Path, wav: Path, sidecar: Path) -> float:
    """Publish ``text`` as a reusable chunk. Returns the committed duration."""
    write_sine(part, text)
    duration = wav_seconds(part)
    commit_chunk(
        part,
        wav,
        sidecar,
        duration_s=duration,
        probe=wav_seconds,
        extra={"spoken_text": text},
    )
    return duration
