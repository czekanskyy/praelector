# SPDX-License-Identifier: Apache-2.0
"""Locked TTS runtime install (D-04, GPU-07).

The flavour choice and ``runtime.json`` mismatch live in
:mod:`praelector.runtime.flavour`. This module only runs a ``uv`` install
into ``<dataDir>/runtimes/<flavour>-<lockhash>/`` and reports progress.
The runner is injected so a test never downloads a wheel.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from praelector.domain.enums import EventType, RuntimeFlavour
from praelector.errors import AppError, ErrorCode
from praelector.events import EventBus
from praelector.gpu.detect import GpuDeviceInfo
from praelector.runtime.flavour import (
    RuntimeRecord,
    mismatch_reason,
    runtime_dir_name,
    write_runtime_json,
)

#: Directory names use this many hex characters of the lock sha256.
_HASH_LEN = 16
_LOG_TAIL = 500

Progress = Callable[[dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class UvRequest:
    """What the bundled ``uv`` is asked to install. ``lock_path`` is already on disk."""

    dest: Path
    lock_path: Path
    flavour: RuntimeFlavour


@dataclass(frozen=True, slots=True)
class UvResult:
    """The runner's outcome. Versions are what it actually installed."""

    returncode: int
    log: str
    torch_version: str
    python_version: str


UvRunner = Callable[[UvRequest, Progress], UvResult]


@dataclass(frozen=True, slots=True)
class ProvisionResult:
    """A finished install. ``mismatch_reason`` is set when the flavour no longer fits."""

    dest: Path
    record: RuntimeRecord
    mismatch_reason: str | None
    progress: tuple[dict[str, object], ...]


def lock_hash(lock_bytes: bytes) -> str:
    """sha256 of the committed lock, hex. The directory uses the first 16 characters."""
    return hashlib.sha256(lock_bytes).hexdigest()


def provision(
    *,
    data_dir: Path,
    flavour: RuntimeFlavour,
    lock_bytes: bytes,
    runner: UvRunner,
    capability: str,
    devices: Sequence[GpuDeviceInfo],
    platform: str,
    bus: EventBus | None = None,
) -> ProvisionResult:
    """Install ``lock_bytes`` for ``flavour`` and write ``runtime.json``.

    ``runner`` performs the ``uv`` work. A non-zero exit leaves no
    ``runtime.json`` and raises ``runtime.not_provisioned`` with the log tail.
    """
    digest = lock_hash(lock_bytes)
    dest = data_dir / "runtimes" / runtime_dir_name(flavour, digest[:_HASH_LEN])
    dest.mkdir(parents=True, exist_ok=True)
    lock_path = dest / "uv.lock"
    lock_path.write_bytes(lock_bytes)
    events: list[dict[str, object]] = []

    def emit(payload: dict[str, object]) -> None:
        body = {"flavour": flavour.value, **payload}
        events.append(body)
        if bus is not None:
            bus.publish(EventType.RUNTIME_PROGRESS, body)

    emit({"phase": "install", "bytes": 0, "total": len(lock_bytes)})
    result = runner(UvRequest(dest=dest, lock_path=lock_path, flavour=flavour), emit)
    if result.returncode != 0:
        tail = result.log[-_LOG_TAIL:]
        emit({"phase": "failed", "log_line": tail})
        raise AppError(
            ErrorCode.RUNTIME_NOT_PROVISIONED,
            detail={"reason": "uv_failed", "log_tail": tail, "flavour": flavour.value},
            message="the locked uv install failed",
        )
    record = RuntimeRecord(
        flavour=flavour,
        torch_version=result.torch_version,
        lock_hash=digest,
        python_version=result.python_version,
        capability=capability,
    )
    write_runtime_json(dest / "runtime.json", record)
    emit({"phase": "ready"})
    return ProvisionResult(
        dest=dest,
        record=record,
        mismatch_reason=mismatch_reason(record, devices, platform=platform),
        progress=tuple(events),
    )
