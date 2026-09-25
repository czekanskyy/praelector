# SPDX-License-Identifier: Apache-2.0
"""Compile chapter blocks into ``plan.jsonl`` (PLAN.md §8.2).

The planner assigns slots. The chunker packs sentences. This writes the
file the render pass will read. It does not render.
"""

from __future__ import annotations

from pathlib import Path

from praelector.domain.enums import VoiceMode
from praelector.jobs.chunker import PlanItem, plan_runs
from praelector.jobs.planfile import write_plan
from praelector.jobs.planner import SourceBlock, spoken_runs


def compile_plan(
    path: Path,
    blocks: list[SourceBlock],
    *,
    mode: VoiceMode,
    filled: set[str],
    profiles: dict[str, tuple[str, str]],
    max_input_chars: int,
    backend_id: str,
    adapter_version: str,
    model_revision: str,
) -> tuple[list[PlanItem], list[str]]:
    """Write the plan and return it with any slot-fallback warnings."""
    runs, warnings = spoken_runs(blocks, mode=mode, filled=filled, profiles=profiles)
    items = plan_runs(
        runs,
        max_input_chars=max_input_chars,
        backend_id=backend_id,
        adapter_version=adapter_version,
        model_revision=model_revision,
    )
    write_plan(path, items)
    return items, warnings
