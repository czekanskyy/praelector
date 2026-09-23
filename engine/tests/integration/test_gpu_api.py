# SPDX-License-Identifier: Apache-2.0
"""The GPU routes end to end: auth, ordering, and a machine with no GPU.

The probe itself is covered by ``tests/unit/test_gpu_detect.py``; these tests are
about the HTTP contract the UI depends on (GPU-06, GPU-07, GPU-08).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from praelector.domain.enums import GpuVendor
from praelector.gpu import detect
from praelector.gpu.detect import GpuDeviceInfo, GpuProbeReport, GpuVendorAvailability

CPU_ONLY = GpuProbeReport(
    devices=(GpuDeviceInfo(index=-1, vendor=GpuVendor.CPU, name="cpu", available=True),),
    vendors=(
        GpuVendorAvailability(
            vendor=GpuVendor.NVIDIA, available=False, reason="nvidia_smi_missing"
        ),
        GpuVendorAvailability(vendor=GpuVendor.AMD, available=False, reason="rocm_smi_missing"),
    ),
)

HYBRID = GpuProbeReport(
    devices=(
        GpuDeviceInfo(
            index=0,
            vendor=GpuVendor.NVIDIA,
            name="NVIDIA GeForce RTX 4070 Ti",
            driver="580.65.06",
            memory_total_mib=12288,
            memory_free_mib=11000,
            available=True,
        ),
        GpuDeviceInfo(
            index=1,
            vendor=GpuVendor.AMD,
            name="RX 9060 XT",
            memory_total_mib=16384,
            memory_free_mib=15000,
            available=True,
        ),
        GpuDeviceInfo(index=-1, vendor=GpuVendor.CPU, name="cpu", available=True),
    ),
    vendors=(
        GpuVendorAvailability(vendor=GpuVendor.NVIDIA, available=True),
        GpuVendorAvailability(vendor=GpuVendor.AMD, available=True),
    ),
)


@pytest.fixture
def stub_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the route away from real vendor tools: CI has no GPU."""
    monkeypatch.setattr(detect, "probe_report", lambda **_: CPU_ONLY)


def test_devices_needs_the_token(client: TestClient, stub_probe: None) -> None:
    assert client.get("/v1/gpu/devices").status_code == 401


def test_a_cpu_only_machine_is_a_success_not_an_error(
    client: TestClient, auth: dict[str, str], stub_probe: None
) -> None:
    """CPU-only is a supported configuration (GPU-08), so this must be 200."""
    response = client.get("/v1/gpu/devices", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert [device["vendor"] for device in body["devices"]] == ["cpu"]
    assert body["devices"][0]["index"] == -1
    assert body["devices"][0]["memory_total_mib"] is None


def test_a_missing_vendor_stack_is_explained_not_hidden(
    client: TestClient, auth: dict[str, str], stub_probe: None
) -> None:
    """GPU-07: the UI has to be able to say "ROCm stack not detected"."""
    vendors = {
        row["vendor"]: row for row in client.get("/v1/gpu/devices", headers=auth).json()["vendors"]
    }
    assert vendors["nvidia"] == {
        "vendor": "nvidia",
        "available": False,
        "reason": "nvidia_smi_missing",
    }
    assert vendors["amd"]["reason"] == "rocm_smi_missing"


def test_the_device_order_is_part_of_the_contract(
    client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """GPU-04's ``device_index`` names a position, so the order cannot drift."""
    monkeypatch.setattr(detect, "probe_report", lambda **_: HYBRID)
    devices = client.get("/v1/gpu/devices", headers=auth).json()["devices"]
    assert [device["vendor"] for device in devices] == ["nvidia", "amd", "cpu"]
    assert [device["index"] for device in devices] == [0, 1, -1]
    assert devices[0]["memory_free_mib"] == 11000


def test_the_probe_route_bypasses_the_cache(
    client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []

    def record(**kwargs: object) -> GpuProbeReport:
        calls.append(bool(kwargs.get("use_cache", True)))
        return CPU_ONLY

    monkeypatch.setattr(detect, "probe_report", record)
    client.get("/v1/gpu/devices", headers=auth)
    client.get("/v1/gpu/probe", headers=auth)
    assert calls == [True, False]


def test_a_real_probe_does_not_crash_this_machine(client: TestClient, auth: dict[str, str]) -> None:
    """No stub: whatever this machine has, the route must answer 200."""
    response = client.get("/v1/gpu/probe", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["devices"], "the CPU pseudo-device is always present"
    assert body["devices"][-1]["vendor"] == "cpu"


@pytest.mark.gpu
def test_a_real_gpu_is_reported_with_vram(client: TestClient, auth: dict[str, str]) -> None:
    """Runs only on the two reference machines (RTX 4070 Ti, RX 9060 XT)."""
    devices = client.get("/v1/gpu/probe", headers=auth).json()["devices"]
    accelerators = [d for d in devices if d["vendor"] != "cpu"]
    assert accelerators, "expected a discrete GPU on a reference machine"
    for device in accelerators:
        assert device["available"] is True
        assert device["memory_total_mib"] and device["memory_total_mib"] >= 8192
        assert device["memory_free_mib"] is not None
