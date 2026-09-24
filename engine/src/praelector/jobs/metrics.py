# SPDX-License-Identifier: Apache-2.0
"""Smoothed progress for a recording job (PLAN.md §8.4).

Instant RTF is this chunk's audio divided by its wall time. Throughput
and characters per audio second are exponential moving averages. The
character rate starts at 14, the Polish seed, and the first chunk sets
throughput.
"""

from __future__ import annotations

from dataclasses import dataclass

_ALPHA = 0.2
_SEED_CHARS_PER_AUDIO_S = 14.0


@dataclass
class Progress:
    """Rates after zero or more finished chunks."""

    throughput: float = 0.0
    chars_per_audio_s: float = _SEED_CHARS_PER_AUDIO_S
    rtf_instant: float | None = None
    _seen: int = 0

    def observe(self, *, chars: int, duration_s: float, wall_s: float) -> Progress:
        """Fold one finished chunk into the averages. Zero time is ignored."""
        if duration_s <= 0 or wall_s <= 0:
            return self
        sample_throughput = duration_s / wall_s
        sample_chars = chars / duration_s
        if self._seen == 0:
            throughput = sample_throughput
        else:
            throughput = _ALPHA * sample_throughput + (1 - _ALPHA) * self.throughput
        chars_rate = _ALPHA * sample_chars + (1 - _ALPHA) * self.chars_per_audio_s
        self.throughput = throughput
        self.chars_per_audio_s = chars_rate
        self.rtf_instant = sample_throughput
        self._seen += 1
        return self

    def eta_seconds(self, remaining_chars: int) -> float:
        """Wall seconds left. A zero throughput means nothing has finished yet."""
        if self.throughput <= 0 or self.chars_per_audio_s <= 0:
            return 0.0
        audio_left = remaining_chars / self.chars_per_audio_s
        return audio_left / self.throughput
