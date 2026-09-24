# SPDX-License-Identifier: Apache-2.0
"""GPU device detection, budget math and the VRAM monitor (PLAN.md §1.3).

Detection (GPU-01, GPU-02, GPU-07, GPU-08), the worker-count formula
(GPU-03, GPU-04) and the 1 Hz admissions monitor (GPU-05) are in place.
The scheduler that consumes the monitor is still ahead.

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
