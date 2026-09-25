# SPDX-License-Identifier: Apache-2.0
"""One page of a job plan, with a reuse flag on each speech item (JB-05)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from praelector.jobs.chunker import PlanItem

Reusable = Callable[[PlanItem], bool]


def annotate_plan(
    items: Sequence[PlanItem],
    *,
    reusable: Reusable,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    """``reusable`` is not called for silence. Those rows are never chunks."""
    page = items[offset : offset + limit]
    return {
        "total": len(items),
        "offset": offset,
        "items": [_row(item, reusable) for item in page],
    }


def _row(item: PlanItem, reusable: Reusable) -> dict[str, Any]:
    return {
        "ordinal": item.ordinal,
        "chapter_id": item.chapter_id,
        "voice_slot": item.voice_slot,
        "spoken_text": item.spoken_text,
        "kind": item.kind,
        "render_key": item.render_key,
        "reusable": False if item.kind == "silence" else reusable(item),
    }
