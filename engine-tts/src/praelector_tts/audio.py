# SPDX-License-Identifier: Apache-2.0
"""PCM to WAV, with no dependency beyond the standard library.

Real backends hold a torch tensor; they convert to mono float32 in
``[-1.0, 1.0]`` and hand the samples here. Keeping the writer torch-free is what
lets the ``fake`` backend — and therefore the whole job engine — run in CI.
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from array import array
from collections.abc import Sequence
from pathlib import Path

from praelector_tts.protocol import PART_SUFFIX

PCM16_MAX = 32767


def part_path(out_path: str | Path) -> Path:
    """The temporary path a worker writes to before the engine renames it."""
    return Path(str(out_path) + PART_SUFFIX)


def float_to_pcm16(samples: Sequence[float]) -> bytes:
    """Clamp and quantise to little-endian PCM16.

    Clipping is intentional: a hot model must flatten, never wrap around.
    """
    quantised = array("h", (int(max(-1.0, min(1.0, s)) * PCM16_MAX) for s in samples))
    if sys.byteorder == "big":
        quantised.byteswap()
    return quantised.tobytes()


def write_wav(path: str | Path, samples: Sequence[float], sample_rate: int) -> Path:
    """Write mono PCM16 WAV to ``path``. Empty input still produces a valid file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(float_to_pcm16(samples))
    return destination


def write_wav_part(out_path: str | Path, samples: Sequence[float], sample_rate: int) -> Path:
    """Write to ``<out_path>.part``; the engine renames it after validating."""
    return write_wav(part_path(out_path), samples, sample_rate)


def read_wav(path: str | Path) -> tuple[list[float], int]:
    """Read a mono PCM16 WAV back as floats in ``[-1.0, 1.0]``.

    Workers only ever write mono; user samples are downmixed by ffmpeg on the
    engine side before they reach a backend, so stereo is an error here rather
    than a case to handle.
    """
    with wave.open(str(path), "rb") as source:
        sample_rate = source.getframerate()
        channels = source.getnchannels()
        width = source.getsampwidth()
        raw = source.readframes(source.getnframes())
    if width != 2:
        raise ValueError(f"only PCM16 is supported, got sample width {width}")
    if channels != 1:
        raise ValueError(f"only mono is supported, got {channels} channels")
    values = struct.unpack(f"<{len(raw) // 2}h", raw)
    return [v / PCM16_MAX for v in values], sample_rate


def sine(
    duration_s: float,
    sample_rate: int,
    frequency: float,
    amplitude: float = 0.2,
) -> list[float]:
    """A deterministic tone. The ``fake`` backend's whole synthesis engine."""
    total = max(0, round(duration_s * sample_rate))
    step = 2.0 * math.pi * frequency / sample_rate
    return [amplitude * math.sin(step * i) for i in range(total)]
