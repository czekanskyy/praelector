# SPDX-License-Identifier: Apache-2.0
"""Which TTS runtime flavour this machine should use (GPU-07, GPU-08, D-20).

The locked install itself is still ahead. This module only recommends
``cuda``, ``rocm`` or ``cpu`` from a probe, records that choice in
``runtime.json``, and says when the installed flavour no longer matches
the hardware.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from praelector.domain.enums import GpuVendor, RuntimeFlavour
from praelector.errors import AppError, ErrorCode
from praelector.gpu.detect import GpuDeviceInfo

#: D-20 — Windows has no supported ROCm wheel, so AMD there stays on CPU.
REASON_WINDOWS_AMD = "windows_amd_experimental"
REASON_FLAVOUR_MISMATCH = "flavour_mismatch"
_WIN32 = "win32"


@dataclass(frozen=True, slots=True)
class FlavourChoice:
    """The flavour to offer, plus a stable reason when it is not the vendor default."""

    flavour: RuntimeFlavour
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeRecord:
    """The ``runtime.json`` sidecar written after a provision (D-04)."""

    flavour: RuntimeFlavour
    torch_version: str
    lock_hash: str
    python_version: str
    capability: str


def recommend_flavour(devices: Sequence[GpuDeviceInfo], *, platform: str) -> FlavourChoice:
    """NVIDIA wins when both vendors are present: one environment, one torch."""
    nvidia = _usable(devices, GpuVendor.NVIDIA)
    amd = _usable(devices, GpuVendor.AMD)
    if nvidia:
        return FlavourChoice(RuntimeFlavour.CUDA)
    if amd and platform != _WIN32:
        return FlavourChoice(RuntimeFlavour.ROCM)
    if amd:
        return FlavourChoice(RuntimeFlavour.CPU, reason=REASON_WINDOWS_AMD)
    return FlavourChoice(RuntimeFlavour.CPU)


def mismatch_reason(
    record: RuntimeRecord,
    devices: Sequence[GpuDeviceInfo],
    *,
    platform: str,
) -> str | None:
    """``None`` when the installed flavour is still the one this machine should run."""
    if platform == _WIN32 and record.flavour is RuntimeFlavour.ROCM:
        return REASON_WINDOWS_AMD
    recommended = recommend_flavour(devices, platform=platform)
    if record.flavour is not recommended.flavour:
        return REASON_FLAVOUR_MISMATCH
    return None


def runtime_dir_name(flavour: RuntimeFlavour, lock_hash: str) -> str:
    """``<dataDir>/runtimes/<flavour>-<lockhash>/`` (D-04)."""
    cleaned = lock_hash.strip()
    if not cleaned or any(char in cleaned for char in "/\\"):
        raise AppError(
            ErrorCode.RUNTIME_NOT_PROVISIONED,
            detail={"reason": "lock_hash_invalid"},
            message="a runtime directory needs a lock hash without a path separator",
        )
    return f"{flavour.value}-{cleaned}"


def write_runtime_json(path: Path, record: RuntimeRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "flavour": record.flavour.value,
        "torch_version": record.torch_version,
        "lock_hash": record.lock_hash,
        "python_version": record.python_version,
        "capability": record.capability,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def read_runtime_json(path: Path) -> RuntimeRecord:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        flavour = RuntimeFlavour(raw["flavour"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise AppError(
            ErrorCode.RUNTIME_NOT_PROVISIONED,
            detail={"reason": "runtime_json_unreadable"},
            message="runtime.json is missing or not a flavour record",
        ) from exc
    return RuntimeRecord(
        flavour=flavour,
        torch_version=str(raw["torch_version"]),
        lock_hash=str(raw["lock_hash"]),
        python_version=str(raw["python_version"]),
        capability=str(raw["capability"]),
    )


def _usable(devices: Sequence[GpuDeviceInfo], vendor: GpuVendor) -> bool:
    return any(
        device.vendor is vendor and device.available and device.memory_total_mib is not None
        for device in devices
    )
