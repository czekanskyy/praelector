# SPDX-License-Identifier: Apache-2.0
"""Walk a plan and decide what can start (GPU-05).

Reuse and silence need no worker. Synthesis takes one admission slot.
A paused tick stops new synthesis. One ``tts.oom`` is retried; the next
fails that item and leaves the job running.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from praelector.gpu.monitor import MonitorTick
from praelector.jobs.admission import AdmissionGate
from praelector.jobs.chunker import PlanItem

Action = Literal["reuse", "silence", "synth"]
OomDecision = Literal["retry", "fail"]


@dataclass(frozen=True, slots=True)
class Dispatch:
    """One item the scheduler will not block on."""

    ordinal: int
    action: Action


def dispatch(
    items: Sequence[PlanItem],
    *,
    cursor: int,
    reusable: Callable[[PlanItem], bool],
    gate: AdmissionGate,
    tick: MonitorTick,
) -> list[Dispatch]:
    """Leading reuse and silence, then as many synths as the gate allows.

    Stops at the first synth the gate will not admit, so a later chunk
    cannot jump a waiting one.
    """
    taken: list[Dispatch] = []
    for item in items:
        if item.ordinal < cursor:
            continue
        if item.kind == "silence":
            taken.append(Dispatch(item.ordinal, "silence"))
            continue
        if reusable(item):
            taken.append(Dispatch(item.ordinal, "reuse"))
            continue
        if gate.try_acquire(tick) != "admit":
            break
        taken.append(Dispatch(item.ordinal, "synth"))
    return taken


def after_oom(attempts: int) -> OomDecision:
    """``attempts`` is how many OOMs this item has already seen."""
    if attempts < 1:
        return "retry"
    return "fail"
