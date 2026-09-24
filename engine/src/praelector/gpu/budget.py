# SPDX-License-Identifier: Apache-2.0
"""VRAM budget math (GPU-03, GPU-04).

The formula is PLAN.md §7.2, unchanged. Detection already knows how much
memory a card has; this module only decides how many workers that memory
can hold. It does not sample the driver and it does not spawn a worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from praelector.domain.enums import GpuVendor
from praelector.errors import AppError, ErrorCode

#: PLAN.md §7.2 — reserve is at least 1.5 GiB, otherwise 20 % of the card.
_RESERVE_FLOOR_MIB: Final = 1536
_RESERVE_NUMERATOR: Final = 20
_RESERVE_DENOMINATOR: Final = 100

#: DATA_MODEL.md §10 seed. qwen3-tts 1.7B is selected with ``model="1.7b"``.
_SEED_PEAK_MIB: Final = {
    ("omnivoice", "fp16"): 3500,
    ("omnivoice", "fp32"): 6000,
    ("chatterbox", "fp16"): 4500,
    ("qwen3_tts", "fp16"): 4000,
    ("fake", ""): 64,
}
_QWEN_LARGE_MIB: Final = 7000

ReserveSource = Literal["default", "user_override"]
PeakSource = Literal["table_default", "measured", "user_override"]


@dataclass(frozen=True, slots=True)
class GpuBudget:
    """One computed snapshot. ``admissions_paused`` stays false until a monitor exists."""

    vendor: GpuVendor
    memory_total_mib: int | None
    memory_free_mib: int | None
    backend_id: str
    precision: str
    reserve_mib: int
    reserve_source: ReserveSource
    peak_worker_mib: int
    peak_source: PeakSource
    max_workers_formula: int
    worker_cap: int
    backend_max_parallel: int
    effective_workers: int
    low_vram_warning: bool
    admissions_paused: bool = False


def compute_budget(
    *,
    vendor: GpuVendor,
    memory_total_mib: int | None,
    memory_free_mib: int | None,
    backend_id: str,
    precision: str,
    worker_cap: int,
    backend_max_parallel: int,
    reserve_override_mib: int | None = None,
    peak_override_mib: int | None = None,
    measured_peak_mib: int | None = None,
    model: str = "0.6b",
) -> GpuBudget:
    """How many workers this device may run for one backend.

    CPU, and any device whose VRAM cannot be read, is one worker. A GPU uses
    ``max(1, floor((free - reserve) / peak))``, then clamps down to the
    settings cap and the backend's own parallel limit, never below 1.
    """
    peak_mib, peak_source = _peak(
        backend_id,
        precision,
        model,
        override_mib=peak_override_mib,
        measured_mib=measured_peak_mib,
    )
    cap = _at_least_one(worker_cap)
    parallel = _at_least_one(backend_max_parallel)
    if vendor is GpuVendor.CPU or memory_total_mib is None or memory_free_mib is None:
        return GpuBudget(
            vendor=vendor,
            memory_total_mib=memory_total_mib,
            memory_free_mib=memory_free_mib,
            backend_id=backend_id,
            precision=precision,
            reserve_mib=0,
            reserve_source="default",
            peak_worker_mib=peak_mib,
            peak_source=peak_source,
            max_workers_formula=1,
            worker_cap=cap,
            backend_max_parallel=parallel,
            effective_workers=1,
            low_vram_warning=vendor is not GpuVendor.CPU,
        )
    reserve_mib, reserve_source = _reserve(memory_total_mib, reserve_override_mib)
    headroom = memory_free_mib - reserve_mib
    raw = headroom // peak_mib if headroom > 0 else 0
    formula = max(1, raw)
    return GpuBudget(
        vendor=vendor,
        memory_total_mib=memory_total_mib,
        memory_free_mib=memory_free_mib,
        backend_id=backend_id,
        precision=precision,
        reserve_mib=reserve_mib,
        reserve_source=reserve_source,
        peak_worker_mib=peak_mib,
        peak_source=peak_source,
        max_workers_formula=formula,
        worker_cap=cap,
        backend_max_parallel=parallel,
        effective_workers=min(formula, cap, parallel),
        low_vram_warning=headroom < peak_mib,
    )


def admits_worker(*, memory_free_mib: int, reserve_mib: int, peak_worker_mib: int) -> bool:
    """GPU-05's spawn check: one more worker fits in the memory left after the reserve."""
    if peak_worker_mib <= 0:
        return False
    return memory_free_mib - reserve_mib >= peak_worker_mib


def _reserve(total_mib: int, override_mib: int | None) -> tuple[int, ReserveSource]:
    if override_mib is not None:
        return max(0, override_mib), "user_override"
    percent = (total_mib * _RESERVE_NUMERATOR + _RESERVE_DENOMINATOR - 1) // _RESERVE_DENOMINATOR
    return max(percent, _RESERVE_FLOOR_MIB), "default"


def _peak(
    backend_id: str,
    precision: str,
    model: str,
    *,
    override_mib: int | None,
    measured_mib: int | None,
) -> tuple[int, PeakSource]:
    if override_mib is not None:
        if override_mib <= 0:
            raise AppError(
                ErrorCode.GPU_UNAVAILABLE,
                detail={"reason": "peak_override_invalid", "backend_id": backend_id},
                message="a worker peak override must be a positive number of MiB",
            )
        return override_mib, "user_override"
    if measured_mib is not None:
        if measured_mib <= 0:
            raise AppError(
                ErrorCode.GPU_UNAVAILABLE,
                detail={"reason": "measured_peak_invalid", "backend_id": backend_id},
                message="a measured worker peak must be a positive number of MiB",
            )
        return measured_mib, "measured"
    seeded = _seed_peak(backend_id, precision, model)
    if seeded is None:
        raise AppError(
            ErrorCode.GPU_UNAVAILABLE,
            detail={"reason": "unknown_backend", "backend_id": backend_id, "precision": precision},
            message="no conservative VRAM peak is seeded for this backend",
        )
    return seeded, "table_default"


def _seed_peak(backend_id: str, precision: str, model: str) -> int | None:
    if backend_id == "fake":
        return _SEED_PEAK_MIB[("fake", "")]
    if backend_id == "qwen3_tts" and model == "1.7b" and precision == "fp16":
        return _QWEN_LARGE_MIB
    return _SEED_PEAK_MIB.get((backend_id, precision))


def _at_least_one(value: int) -> int:
    return value if value >= 1 else 1
