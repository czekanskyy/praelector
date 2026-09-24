# SPDX-License-Identifier: Apache-2.0
"""The PLAN.md §7.2 worked examples, plus the clamps around them."""

from __future__ import annotations

import pytest

from praelector.domain.enums import GpuVendor
from praelector.errors import AppError, ErrorCode
from praelector.gpu.budget import GpuBudget, admits_worker, compute_budget


def test_rtx_4070_ti_runs_two_omnivoice_workers() -> None:
    budget = _omnivoice(total=12288, free=11000)
    assert budget.reserve_mib == 2458
    assert budget.reserve_source == "default"
    assert budget.peak_worker_mib == 3500
    assert budget.peak_source == "table_default"
    assert budget.max_workers_formula == 2
    assert budget.effective_workers == 2
    assert budget.low_vram_warning is False


def test_rx_9060_xt_runs_three_omnivoice_workers() -> None:
    budget = _omnivoice(total=16384, free=15000, vendor=GpuVendor.AMD)
    assert budget.reserve_mib == 3277
    assert budget.max_workers_formula == 3
    assert budget.effective_workers == 3
    assert budget.low_vram_warning is False


def test_eight_gigabyte_card_runs_one_omnivoice_worker() -> None:
    budget = _omnivoice(total=8192, free=7200)
    assert budget.reserve_mib == 1639
    assert budget.max_workers_formula == 1
    assert budget.effective_workers == 1
    assert budget.low_vram_warning is False


def test_card_that_cannot_hold_one_worker_still_starts_one_and_warns() -> None:
    budget = _omnivoice(total=8192, free=7200, model="1.7b", backend_id="qwen3_tts")
    assert budget.peak_worker_mib == 7000
    assert budget.max_workers_formula == 1
    assert budget.effective_workers == 1
    assert budget.low_vram_warning is True
    assert (
        admits_worker(
            memory_free_mib=7200,
            reserve_mib=budget.reserve_mib,
            peak_worker_mib=7000,
        )
        is False
    )


def test_worker_cap_only_clamps_downward() -> None:
    budget = _omnivoice(total=16384, free=15000, worker_cap=2, backend_max_parallel=4)
    assert budget.max_workers_formula == 3
    assert budget.effective_workers == 2


def test_cpu_is_one_worker_without_a_vram_warning() -> None:
    budget = compute_budget(
        vendor=GpuVendor.CPU,
        memory_total_mib=None,
        memory_free_mib=None,
        backend_id="omnivoice",
        precision="fp16",
        worker_cap=4,
        backend_max_parallel=4,
    )
    assert budget.effective_workers == 1
    assert budget.max_workers_formula == 1
    assert budget.low_vram_warning is False
    assert budget.reserve_mib == 0


def test_user_overrides_replace_the_seeded_reserve_and_peak() -> None:
    budget = _omnivoice(total=12288, free=11000, reserve_override_mib=4000, peak_override_mib=2000)
    assert budget.reserve_mib == 4000
    assert budget.reserve_source == "user_override"
    assert budget.peak_worker_mib == 2000
    assert budget.peak_source == "user_override"
    assert budget.max_workers_formula == 3


def test_a_measured_peak_wins_over_the_seed_until_the_user_overrides_it() -> None:
    measured = _omnivoice(total=12288, free=11000, measured_peak_mib=2800)
    assert measured.peak_worker_mib == 2800
    assert measured.peak_source == "measured"
    overridden = _omnivoice(
        total=12288,
        free=11000,
        measured_peak_mib=2800,
        peak_override_mib=2000,
    )
    assert overridden.peak_source == "user_override"
    assert overridden.peak_worker_mib == 2000


def test_unknown_backend_is_an_error() -> None:
    with pytest.raises(AppError) as excinfo:
        _omnivoice(total=12288, free=11000, backend_id="missing")
    assert excinfo.value.code is ErrorCode.GPU_UNAVAILABLE
    assert excinfo.value.detail["reason"] == "unknown_backend"


def test_fake_backend_uses_the_tiny_seed() -> None:
    budget = compute_budget(
        vendor=GpuVendor.NVIDIA,
        memory_total_mib=8192,
        memory_free_mib=7200,
        backend_id="fake",
        precision="",
        worker_cap=4,
        backend_max_parallel=4,
    )
    assert budget.peak_worker_mib == 64
    assert budget.effective_workers == 4


def _omnivoice(
    *,
    total: int,
    free: int,
    vendor: GpuVendor = GpuVendor.NVIDIA,
    worker_cap: int = 4,
    backend_max_parallel: int = 4,
    backend_id: str = "omnivoice",
    model: str = "0.6b",
    reserve_override_mib: int | None = None,
    peak_override_mib: int | None = None,
    measured_peak_mib: int | None = None,
) -> GpuBudget:
    return compute_budget(
        vendor=vendor,
        memory_total_mib=total,
        memory_free_mib=free,
        backend_id=backend_id,
        precision="fp16",
        worker_cap=worker_cap,
        backend_max_parallel=backend_max_parallel,
        reserve_override_mib=reserve_override_mib,
        peak_override_mib=peak_override_mib,
        measured_peak_mib=measured_peak_mib,
        model=model,
    )
