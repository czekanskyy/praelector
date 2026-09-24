# SPDX-License-Identifier: Apache-2.0
"""The cursor stops on the first speech chunk that is not done."""

from __future__ import annotations

from praelector.jobs.chunker import PlanItem
from praelector.jobs.cursor import cursor_after


def _item(ordinal: int, kind: str = "tts") -> PlanItem:
    return PlanItem(ordinal, "chp_1", "narrator", "a", kind, f"k{ordinal}")


def test_the_cursor_skips_silence_and_finished_speech() -> None:
    items = [_item(0), _item(1, "silence"), _item(2)]
    assert cursor_after(items, {0}) == 2


def test_a_finished_plan_points_past_the_end() -> None:
    items = [_item(4), _item(5, "silence")]
    assert cursor_after(items, {4}) == 6


def test_an_empty_plan_starts_at_zero() -> None:
    assert cursor_after([], set()) == 0
