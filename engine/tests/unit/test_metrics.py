# SPDX-License-Identifier: Apache-2.0
"""Progress rates follow PLAN.md §8.4."""

from __future__ import annotations

from praelector.jobs.metrics import Progress


def test_the_first_chunk_sets_throughput_and_moves_the_char_seed() -> None:
    progress = Progress().observe(chars=28, duration_s=1.0, wall_s=2.0)
    assert progress.rtf_instant == 0.5
    assert progress.throughput == 0.5
    assert progress.chars_per_audio_s == 0.2 * 28 + 0.8 * 14


def test_the_second_chunk_smooths_throughput() -> None:
    progress = Progress().observe(chars=10, duration_s=1.0, wall_s=1.0)
    progress.observe(chars=10, duration_s=1.0, wall_s=2.0)
    assert progress.throughput == 0.2 * 0.5 + 0.8 * 1.0


def test_eta_uses_the_smoothed_rates() -> None:
    progress = Progress().observe(chars=14, duration_s=2.0, wall_s=1.0)
    audio_left = 28 / progress.chars_per_audio_s
    assert progress.eta_seconds(28) == audio_left / progress.throughput


def test_a_zero_duration_does_not_change_the_seed() -> None:
    progress = Progress().observe(chars=10, duration_s=0.0, wall_s=1.0)
    assert progress.chars_per_audio_s == 14.0
    assert progress.eta_seconds(14) == 0.0
