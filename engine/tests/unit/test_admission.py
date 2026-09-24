# SPDX-License-Identifier: Apache-2.0
"""Slot admission from a monitor tick. No worker is spawned."""

from __future__ import annotations

from praelector.gpu.monitor import MonitorTick
from praelector.jobs.admission import AdmissionGate


def test_two_slots_admit_twice_then_wait() -> None:
    gate = AdmissionGate(2)
    assert gate.try_acquire(_tick(admits=True)) == "admit"
    assert gate.try_acquire(_tick(admits=True)) == "admit"
    assert gate.try_acquire(_tick(admits=True)) == "wait"
    assert gate.held == 2
    gate.release()
    assert gate.try_acquire(_tick(admits=True)) == "admit"


def test_a_pause_admits_nobody_and_keeps_the_running_slot() -> None:
    gate = AdmissionGate(2)
    assert gate.try_acquire(_tick(admits=True)) == "admit"
    assert gate.try_acquire(_tick(paused=True, admits=False)) == "paused"
    assert gate.held == 1


def test_a_tight_sample_waits_without_taking_a_slot() -> None:
    gate = AdmissionGate(2)
    assert gate.try_acquire(_tick(admits=False)) == "wait"
    assert gate.held == 0


def _tick(*, admits: bool, paused: bool = False) -> MonitorTick:
    return MonitorTick(
        sampled=True,
        memory_total_mib=12288,
        memory_free_mib=11000 if admits else 2000,
        memory_used_mib=1288 if admits else 10288,
        admissions_paused=paused,
        paused_now=paused,
        resumed_now=False,
        admits=admits,
    )
