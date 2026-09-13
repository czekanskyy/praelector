# SPDX-License-Identifier: Apache-2.0
"""Deterministic fake TTS backend for CI and offline integration tests."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Any

from praelector_tts.backends.base import BaseBackend


class FakeBackend(BaseBackend):
    """Deterministic sine-wave synthesizer with duration proportional to character count.

    Does not require PyTorch or GPU hardware.
    Duration formula: max(0.5, len(text) / 14.0) seconds (PLAN.md §8.4, §10.3).
    """

    backend_id = "fake"

    def __init__(self, sample_rate: int = 24000, frequency: float = 440.0) -> None:
        self.sample_rate = sample_rate
        self.frequency = frequency

    def synthesize(
        self,
        text: str,
        output_path: str,
        reference_audio_path: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[float, int]:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        clean_text = text.strip()
        duration_s = max(0.2, len(clean_text) / 14.0)
        num_frames = int(duration_s * self.sample_rate)

        amplitude = 16000  # PCM16 amplitude range [-32768, 32767]
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)  # Mono
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(self.sample_rate)

            # Generate sine wave samples
            samples = bytearray()
            for i in range(num_frames):
                t = i / self.sample_rate
                val = int(amplitude * math.sin(2.0 * math.pi * self.frequency * t))
                samples.extend(struct.pack("<h", val))

            wav.writeframes(samples)

        return duration_s, self.sample_rate
