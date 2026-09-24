# SPDX-License-Identifier: Apache-2.0
"""The scheduler reuses without a slot and will not pass a waiting chunk."""

from __future__ import annotations

from praelector.gpu.monitor import MonitorTick
from praelector.jobs.admission import AdmissionGate
from praelector.jobs.chunker import PlanItem
from praelector.jobs.scheduler import after_oom, dispatch


def _item(ordinal: int, kind: str = "tts", key: str = "k") -> PlanItem:
    return PlanItem(ordinal, "chp_1", "narrator", "a", kind, key)


def _tick(*, admits: bool = True, paused: bool = False) -> MonitorTick:
    return MonitorTick(
        sampled=True,
        memory_total_mib=12288,
        memory_free_mib=11000 if admits else 2000,
        memory_used_mib=1288,
        admissions_paused=paused,
        paused_now=paused,
        resumed_now=False,
        admits=admits,
    )


def test_reuse_and_silence_take_no_slot() -> None:
    gate = AdmissionGate(1)
    items = [_item(0, "silence", ""), _item(1, key="ready"), _item(2, key="fresh")]
    taken = dispatch(
        items,
        cursor=0,
        reusable=lambda item: item.render_key == "ready",
        gate=gate,
        tick=_tick(),
    )
    assert [(step.ordinal, step.action) for step in taken] == [
        (0, "silence"),
        (1, "reuse"),
        (2, "synth"),
    ]
    assert gate.held == 1


def test_a_full_gate_does_not_skip_ahead() -> None:
    gate = AdmissionGate(1)
    items = [_item(0, key="a"), _item(1, key="ready"), _item(2, key="b")]
    taken = dispatch(items, cursor=0, reusable=lambda item: False, gate=gate, tick=_tick())
    assert [step.ordinal for step in taken] == [0]
    assert gate.held == 1


def test_a_pause_keeps_reuse_and_holds_synthesis() -> None:
    gate = AdmissionGate(2)
    items = [_item(3, key="ready"), _item(4, key="fresh")]
    taken = dispatch(
        items,
        cursor=3,
        reusable=lambda item: item.render_key == "ready",
        gate=gate,
        tick=_tick(paused=True, admits=False),
    )
    assert [(step.ordinal, step.action) for step in taken] == [(3, "reuse")]
    assert gate.held == 0


def test_the_cursor_skips_finished_ordinals() -> None:
    gate = AdmissionGate(2)
    taken = dispatch(
        [_item(0), _item(1), _item(2)],
        cursor=2,
        reusable=lambda _item: False,
        gate=gate,
        tick=_tick(),
    )
    assert [step.ordinal for step in taken] == [2]


def test_oom_retries_once() -> None:
    assert after_oom(0) == "retry"
    assert after_oom(1) == "fail"
