# SPDX-License-Identifier: Apache-2.0
"""Min/max envelope for a voice-sample waveform (TTS-03).

The UI draws one pair per bucket. Values are in ``[-1, 1]``. A file that is
not a PCM WAV still gets a flat pair so ingest can finish without ffmpeg
having written a real header, which is what the fake tool does in tests.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path


def write_peaks(wav: Path, dest: Path, *, buckets: int = 80) -> None:
    """Write ``dest`` as JSON. ``buckets`` below 1 is treated as 1."""
    count = buckets if buckets >= 1 else 1
    try:
        peaks, rate = envelope(wav, buckets=count)
    except (OSError, wave.Error, EOFError):
        peaks, rate = [[0.0, 0.0]], 0
    dest.write_text(
        json.dumps({"peaks": peaks, "sample_rate": rate}) + "\n",
        encoding="utf-8",
    )


def envelope(wav: Path, *, buckets: int) -> tuple[list[list[float]], int]:
    """``buckets`` min/max pairs from mono or the first channel of PCM16."""
    with wave.open(str(wav), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width != 2 or channels < 1 or rate <= 0:
        raise wave.Error("peaks need 16-bit PCM")
    samples = _mono(frames, channels)
    return _buckets(samples, buckets), rate


def _mono(frames: bytes, channels: int) -> list[int]:
    count = len(frames) // 2
    values = list(memoryview(frames).cast("h"))
    if channels == 1:
        return values[:count]
    return [values[index] for index in range(0, count, channels)]


def _buckets(samples: list[int], buckets: int) -> list[list[float]]:
    if not samples:
        return [[0.0, 0.0]]
    size = max(1, (len(samples) + buckets - 1) // buckets)
    pairs: list[list[float]] = []
    for start in range(0, len(samples), size):
        window = samples[start : start + size]
        low = min(window) / 32768.0
        high = max(window) / 32768.0
        pairs.append([round(low, 5), round(high, 5)])
    return pairs
