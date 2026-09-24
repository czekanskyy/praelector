# SPDX-License-Identifier: Apache-2.0
"""1 Hz VRAM sampler and the admissions pause (GPU-05).

The slot gate that consumes these decisions is
:mod:`praelector.jobs.admission`. A probe returns the latest free MiB; the
monitor calls it at most once per second and pauses admissions when free
memory drops below the reserve from :mod:`praelector.gpu.budget`. Three
later samples with the reserve intact resume admissions. Running workers
are not stopped here.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from praelector.gpu.budget import admits_worker

#: PLAN.md §7.3 — re-check on the next 1 s tick.
SAMPLE_INTERVAL_S: Final = 1.0

#: PLAN.md §7.3 — resume only after headroom holds for this many samples.
RESUME_SAMPLES: Final = 3


@dataclass(frozen=True, slots=True)
class VramReading:
    """One probe result. MiB, same units as :class:`praelector.gpu.budget.GpuBudget`."""

    memory_total_mib: int | None
    memory_free_mib: int | None


@dataclass(frozen=True, slots=True)
class MonitorTick:
    """What one poll decided. ``sampled`` is false when the interval has not elapsed."""

    sampled: bool
    memory_total_mib: int | None
    memory_free_mib: int | None
    memory_used_mib: int | None
    admissions_paused: bool
    paused_now: bool
    resumed_now: bool
    admits: bool


class VramMonitor:
    """Poll a probe on a 1 s cadence and track the admissions pause."""

    def __init__(
        self,
        probe: Callable[[], VramReading],
        *,
        reserve_mib: int,
        peak_worker_mib: int,
        interval_s: float = SAMPLE_INTERVAL_S,
        resume_samples: int = RESUME_SAMPLES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._probe = probe
        self._reserve_mib = reserve_mib
        self._peak_worker_mib = peak_worker_mib
        self._interval_s = interval_s
        self._resume_samples = resume_samples
        self._clock = clock
        self._last_at: float | None = None
        self._last: MonitorTick | None = None
        self._paused = False
        self._clear_streak = 0

    @property
    def admissions_paused(self) -> bool:
        return self._paused

    def poll(self, now: float | None = None) -> MonitorTick:
        """Return the latest decision. A probe runs only when ``interval_s`` has passed."""
        moment = self._clock() if now is None else now
        if (
            self._last is not None
            and self._last_at is not None
            and moment - self._last_at < self._interval_s
        ):
            return MonitorTick(
                sampled=False,
                memory_total_mib=self._last.memory_total_mib,
                memory_free_mib=self._last.memory_free_mib,
                memory_used_mib=self._last.memory_used_mib,
                admissions_paused=self._paused,
                paused_now=False,
                resumed_now=False,
                admits=self._last.admits and not self._paused,
            )
        reading = self._probe()
        tick = self._decide(reading)
        self._last_at = moment
        self._last = tick
        return tick

    def _decide(self, reading: VramReading) -> MonitorTick:
        free = reading.memory_free_mib
        total = reading.memory_total_mib
        used = total - free if total is not None and free is not None else None
        below_reserve = free is not None and free < self._reserve_mib
        paused_now = False
        resumed_now = False
        if below_reserve:
            self._clear_streak = 0
            if not self._paused:
                self._paused = True
                paused_now = True
        elif self._paused:
            self._clear_streak += 1
            if self._clear_streak >= self._resume_samples:
                self._paused = False
                self._clear_streak = 0
                resumed_now = True
        else:
            self._clear_streak = 0
        fits = free is not None and admits_worker(
            memory_free_mib=free,
            reserve_mib=self._reserve_mib,
            peak_worker_mib=self._peak_worker_mib,
        )
        return MonitorTick(
            sampled=True,
            memory_total_mib=total,
            memory_free_mib=free,
            memory_used_mib=used,
            admissions_paused=self._paused,
            paused_now=paused_now,
            resumed_now=resumed_now,
            admits=fits and not self._paused,
        )
