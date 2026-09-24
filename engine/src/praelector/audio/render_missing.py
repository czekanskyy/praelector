# SPDX-License-Identifier: Apache-2.0
"""Render the plan lines that are not already reusable.

Silence is skipped. A chunk the sidecar already accepts is left alone.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from praelector.audio.render_fake import render_chunk
from praelector.jobs.chunker import PlanItem

Paths = Callable[[PlanItem], tuple[Path, Path, Path]]
Reusable = Callable[[PlanItem], bool]


def render_missing(
    items: Sequence[PlanItem],
    *,
    paths_for: Paths,
    reusable: Reusable,
) -> list[int]:
    """Ordinals that were rendered now. Already-good lines are not touched."""
    rendered: list[int] = []
    for item in items:
        if item.kind == "silence":
            continue
        if reusable(item):
            continue
        part, wav, sidecar = paths_for(item)
        render_chunk(item.spoken_text, part, wav, sidecar)
        rendered.append(item.ordinal)
    return rendered
