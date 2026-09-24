# SPDX-License-Identifier: Apache-2.0
"""Where a job should resume (JB-07).

Silence does not need a render. The cursor is the first speech ordinal
that is not done, or one past the last item when the plan is finished.
"""

from __future__ import annotations

from collections.abc import Sequence

from praelector.jobs.chunker import PlanItem


def cursor_after(items: Sequence[PlanItem], done: set[int]) -> int:
    """Next ordinal to work on. ``done`` holds speech ordinals already finished."""
    for item in items:
        if item.kind == "silence" or item.ordinal in done:
            continue
        return item.ordinal
    if not items:
        return 0
    return items[-1].ordinal + 1
