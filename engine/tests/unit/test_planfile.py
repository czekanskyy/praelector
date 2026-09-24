# SPDX-License-Identifier: Apache-2.0
"""plan.jsonl round-trips the chunker's items in order."""

from __future__ import annotations

from pathlib import Path

from praelector.jobs.chunker import PlanItem
from praelector.jobs.planfile import read_plan, write_plan


def test_a_plan_round_trips_in_order(tmp_path: Path) -> None:
    path = tmp_path / "plan.jsonl"
    items = [
        PlanItem(0, "chp_1", "narrator", "Szła.", "tts", "aa"),
        PlanItem(1, "chp_1", "narrator", "", "silence", ""),
        PlanItem(2, "chp_2", "female", "Nie zdążymy.", "tts", "bb"),
    ]
    write_plan(path, items)
    assert read_plan(path) == items


def test_rewriting_a_plan_replaces_the_previous_lines(tmp_path: Path) -> None:
    path = tmp_path / "plan.jsonl"
    write_plan(path, [PlanItem(0, "chp_1", "narrator", "Stare.", "tts", "aa")])
    write_plan(path, [PlanItem(0, "chp_1", "narrator", "Nowe.", "tts", "bb")])
    assert read_plan(path) == [PlanItem(0, "chp_1", "narrator", "Nowe.", "tts", "bb")]


def test_a_missing_plan_reads_as_empty(tmp_path: Path) -> None:
    assert read_plan(tmp_path / "plan.jsonl") == []
