# SPDX-License-Identifier: Apache-2.0
"""GPU device detection, budget math and the VRAM monitor (PLAN.md §1.3).

Detection (GPU-01, GPU-02's sampling primitive, GPU-07, GPU-08) and the
worker-count formula (GPU-03, GPU-04) are in place. ``monitor.py`` — the 1 Hz
sampler and the admissions pause — is still ahead, because nothing consumes
it until the scheduler exists.

Routers must call :mod:`praelector.gpu.detect` through the module
(``detect.probe_report()``) rather than importing the function, so a test can
monkeypatch it and so the 5 s cache stays behind exactly one call site.
"""

from __future__ import annotations

from praelector.gpu import detect
from praelector.gpu.detect import (
    CPU_DEVICE_INDEX,
    CPU_DEVICE_NAME,
    CommandResult,
    GpuDeviceInfo,
    GpuProbeReport,
    GpuVendorAvailability,
    detect_devices,
    invalidate_cache,
    probe_report,
)

__all__ = [
    "CPU_DEVICE_INDEX",
    "CPU_DEVICE_NAME",
    "CommandResult",
    "GpuDeviceInfo",
    "GpuProbeReport",
    "GpuVendorAvailability",
    "detect",
    "detect_devices",
    "invalidate_cache",
    "probe_report",
]
