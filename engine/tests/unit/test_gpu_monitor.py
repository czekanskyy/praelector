# SPDX-License-Identifier: Apache-2.0
"""The VRAM monitor, driven by an injected probe and clock. No GPU, no sleep."""

from __future__ import annotations

from praelector.domain.enums import GpuVendor
from praelector.gpu.budget import compute_budget
from praelector.gpu.monitor import VramMonitor, VramReading

#: RTX 4070 Ti from PLAN.md §7.2. Reserve is 2458 MiB, so used above 9830 pauses.
_TOTAL = 12288
_RESERVE = 2458
_PEAK = 3500


def test_probe_runs_once_per_second() -> None:
    calls = {"n": 0}

    def probe() -> VramReading:
        calls["n"] += 1
        return VramReading(memory_total_mib=_TOTAL, memory_free_mib=11000)

    monitor = VramMonitor(probe, reserve_mib=_RESERVE, peak_worker_mib=_PEAK)
    first = monitor.poll(now=0.0)
    second = monitor.poll(now=0.5)
    third = monitor.poll(now=1.0)
    assert calls["n"] == 2
    assert first.sampled is True
    assert second.sampled is False
    assert second.memory_free_mib == 11000
    assert third.sampled is True
    assert third.admits is True


def test_used_memory_crossing_the_reserve_pauses_until_three_clear_samples() -> None:
    budget = compute_budget(
        vendor=GpuVendor.NVIDIA,
        memory_total_mib=_TOTAL,
        memory_free_mib=11000,
        backend_id="omnivoice",
        precision="fp16",
        worker_cap=4,
        backend_max_parallel=4,
    )
    assert budget.reserve_mib == _RESERVE
    free_values = iter([11000, 2000, 2000, 11000, 11000, 11000])

    def probe() -> VramReading:
        return VramReading(memory_total_mib=_TOTAL, memory_free_mib=next(free_values))

    monitor = VramMonitor(
        probe, reserve_mib=budget.reserve_mib, peak_worker_mib=budget.peak_worker_mib
    )
    healthy = monitor.poll(now=0.0)
    paused = monitor.poll(now=1.0)
    still = monitor.poll(now=2.0)
    one = monitor.poll(now=3.0)
    two = monitor.poll(now=4.0)
    three = monitor.poll(now=5.0)

    assert healthy.admissions_paused is False
    assert healthy.memory_used_mib == _TOTAL - 11000
    assert paused.paused_now is True
    assert paused.admissions_paused is True
    assert paused.admits is False
    assert paused.memory_used_mib == _TOTAL - 2000
    assert paused.memory_used_mib > _TOTAL - _RESERVE
    assert still.paused_now is False
    assert still.admissions_paused is True
    assert one.admissions_paused is True
    assert two.admissions_paused is True
    assert three.resumed_now is True
    assert three.admissions_paused is False
    assert three.admits is True


def test_a_tight_sample_waits_without_pausing_admissions() -> None:
    """free - reserve is positive but smaller than one worker: wait, do not pause."""
    monitor = VramMonitor(
        lambda: VramReading(memory_total_mib=_TOTAL, memory_free_mib=_RESERVE + 100),
        reserve_mib=_RESERVE,
        peak_worker_mib=_PEAK,
    )
    tick = monitor.poll(now=0.0)
    assert tick.admissions_paused is False
    assert tick.admits is False
    assert tick.paused_now is False
