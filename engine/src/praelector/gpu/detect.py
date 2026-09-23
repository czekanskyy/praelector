# SPDX-License-Identifier: Apache-2.0
"""GPU device detection (GPU-01, GPU-02, GPU-07, GPU-08).

PLAN.md §7.1: shell out to the vendor tools, parse, cache for 5 s. Three rules
shape this module.

1. **A machine with no GPU is the normal case.** Every probe swallows a missing
   binary, a non-zero exit, a timeout and unparseable output, and returns an
   empty list plus a structured reason. CPU-only mode (GPU-08) is a supported
   configuration and a broken driver must never take the engine down.
2. **Parsing is pure.** :func:`parse_nvidia_smi`, :func:`parse_amd_smi` and
   :func:`parse_sysfs_vram` take text or a path and return devices; the
   subprocess call sits in :func:`run_probe_command` above them. That split is
   what lets hostile output be tested on a CI box with no GPU at all.
3. **Nothing here is prose.** A vendor stack that cannot be probed is reported
   with a stable snake_case reason code that ``apps/ui`` localises (D-16).

Ordering is part of the contract: NVIDIA devices first, carrying the indices
``nvidia-smi`` reported, then AMD devices, then the CPU pseudo-device with
``index == -1`` last. GPU-04's ``device_index`` and GPU-06's device picker both
address that list, so indices are unique within a response and stable between
calls on the same machine.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from pydantic import BaseModel, ConfigDict

from praelector.domain.enums import GpuVendor

logger = logging.getLogger(__name__)

# PLAN.md §7.1's optional nvidia-ml-py fast path for the 1 Hz in-job sampler is
# deliberately absent here: it belongs to gpu/monitor.py in M3, and wiring it up
# now would be dead code.

#: PLAN.md §7.1 — the device picker and (from M4) the scheduler both ask, and
#: spawning a vendor tool more often than this is pure waste.
CACHE_TTL_S: Final = 5.0

#: Long enough for an idle driver query, short enough that a hung driver cannot
#: stall the loopback API for long (the shell polls ``/v1/health`` every 5 s and
#: restarts the engine after three failures, PLAN.md §1.6).
PROBE_TIMEOUT_S: Final = 2.0

#: Bound on reaping a probe that had to be killed. Without it the "timeout" is not
#: a timeout: see :func:`run_probe_command`.
KILL_GRACE_S: Final = 1.0

_IS_WINDOWS: bool = sys.platform == "win32"

#: A desktop app must not flash a console window every time it asks about VRAM.
#: ``getattr`` keeps this importable on POSIX, where the flag does not exist.
_CREATE_NO_WINDOW: Final = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

#: Reserved for the CPU pseudo-device so it can never be mistaken for a real
#: ordinal (GPU-04's ``device_index`` addresses the device list).
CPU_DEVICE_INDEX: Final = -1

#: ``platform.processor()`` is empty on Linux and a CPUID string on Windows, and
#: a marketing name is prose the UI cannot localise (D-16). The CPU device
#: carries a stable token instead; the UI keys off ``vendor == "cpu"``.
CPU_DEVICE_NAME: Final = "cpu"

#: Injected into :func:`parse_sysfs_vram` so the AMD sysfs fallback is testable
#: with a ``tmp_path`` tree, on Windows and in CI, where ``/sys`` does not exist.
DEFAULT_SYSFS_ROOT: Final = Path("/sys")

_BYTES_PER_MIB: Final = 1024 * 1024
_NVIDIA_FIELD_COUNT: Final = 5

_NVIDIA_BINARY: Final = "nvidia-smi"
#: ``nounits`` makes the two memory fields plain integers in MiB (PLAN.md §7.1).
_NVIDIA_QUERY: Final = (
    "--query-gpu=index,name,memory.total,memory.free,driver_version",
    "--format=csv,noheader,nounits",
)
_AMD_SMI_BINARY: Final = "amd-smi"
_ROCM_SMI_BINARY: Final = "rocm-smi"
_AMD_SMI_QUERY: Final = (_AMD_SMI_BINARY, "metric", "--mem", "--json")
_ROCM_SMI_QUERY: Final = (_ROCM_SMI_BINARY, "--showmeminfo", "vram", "--json")

# Reason codes are a published contract: one stable snake_case token per failure
# so ``apps/ui`` can localise it (D-16, GPU-07). Never a sentence.
REASON_NVIDIA_SMI_MISSING: Final = "nvidia_smi_missing"
REASON_AMD_SMI_MISSING: Final = "amd_smi_missing"
REASON_ROCM_SMI_MISSING: Final = "rocm_smi_missing"
REASON_SYSFS_VRAM_MISSING: Final = "sysfs_vram_missing"
REASON_PROBE_TIMEOUT: Final = "probe_timeout"
REASON_PROBE_FAILED: Final = "probe_failed"
REASON_PARSE_FAILED: Final = "parse_failed"
REASON_NO_DEVICES: Final = "no_devices"
REASON_MEMORY_UNREADABLE: Final = "memory_unreadable"

#: Which reason wins when every AMD fallback failed. A tool that exists but
#: misbehaved is more actionable than one that is absent, so the hard failures
#: come first; ``rocm_smi_missing`` is PLAN.md §7.1's "no ROCm stack" code.
_AMD_REASON_PRECEDENCE: Final = (
    REASON_PROBE_TIMEOUT,
    REASON_PROBE_FAILED,
    REASON_PARSE_FAILED,
    REASON_NO_DEVICES,
    REASON_ROCM_SMI_MISSING,
    REASON_AMD_SMI_MISSING,
    REASON_SYSFS_VRAM_MISSING,
)

#: Outcomes of :func:`run_probe_command` that mean "the tool never produced
#: output", as opposed to "it ran and returned something".
OUTCOME_OK: Final = "ok"
OUTCOME_MISSING: Final = "missing"
OUTCOME_TIMEOUT: Final = "timeout"
OUTCOME_SPAWN_FAILED: Final = "spawn_failed"

#: nvidia-smi answers an unsupported query with a bracketed token instead of a
#: number; on a vGPU, under MIG or with restricted permissions every memory
#: field can come back as one of these.
_PLACEHOLDERS: Final = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "[n/a]",
        "not supported",
        "[not supported]",
        "[insufficient permissions]",
        "[not permitted]",
        "[code error]",
    }
)

#: AMD key names, normalised (lowercase, alphanumerics only) and in preference
#: order: an explicitly unitised key beats a bare one, which matters because
#: ``amd-smi`` mixes ``"% used"`` (a percentage!) with ``"used memory (B)"`` in
#: the same object. Percentages are dropped before this lookup happens.
_TOTAL_KEYS: Final = (
    "vramtotalmemoryb",
    "totalmemoryb",
    "vramtotalbytes",
    "vramtotalmib",
    "memtotalmib",
    "vramtotalmemory",
    "totalmemory",
    "vramtotal",
    "memtotal",
    "vramsize",
    "total",
)
_USED_KEYS: Final = (
    "vramtotalusedmemoryb",
    "usedmemoryb",
    "vramusedbytes",
    "vramusedmib",
    "memusedmib",
    "vramtotalusedmemory",
    "usedmemory",
    "vramused",
    "memused",
    "vramusage",
    "used",
)
_FREE_KEYS: Final = (
    "vramfreememoryb",
    "freememoryb",
    "vramfreebytes",
    "vramfreemib",
    "memfreemib",
    "vramfreememory",
    "freememory",
    "vramfree",
    "memfree",
    "free",
)
_ALL_MEMORY_KEYS: Final = frozenset(_TOTAL_KEYS) | frozenset(_USED_KEYS) | frozenset(_FREE_KEYS)

#: Product-name keys, when the tool happens to emit one (``amd-smi static``
#: does; ``amd-smi metric --mem`` does not).
_NAME_KEYS: Final = frozenset(
    {"sku", "series", "model", "marketname", "productname", "cardname", "gpuname", "asicname"}
)
_DRIVER_KEYS: Final = frozenset({"driverversion", "driver", "kfdversion"})
#: Keys a list-of-records payload uses to identify the card it describes.
_CARD_KEYS: Final = ("card", "cardid", "cardpath", "path", "gpuid", "bdf", "pcislotname")

_SYSFS_CARD_RE: Final = re.compile(r"card(?P<ordinal>\d+)")
_SYSFS_VRAM_TOTAL: Final = "mem_info_vram_total"
_SYSFS_VRAM_USED: Final = "mem_info_vram_used"


class GpuDeviceInfo(BaseModel):
    """One device in ``GET /v1/gpu/devices`` (OPENAPI_SKETCH.md §8).

    Frozen: the same instance is handed to every caller of the 5 s cache, and the
    M4 scheduler reads it from worker threads.

    ``memory_free_mib`` is reported exactly as the driver reported it. A driver
    that claims more free than total VRAM is broken, and clamping here would hide
    that from the bug report GPU-06 exists to support; the budget math
    (PLAN.md §7.2) is what has to cope with it.
    """

    model_config = ConfigDict(frozen=True)

    #: Position in the response, which is what GPU-04's ``device_index`` names.
    #: ``-1`` for the CPU pseudo-device, never a vendor ordinal for it.
    index: int
    vendor: GpuVendor
    name: str
    driver: str | None = None
    #: MiB, or ``None`` when the driver would not say (always ``None`` for CPU).
    memory_total_mib: int | None = None
    memory_free_mib: int | None = None
    #: False when the device cannot be budgeted, i.e. its total VRAM is unknown.
    #: The CPU device is always available: it is the GPU-08 slow path, not an error.
    available: bool
    #: Stable snake_case reason code when ``available`` is False (D-16).
    reason: str | None = None


class GpuVendorAvailability(BaseModel):
    """Whether one vendor stack could be probed, and if not, why (GPU-07).

    This is what lets the UI say "ROCm stack not detected" next to a CPU-only
    machine instead of showing an empty list and shrugging.
    """

    model_config = ConfigDict(frozen=True)

    vendor: GpuVendor
    available: bool
    reason: str | None = None


class GpuProbeReport(BaseModel):
    """Everything one probe round learned: the devices and the per-vendor verdict."""

    model_config = ConfigDict(frozen=True)

    devices: tuple[GpuDeviceInfo, ...] = ()
    vendors: tuple[GpuVendorAvailability, ...] = ()


@dataclass(frozen=True, slots=True)
class CommandResult:
    """One vendor-tool invocation.

    ``outcome`` distinguishes "the tool never ran" from "it ran and answered",
    which map to different reason codes: a missing binary is a normal
    configuration (GPU-08), a non-zero exit is a fault worth reporting.
    """

    outcome: str = OUTCOME_OK
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class _Memory:
    total_mib: int | None
    free_mib: int | None


@dataclass(frozen=True, slots=True)
class _ProbeOutcome:
    devices: list[GpuDeviceInfo]
    #: ``None`` when the vendor stack answered with at least one usable device.
    reason: str | None


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: float
    report: GpuProbeReport


_cache_lock = threading.Lock()
_probe_lock = threading.Lock()
_cached: _CacheEntry | None = None


def run_probe_command(argv: Sequence[str]) -> CommandResult:
    """Run one vendor tool and never raise, within a real wall-clock bound.

    ``argv[0]`` is resolved through ``PATH`` because these binaries live in
    ``System32`` on Windows and in ``/usr/bin`` (or an AMD install dir) on Linux;
    hardcoding either breaks the other (PLAN.md §2). Nothing in ``argv`` is
    user-controlled and ``shell`` is never used, so there is no injection surface.

    ``subprocess.run(timeout=…)`` is not enough here, and that was observed rather
    than theorised: Windows ships an ``amd-smi.exe`` in ``System32`` that never
    returns on a machine with no AMD GPU. ``run`` kills the child when the timeout
    fires and then reaps it, but a descendant still holding the inherited pipe
    handle makes that reap block forever — a 2 s timeout hung the calling thread
    indefinitely, which in a served route means a threadpool worker gone for good.
    Killing the whole tree and bounding the reap is what makes
    :data:`PROBE_TIMEOUT_S` mean something. ``stdin`` is ``DEVNULL`` for the same
    class of reason: a tool that waits for input must not be able to stall us.
    """
    if not argv:
        return CommandResult(outcome=OUTCOME_SPAWN_FAILED, stderr="empty argv")
    if shutil.which(argv[0]) is None:
        return CommandResult(outcome=OUTCOME_MISSING)

    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # FileNotFoundError lands here too: the binary can vanish between the
        # PATH lookup above and CreateProcess/execvp.
        logger.debug("gpu probe could not run", extra={"probe": argv[0], "error": str(exc)})
        return CommandResult(outcome=OUTCOME_SPAWN_FAILED, stderr=str(exc))

    try:
        stdout, stderr = process.communicate(timeout=PROBE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        logger.warning(
            "gpu probe timed out",
            extra={"probe": argv[0], "timeout_s": PROBE_TIMEOUT_S},
        )
        _kill_tree(process)
        try:
            process.communicate(timeout=KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            logger.warning("gpu probe ignored being killed", extra={"probe": argv[0]})
            _abandon(process)
        except (OSError, ValueError, subprocess.SubprocessError):
            _abandon(process)
        return CommandResult(outcome=OUTCOME_TIMEOUT)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.debug(
            "gpu probe output could not be read", extra={"probe": argv[0], "error": str(exc)}
        )
        _kill_tree(process)
        _abandon(process)
        return CommandResult(outcome=OUTCOME_SPAWN_FAILED, stderr=str(exc))

    return CommandResult(
        returncode=process.returncode or 0,
        stdout=stdout or "",
        stderr=stderr or "",
    )


def _kill_tree(process: subprocess.Popen[str]) -> None:
    """Kill the child and, on Windows, everything it spawned."""
    if _IS_WINDOWS:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=KILL_GRACE_S,
                check=False,
                creationflags=_CREATE_NO_WINDOW,
            )
    with contextlib.suppress(OSError):
        process.kill()


def _abandon(process: subprocess.Popen[str]) -> None:
    """Drop our pipe handles without waiting, for a child that refuses to die."""
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is None:
            continue
        with contextlib.suppress(OSError, ValueError):
            stream.close()


def parse_nvidia_smi(stdout: str) -> list[GpuDeviceInfo]:
    """Parse ``nvidia-smi`` CSV output into devices. Pure: no subprocess, no state.

    The device name is the only field that may itself contain a comma
    (``NVIDIA GeForce RTX 4070 Ti, 12GB`` is real output), so the line is split
    on ``,`` and read back from both ends: field 0 is the index, the last three
    are ``memory.total``, ``memory.free`` and ``driver_version``, and everything
    in between is the name. A line whose first field is not an integer index is
    dropped — that is an unsuppressed header, not a device. Rows are never
    invented: a line yields at most one device, a malformed line yields none.
    """
    devices: list[GpuDeviceInfo] = []
    for line in stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < _NVIDIA_FIELD_COUNT:
            continue
        index = _int_from_text(fields[0])
        if index is None or index < 0:
            # No index, or a negative one: CPU_DEVICE_INDEX is reserved.
            continue
        total = _int_from_text(fields[-3])
        devices.append(
            GpuDeviceInfo(
                index=index,
                vendor=GpuVendor.NVIDIA,
                name=_text_or(", ".join(fields[1:-3]).strip(), None) or "unknown",
                driver=_text_or(fields[-1], None),
                memory_total_mib=total,
                memory_free_mib=_int_from_text(fields[-2]),
                available=total is not None,
                reason=None if total is not None else REASON_MEMORY_UNREADABLE,
            )
        )
    return devices


def parse_amd_smi(payload: str) -> list[GpuDeviceInfo]:
    """Parse ``amd-smi metric --mem --json`` or ``rocm-smi --showmeminfo vram --json``.

    Pure and deliberately tolerant: neither tool's JSON is a stable contract and
    both change shape between ROCm releases. Accepted payloads:

    1. **dict keyed by card** — ``{"card0": {...}}`` (amd-smi) or
       ``{"/sys/devices/pci0000:00/0000:03:00.0": {...}, "system": {...}}``
       (rocm-smi). Each value that carries VRAM figures becomes one device; a
       value that does not (rocm-smi's ``system`` block) is skipped.
    2. **list of records** — ``[{"card": "card0", ...}, ...]``, which is what
       newer ``amd-smi`` builds emit.
    3. **one bare record** — ``{"vram_total": 17163091968, ...}``, recognised by
       a memory key at its own level.

    Inside a record, memory figures are found at the top level *or* one level
    down (amd-smi nests them under ``Vram``). Keys are matched after lowercasing
    and dropping every non-alphanumeric character, so ``VRAM Total Memory (B)``,
    ``vram_total_memory_b`` and ``mem_total`` all resolve, and an explicitly
    unitised key beats a bare ``total``/``used``/``free``. Keys containing ``%``
    are ignored, because ``"% free": "100"`` next to ``"free memory (B)"`` would
    otherwise read as 100 MiB. A key with no unit is bytes — that is what
    amd-smi, rocm-smi and the sysfs attributes all report. ``free`` falls back to
    ``total - used`` when the tool omits it.

    Anything else — malformed JSON, a bare string, a number, an empty object —
    yields an empty list rather than an exception (GPU-08).
    """
    try:
        decoded: object = json.loads(payload)
    except ValueError:
        return []
    devices: list[GpuDeviceInfo] = []
    for key, record in _amd_records(decoded):
        device = _amd_device(key, record, len(devices))
        if device is not None:
            devices.append(device)
    return devices


def parse_sysfs_vram(sysfs_root: Path) -> list[GpuDeviceInfo]:
    """Read VRAM from the amdgpu sysfs attributes: the last AMD fallback.

    Expects ``<sysfs_root>/class/drm/card<N>/device/mem_info_vram_{total,used}``
    in bytes; ``free`` is ``total - used`` because the kernel exposes no free
    attribute. Connector directories (``card0-DP-1``) are not cards and are
    ignored, and a card without ``mem_info_vram_total`` (an Intel or nouveau
    card sharing the box) is skipped rather than reported as a zero-VRAM AMD GPU.
    sysfs carries no product name, so the device is named after the card id.
    """
    try:
        children = list((sysfs_root / "class" / "drm").iterdir())
    except OSError:
        return []
    cards: list[tuple[int, Path]] = []
    for child in children:
        match = _SYSFS_CARD_RE.fullmatch(child.name)
        if match is None:
            continue
        try:
            if not child.is_dir():
                continue
        except OSError:  # pragma: no cover - a racing udev rename, not a real path
            continue
        cards.append((int(match.group("ordinal")), child))

    devices: list[GpuDeviceInfo] = []
    for ordinal, card in sorted(cards):
        device_dir = card / "device"
        total = _read_int_file(device_dir / _SYSFS_VRAM_TOTAL)
        # A negative or unreadable total is not a VRAM figure. Skipping the card
        # is honest; reporting a zero-VRAM AMD GPU would put a device the user
        # can select into the picker (GPU-06).
        if total is None or total < 0:
            continue
        used = _read_int_file(device_dir / _SYSFS_VRAM_USED)
        if used is not None and used < 0:
            used = None
        devices.append(
            GpuDeviceInfo(
                index=ordinal,
                vendor=GpuVendor.AMD,
                name=card.name,
                driver=_read_sysfs_driver(device_dir),
                memory_total_mib=total // _BYTES_PER_MIB,
                memory_free_mib=None if used is None else (total - used) // _BYTES_PER_MIB,
                available=True,
                reason=None,
            )
        )
    return devices


def cpu_device() -> GpuDeviceInfo:
    """The always-present CPU pseudo-device (PLAN.md §7.1, GPU-08)."""
    return GpuDeviceInfo(
        index=CPU_DEVICE_INDEX,
        vendor=GpuVendor.CPU,
        name=CPU_DEVICE_NAME,
        driver=None,
        memory_total_mib=None,
        memory_free_mib=None,
        available=True,
        reason=None,
    )


def probe_nvidia() -> list[GpuDeviceInfo]:
    """NVIDIA devices, or ``[]`` when the stack is absent. Never raises."""
    return _probe_nvidia().devices


def probe_amd(*, sysfs_root: Path | None = None) -> list[GpuDeviceInfo]:
    """AMD devices from the first fallback that answers. Never raises.

    Order is PLAN.md §7.1's: ``amd-smi``, then ``rocm-smi``, then sysfs.
    """
    return _probe_amd(DEFAULT_SYSFS_ROOT if sysfs_root is None else sysfs_root).devices


def probe_cpu() -> list[GpuDeviceInfo]:
    """Always exactly one device: the CPU path exists on every machine."""
    return [cpu_device()]


def detect_devices(
    *,
    use_cache: bool = True,
    now: Callable[[], float] = time.monotonic,
    sysfs_root: Path | None = None,
) -> list[GpuDeviceInfo]:
    """Every device, in the documented order: NVIDIA, then AMD, then CPU.

    ``use_cache=False`` neither reads nor writes the 5 s cache, which is what
    makes the tests deterministic; ``now`` and ``sysfs_root`` are injectable for
    the same reason.
    """
    report = probe_report(use_cache=use_cache, now=now, sysfs_root=sysfs_root)
    return list(report.devices)


def probe_report(
    *,
    use_cache: bool = True,
    now: Callable[[], float] = time.monotonic,
    sysfs_root: Path | None = None,
) -> GpuProbeReport:
    """Devices plus a per-vendor verdict, cached for :data:`CACHE_TTL_S`.

    Thread-safe: M4's scheduler calls this from worker threads. The cache lock is
    never held across a subprocess call; ``_probe_lock`` deliberately is, so a
    burst of concurrent callers costs one probe round instead of one per thread.
    """
    global _cached  # the process-wide 5 s cache is the point of this function
    root = DEFAULT_SYSFS_ROOT if sysfs_root is None else sysfs_root
    if use_cache:
        cached = _read_cache(now())
        if cached is not None:
            return cached
    with _probe_lock:
        if use_cache:
            # Re-check: another thread may have filled the cache while we waited.
            cached = _read_cache(now())
            if cached is not None:
                return cached
        report = _probe_all(root)
        if use_cache:
            with _cache_lock:
                _cached = _CacheEntry(expires_at=now() + CACHE_TTL_S, report=report)
        return report


def invalidate_cache() -> None:
    """Drop the cached probe, so the next call shells out again.

    Used after a runtime is provisioned (GPU-07: the user may have just installed
    a driver) and by tests, which must not inherit each other's machine state.
    """
    global _cached  # see probe_report: one cache per process, by design
    with _cache_lock:
        _cached = None


def _read_cache(current: float) -> GpuProbeReport | None:
    with _cache_lock:
        entry = _cached
    if entry is not None and current < entry.expires_at:
        return entry.report
    return None


def _probe_all(sysfs_root: Path) -> GpuProbeReport:
    nvidia = _guarded(_probe_nvidia)
    amd = _guarded(lambda: _probe_amd(sysfs_root))
    devices = [
        *nvidia.devices,
        # A machine with both stacks installed (a hybrid laptop, or a user who
        # installed both SDKs) reports every device, and GPU-04 picks one by
        # index, so the AMD group is shifted when it would collide.
        *_unique_indices(amd.devices, taken={device.index for device in nvidia.devices}),
        cpu_device(),
    ]
    vendors = [
        GpuVendorAvailability(
            vendor=GpuVendor.NVIDIA, available=nvidia.reason is None, reason=nvidia.reason
        ),
        GpuVendorAvailability(
            vendor=GpuVendor.AMD, available=amd.reason is None, reason=amd.reason
        ),
        # The CPU path is never unavailable; reporting it keeps the list aligned
        # with GpuVendor so the UI can render one row per vendor.
        GpuVendorAvailability(vendor=GpuVendor.CPU, available=True, reason=None),
    ]
    return GpuProbeReport(devices=tuple(devices), vendors=tuple(vendors))


def _guarded(probe: Callable[[], _ProbeOutcome]) -> _ProbeOutcome:
    """A probe must not be able to take the engine down with it.

    The parsers are written not to raise, but a driver can hand back something
    nobody anticipated, and ``GET /v1/gpu/devices`` still has to answer for the
    CPU-only path (GPU-08).
    """
    try:
        return probe()
    except Exception:
        logger.exception("gpu probe raised unexpectedly")
        return _ProbeOutcome([], REASON_PROBE_FAILED)


def _probe_nvidia() -> _ProbeOutcome:
    result = run_probe_command((_NVIDIA_BINARY, *_NVIDIA_QUERY))
    reason = _failure_reason(result, REASON_NVIDIA_SMI_MISSING)
    if reason is not None:
        return _ProbeOutcome([], reason)
    devices = parse_nvidia_smi(result.stdout)
    if devices:
        return _ProbeOutcome(devices, None)
    return _ProbeOutcome([], _empty_output_reason(result))


def _probe_amd(sysfs_root: Path) -> _ProbeOutcome:
    """First success wins, in PLAN.md §7.1's order."""
    reasons: list[str] = []
    for argv, missing_reason in (
        (_AMD_SMI_QUERY, REASON_AMD_SMI_MISSING),
        (_ROCM_SMI_QUERY, REASON_ROCM_SMI_MISSING),
    ):
        outcome = _run_amd_tool(argv, missing_reason)
        if outcome.devices:
            return outcome
        if outcome.reason is not None:
            reasons.append(outcome.reason)
    sysfs_outcome = _probe_sysfs(sysfs_root)
    if sysfs_outcome.devices:
        return sysfs_outcome
    if sysfs_outcome.reason is not None:
        reasons.append(sysfs_outcome.reason)
    for candidate in _AMD_REASON_PRECEDENCE:
        if candidate in reasons:
            return _ProbeOutcome([], candidate)
    return _ProbeOutcome([], REASON_PROBE_FAILED)


def _run_amd_tool(argv: tuple[str, ...], missing_reason: str) -> _ProbeOutcome:
    result = run_probe_command(argv)
    reason = _failure_reason(result, missing_reason)
    if reason is not None:
        return _ProbeOutcome([], reason)
    devices = parse_amd_smi(result.stdout)
    if devices:
        return _ProbeOutcome(devices, None)
    return _ProbeOutcome([], _empty_output_reason(result))


def _probe_sysfs(sysfs_root: Path) -> _ProbeOutcome:
    devices = parse_sysfs_vram(sysfs_root)
    if devices:
        return _ProbeOutcome(devices, None)
    return _ProbeOutcome([], REASON_SYSFS_VRAM_MISSING)


def _failure_reason(result: CommandResult, missing_reason: str) -> str | None:
    """``None`` when the tool ran and exited 0, else the reason to report."""
    if result.outcome == OUTCOME_MISSING:
        return missing_reason
    if result.outcome == OUTCOME_TIMEOUT:
        return REASON_PROBE_TIMEOUT
    if result.outcome != OUTCOME_OK:
        return REASON_PROBE_FAILED
    if result.returncode != 0:
        logger.debug(
            "gpu probe returned a non-zero exit",
            extra={
                "returncode": result.returncode,
                "stderr_tail": result.stderr[-200:],
            },
        )
        return REASON_PROBE_FAILED
    return None


def _empty_output_reason(result: CommandResult) -> str:
    """A tool that ran fine but described no device: broken output or no hardware?

    Valid JSON with nothing in it means no card from that vendor is present — the
    normal case on a single-vendor machine — so it must not be reported as a parse
    failure. Only output that is not JSON at all is a broken probe.
    """
    text = result.stdout.strip()
    if not text:
        return REASON_NO_DEVICES
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return REASON_PARSE_FAILED
    return REASON_NO_DEVICES


def _unique_indices(devices: Sequence[GpuDeviceInfo], *, taken: set[int]) -> list[GpuDeviceInfo]:
    """Shift a vendor group so its indices cannot collide with an earlier one.

    The vendor ordinal is preserved whenever it does not collide, because that
    ordinal is what ``HIP_VISIBLE_DEVICES`` expects in M3 (D-13); only a colliding
    group is moved, continuing from the highest index already taken.
    """
    if not taken or not any(device.index in taken for device in devices):
        return list(devices)
    base = max(taken) + 1
    return [
        device.model_copy(update={"index": base + offset}) for offset, device in enumerate(devices)
    ]


def _amd_records(payload: object) -> list[tuple[str, Mapping[str, object]]]:
    """Normalise the three accepted top-level shapes into ``(card_key, record)``."""
    if isinstance(payload, Mapping):
        if any(_normalise_key(str(key)) in _ALL_MEMORY_KEYS for key in payload):
            # A memory key at the top level means the object *is* the record.
            return [("", payload)]
        groups = [(str(key), value) for key, value in payload.items() if isinstance(value, Mapping)]
        if groups:
            return groups
        return []
    if isinstance(payload, list):
        return [(_card_key(item, ordinal), item) for ordinal, item in enumerate(payload)]
    # A bare string, a number, null: not a device list, and not worth an exception.
    return []


def _card_key(record: Mapping[str, object], ordinal: int) -> str:
    fields = {_normalise_key(str(key)): value for key, value in record.items()}
    for key in _CARD_KEYS:
        value = fields.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"card{ordinal}"


def _amd_device(key: str, record: Mapping[str, object], ordinal: int) -> GpuDeviceInfo | None:
    memory = _memory_of(record)
    if memory is None:
        # rocm-smi's "system" block, or a record with no VRAM figures: not a device.
        return None
    total = memory.total_mib
    return GpuDeviceInfo(
        index=ordinal,
        vendor=GpuVendor.AMD,
        name=_amd_name(key, record, ordinal),
        driver=_amd_driver(record),
        memory_total_mib=total,
        memory_free_mib=memory.free_mib,
        available=total is not None,
        reason=None if total is not None else REASON_MEMORY_UNREADABLE,
    )


def _memory_of(record: Mapping[str, object]) -> _Memory | None:
    fields: dict[str, int] = {}
    for raw_key, value in _iter_fields(record):
        if _is_percentage(raw_key):
            continue
        parsed = _as_int(value)
        if parsed is None:
            continue
        fields.setdefault(_normalise_key(raw_key), parsed)

    total_hit = _first_field(fields, _TOTAL_KEYS)
    free_hit = _first_field(fields, _FREE_KEYS)
    if total_hit is None and free_hit is None:
        return None
    total = None if total_hit is None else _to_mib(total_hit[1], total_hit[0])
    free = None if free_hit is None else _to_mib(free_hit[1], free_hit[0])
    used_hit = _first_field(fields, _USED_KEYS)
    if free is None and total is not None and used_hit is not None:
        free = total - _to_mib(used_hit[1], used_hit[0])
    return _Memory(total_mib=total, free_mib=free)


def _first_field(fields: Mapping[str, int], order: tuple[str, ...]) -> tuple[str, int] | None:
    for key in order:
        if key in fields:
            return key, fields[key]
    return None


def _iter_fields(record: Mapping[str, object]) -> Iterator[tuple[str, object]]:
    """The record's own fields plus one level of nested objects.

    One level is exactly what amd-smi needs (``{"Vram": {"mem_total": …}}``) and
    no deeper, so an unrelated nested ``total`` cannot be mistaken for VRAM.
    """
    for key, value in record.items():
        yield str(key), value
        if isinstance(value, Mapping):
            yield from ((str(inner), inner_value) for inner, inner_value in value.items())


def _amd_name(key: str, record: Mapping[str, object], ordinal: int) -> str:
    for raw_key, value in _iter_fields(record):
        if _normalise_key(raw_key) in _NAME_KEYS and isinstance(value, str) and value.strip():
            return value.strip()
    if key:
        # rocm-smi keys records by PCI path; the address is the useful part.
        return PurePosixPath(key).name
    return f"card{ordinal}"


def _amd_driver(record: Mapping[str, object]) -> str | None:
    for raw_key, value in _iter_fields(record):
        if _normalise_key(raw_key) not in _DRIVER_KEYS:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
        number = _as_int(value)
        if number is not None:
            return str(number)
    return None


def _is_percentage(raw_key: str) -> bool:
    normalised = _normalise_key(raw_key)
    return "%" in raw_key or normalised.endswith(("percent", "pct", "percentage"))


def _to_mib(value: int, normalised_key: str) -> int:
    if normalised_key.endswith("mib"):
        return value
    if normalised_key.endswith("gib"):
        return value * 1024
    if normalised_key.endswith("kib"):
        return value // 1024
    # No unit in the key means bytes: amd-smi, rocm-smi and the sysfs attributes
    # all report bytes, and a key that says ``(B)`` normalises to a ``b`` suffix.
    return value // _BYTES_PER_MIB


def _normalise_key(raw_key: str) -> str:
    return "".join(character for character in raw_key.lower() if character.isalnum())


def _as_int(value: object) -> int | None:
    """Coerce a JSON scalar to an int. AMD tools emit numbers *and* numeric strings."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) else None
    if isinstance(value, str):
        return _int_from_text(value)
    return None


def _int_from_text(text: str) -> int | None:
    """Parse ``12287``, ``12287.0``, ``" 12287 "`` or an ``[N/A]`` placeholder."""
    stripped = text.strip()
    if not stripped or stripped.lower() in _PLACEHOLDERS:
        return None
    try:
        return int(stripped)
    except ValueError:
        return _int_from_float_text(stripped)


def _int_from_float_text(stripped: str) -> int | None:
    try:
        value = float(stripped)
    except ValueError:
        return None
    return int(value) if math.isfinite(value) else None


def _text_or(value: str, fallback: str | None) -> str | None:
    """Map a placeholder or an empty field onto ``None`` instead of a fake value."""
    stripped = value.strip()
    if not stripped or stripped.lower() in _PLACEHOLDERS:
        return fallback
    return stripped


def _read_int_file(path: Path) -> int | None:
    try:
        return _int_from_text(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def _read_sysfs_driver(device_dir: Path) -> str | None:
    """``DRIVER=amdgpu`` from the device uevent; sysfs has no version attribute."""
    try:
        uevent = (device_dir / "uevent").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in uevent.splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "DRIVER" and value.strip():
            return value.strip()
    return None
