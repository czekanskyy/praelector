# SPDX-License-Identifier: Apache-2.0
"""Deterministic speech stand-in (PLAN.md §10.3).

Duration is ``len(text) / 14`` seconds of a quiet sine. Jobs and mux can
run without a GPU or a TTS model. This module does not import torch.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

CHARS_PER_SECOND = 14.0
SAMPLE_RATE = 24000
_FREQUENCY = 440.0
_AMPLITUDE = 0.2


def spoken_seconds(text: str) -> float:
    """How long the fake voice holds this text."""
    return len(text) / CHARS_PER_SECOND


def write_sine(path: Path, text: str) -> float:
    """Write a mono 16-bit WAV and return its duration in seconds."""
    duration = spoken_seconds(text)
    frames = round(duration * SAMPLE_RATE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(_pcm(frames))
    return duration


def _pcm(frames: int) -> bytes:
    if frames <= 0:
        return b""
    scale = _AMPLITUDE * 32767
    step = 2 * math.pi * _FREQUENCY / SAMPLE_RATE
    samples = (int(scale * math.sin(index * step)) for index in range(frames))
    return struct.pack(f"<{frames}h", *samples)
