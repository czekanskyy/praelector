# SPDX-License-Identifier: Apache-2.0
"""Flavour recommendation and runtime.json mismatch, with no download."""

from __future__ import annotations

from pathlib import Path

import pytest

from praelector.domain.enums import GpuVendor, RuntimeFlavour
from praelector.errors import AppError, ErrorCode
from praelector.gpu.detect import GpuDeviceInfo
from praelector.runtime.flavour import (
    REASON_FLAVOUR_MISMATCH,
    REASON_WINDOWS_AMD,
    RuntimeRecord,
    mismatch_reason,
    read_runtime_json,
    recommend_flavour,
    runtime_dir_name,
    write_runtime_json,
)


def test_nvidia_recommends_cuda_even_when_amd_is_also_present() -> None:
    choice = recommend_flavour(
        (_device(GpuVendor.NVIDIA, 12288), _device(GpuVendor.AMD, 16384)),
        platform="linux",
    )
    assert choice.flavour is RuntimeFlavour.CUDA
    assert choice.reason is None


def test_linux_amd_recommends_rocm() -> None:
    choice = recommend_flavour((_device(GpuVendor.AMD, 16384),), platform="linux")
    assert choice.flavour is RuntimeFlavour.ROCM


def test_windows_amd_recommends_cpu_with_the_experimental_reason() -> None:
    choice = recommend_flavour((_device(GpuVendor.AMD, 16384),), platform="win32")
    assert choice.flavour is RuntimeFlavour.CPU
    assert choice.reason == REASON_WINDOWS_AMD


def test_no_gpu_recommends_cpu_without_a_warning() -> None:
    choice = recommend_flavour((_device(GpuVendor.CPU, None),), platform="linux")
    assert choice.flavour is RuntimeFlavour.CPU
    assert choice.reason is None


def test_a_cuda_record_on_cpu_hardware_is_a_flavour_mismatch() -> None:
    record = _record(RuntimeFlavour.CUDA)
    reason = mismatch_reason(record, (_device(GpuVendor.CPU, None),), platform="linux")
    assert reason == REASON_FLAVOUR_MISMATCH


def test_a_rocm_record_on_windows_is_explained_before_the_generic_mismatch() -> None:
    record = _record(RuntimeFlavour.ROCM)
    reason = mismatch_reason(record, (_device(GpuVendor.AMD, 16384),), platform="win32")
    assert reason == REASON_WINDOWS_AMD


def test_runtime_json_round_trip_and_directory_name(tmp_path: Path) -> None:
    record = _record(RuntimeFlavour.CUDA, capability="sm_89")
    path = tmp_path / "runtime.json"
    write_runtime_json(path, record)
    assert read_runtime_json(path) == record
    assert runtime_dir_name(RuntimeFlavour.CUDA, "abc123") == "cuda-abc123"


def test_a_broken_runtime_json_is_not_provisioned(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(AppError) as excinfo:
        read_runtime_json(path)
    assert excinfo.value.code is ErrorCode.RUNTIME_NOT_PROVISIONED


def _device(vendor: GpuVendor, total: int | None) -> GpuDeviceInfo:
    return GpuDeviceInfo(
        index=0 if vendor is not GpuVendor.CPU else -1,
        vendor=vendor,
        name="card" if vendor is not GpuVendor.CPU else "cpu",
        memory_total_mib=total,
        memory_free_mib=total,
        available=True,
    )


def _record(flavour: RuntimeFlavour, capability: str = "gfx1200") -> RuntimeRecord:
    return RuntimeRecord(
        flavour=flavour,
        torch_version="2.12.0",
        lock_hash="abc123",
        python_version="3.12.0",
        capability=capability,
    )
