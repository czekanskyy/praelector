# SPDX-License-Identifier: Apache-2.0
"""How many TTS workers may start (GPU-05).

The monitor decides whether memory allows another worker. This gate turns
that decision into slots: at most ``effective`` workers are admitted, a
tight sample waits, and a pause admits nobody. Workers already running
are not stopped.
"""

from __future__ import annotations

from typing import Literal

from praelector.gpu.monitor import MonitorTick

Admission = Literal["admit", "wait", "paused"]


class AdmissionGate:
    """A slot count of size ``effective``. ``try_acquire`` does not block."""

    def __init__(self, effective: int) -> None:
        self._slots = effective if effective >= 1 else 1
        self._held = 0

    @property
    def held(self) -> int:
        return self._held

    def try_acquire(self, tick: MonitorTick) -> Admission:
        """Take one slot, or say why this sample cannot start a worker."""
        if tick.admissions_paused:
            return "paused"
        if not tick.admits or self._held >= self._slots:
            return "wait"
        self._held += 1
        return "admit"

    def release(self) -> None:
        """Return one slot when a worker exits. Extra releases are ignored."""
        if self._held > 0:
            self._held -= 1
