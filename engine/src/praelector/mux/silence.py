# SPDX-License-Identifier: Apache-2.0
"""PCM silence for the gaps between sentences (TTS-08).

The file is mono 16-bit. Concat reads it; nothing here calls ffmpeg.
"""

from __future__ import annotations

import wave
from pathlib import Path


def write_silence(path: Path, *, duration_ms: int, sample_rate: int = 44100) -> Path:
    """Write ``duration_ms`` of silence. A zero duration writes no frames."""
    if duration_ms < 0 or sample_rate < 1:
        raise ValueError("duration and sample rate must be non-negative")
    frames = sample_rate * duration_ms // 1000
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return path
