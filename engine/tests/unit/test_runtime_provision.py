# SPDX-License-Identifier: Apache-2.0
"""The locked runtime install, with a fake uv runner and no download."""

from __future__ import annotations

import pytest

from praelector.domain.enums import EventType, GpuVendor, RuntimeFlavour
from praelector.errors import AppError, ErrorCode
from praelector.events import EventBus
from praelector.gpu.detect import GpuDeviceInfo
from praelector.runtime.flavour import read_runtime_json
from praelector.runtime.provision import UvRequest, UvResult, lock_hash, provision

_LOCK = b'version = 1\nname = "praelector-tts"\n'


def test_install_lays_out_the_runtime_dir_and_reports_progress(tmp_path) -> None:
    seen: list[UvRequest] = []

    def runner(request: UvRequest, progress) -> UvResult:
        seen.append(request)
        (request.dest / ".venv").mkdir()
        progress({"phase": "install", "bytes": 10, "total": len(_LOCK), "log_line": "installed"})
        return UvResult(0, "installed\n", "2.12.0", "3.12.0")

    bus = EventBus()
    result = provision(
        data_dir=tmp_path,
        flavour=RuntimeFlavour.CUDA,
        lock_bytes=_LOCK,
        runner=runner,
        capability="sm_89",
        devices=(_device(GpuVendor.NVIDIA, 12288),),
        platform="linux",
        bus=bus,
    )
    digest = lock_hash(_LOCK)
    assert result.dest == tmp_path / "runtimes" / f"cuda-{digest[:16]}"
    assert (result.dest / "uv.lock").read_bytes() == _LOCK
    assert (result.dest / ".venv").is_dir()
    assert result.record.lock_hash == digest
    assert read_runtime_json(result.dest / "runtime.json") == result.record
    assert result.mismatch_reason is None
    assert seen[0].lock_path == result.dest / "uv.lock"
    phases = [event["phase"] for event in result.progress]
    assert phases == ["install", "install", "ready"]
    published = [
        event.payload["phase"] for event in bus.since(0) if event.type is EventType.RUNTIME_PROGRESS
    ]
    assert published == phases


def test_a_cuda_install_on_cpu_hardware_still_surfaces_the_mismatch(tmp_path) -> None:
    result = provision(
        data_dir=tmp_path,
        flavour=RuntimeFlavour.CUDA,
        lock_bytes=_LOCK,
        runner=lambda _request, _progress: UvResult(0, "", "2.12.0", "3.12.0"),
        capability="sm_89",
        devices=(_device(GpuVendor.CPU, None),),
        platform="linux",
    )
    assert result.mismatch_reason == "flavour_mismatch"
    assert (result.dest / "runtime.json").is_file()


def test_a_failed_runner_keeps_the_log_tail_and_writes_no_record(tmp_path) -> None:
    def runner(_request: UvRequest, _progress) -> UvResult:
        return UvResult(1, "x" * 600 + "boom", "", "")

    with pytest.raises(AppError) as excinfo:
        provision(
            data_dir=tmp_path,
            flavour=RuntimeFlavour.CPU,
            lock_bytes=_LOCK,
            runner=runner,
            capability="cpu",
            devices=(_device(GpuVendor.CPU, None),),
            platform="linux",
        )
    assert excinfo.value.code is ErrorCode.RUNTIME_NOT_PROVISIONED
    assert excinfo.value.detail["reason"] == "uv_failed"
    assert excinfo.value.detail["log_tail"].endswith("boom")
    assert len(excinfo.value.detail["log_tail"]) == 500
    digest = lock_hash(_LOCK)
    dest = tmp_path / "runtimes" / f"cpu-{digest[:16]}"
    assert (dest / "uv.lock").read_bytes() == _LOCK
    assert not (dest / "runtime.json").exists()


def _device(vendor: GpuVendor, total: int | None) -> GpuDeviceInfo:
    return GpuDeviceInfo(
        index=-1 if vendor is GpuVendor.CPU else 0,
        vendor=vendor,
        name="cpu" if vendor is GpuVendor.CPU else "card",
        memory_total_mib=total,
        memory_free_mib=total,
        available=True,
    )
