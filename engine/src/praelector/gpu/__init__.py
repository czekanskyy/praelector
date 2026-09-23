# SPDX-License-Identifier: Apache-2.0
"""GPU device detection, budget math and the VRAM monitor (PLAN.md §1.3).

This PR delivers detection only (GPU-01, GPU-02's sampling primitive, GPU-07,
GPU-08). ``budget.py``, ``monitor.py`` and ``vram_table.py`` — GPU-03, GPU-04 and
GPU-05 — arrive in M3, because nothing can consume them yet.

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
