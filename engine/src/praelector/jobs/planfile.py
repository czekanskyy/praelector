# SPDX-License-Identifier: Apache-2.0
"""Ordered ``plan.jsonl`` for one job (PLAN.md §8.2).

The file is rewritten as a whole. Readers see either the previous plan or
the new one, never a truncated line.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from praelector.jobs.chunker import PlanItem
from praelector.store.atomic import canonical_json, write_text_atomic


def write_plan(path: Path, items: list[PlanItem]) -> None:
    body = "".join(canonical_json(asdict(item)) for item in items)
    write_text_atomic(path, body)


def read_plan(path: Path) -> list[PlanItem]:
    if not path.is_file():
        return []
    items: list[PlanItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        payload = json.loads(line)
        items.append(
            PlanItem(
                ordinal=int(payload["ordinal"]),
                chapter_id=payload["chapter_id"],
                voice_slot=payload["voice_slot"],
                spoken_text=payload["spoken_text"],
                kind=payload["kind"],
                render_key=payload["render_key"],
            )
        )
    return items
