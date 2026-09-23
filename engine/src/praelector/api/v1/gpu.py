# SPDX-License-Identifier: Apache-2.0
"""GPU routes: the device list and the per-vendor probe verdict (OPENAPI_SKETCH.md §8)."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from praelector.gpu import detect
from praelector.gpu.detect import GpuDeviceInfo, GpuProbeReport, GpuVendorAvailability

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gpu"])


class GpuDevicesResponse(BaseModel):
    """The body of both GPU routes.

    ``devices`` is ordered NVIDIA, then AMD, then the CPU pseudo-device with
    ``index == -1``; GPU-04's ``device_index`` names a position in that list, so
    the order is part of the contract and never varies on the same machine.

    ``vendors`` carries one row per vendor stack, with a stable snake_case reason
    code when it could not be probed. That is what lets the UI explain "ROCm
    stack not detected" instead of showing a bare CPU-only machine and leaving the
    user to guess (GPU-07, D-16).
    """

    devices: list[GpuDeviceInfo]
    vendors: list[GpuVendorAvailability]


# Both routes are sync ``def`` on purpose: a cold probe shells out to up to three
# vendor tools at PROBE_TIMEOUT_S each. FastAPI runs a sync route in the
# threadpool, so a hung driver stalls one worker thread instead of the event loop
# that serves the shell's 5 s health poll (PLAN.md §1.6) and the WS hub.
@router.get("/gpu/devices", response_model=GpuDevicesResponse)
def gpu_devices() -> GpuDevicesResponse:
    """Every device, served from the 5 s cache when it is warm.

    A machine with no GPU answers 200 with just the CPU pseudo-device: CPU-only
    mode is a supported configuration (GPU-08), not a failure, so this route never
    raises ``gpu.unavailable``. That code belongs to the M3 budget routes, which
    have something concrete to refuse.
    """
    return _serialise(detect.probe_report())


@router.get("/gpu/probe", response_model=GpuDevicesResponse)
def gpu_probe() -> GpuDevicesResponse:
    """Force a fresh probe, bypassing the cache.

    The "rescan" behind Settings → Recording runtime: a user who has just
    installed a driver or a ROCm stack must not be shown a verdict that is up to
    5 s stale, and must not have to restart the app to get an honest one (GPU-07).
    """
    return _serialise(detect.probe_report(use_cache=False))


def _serialise(report: GpuProbeReport) -> GpuDevicesResponse:
    return GpuDevicesResponse(devices=list(report.devices), vendors=list(report.vendors))
