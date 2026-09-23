# SPDX-License-Identifier: Apache-2.0
"""VRAM reporting from inside the worker (GPU-02, GPU-03).

The engine's own probe shells out to ``nvidia-smi``/``rocm-smi`` and sees the
whole device; this sees what *this process* actually took, which is the number
that calibrates the per-backend peak table after a real run.
"""

from __future__ import annotations

from praelector_tts.device import torch_available
from praelector_tts.protocol import VramReport

_BYTES_PER_MIB = 1024 * 1024


def probe(device: str | None = None) -> VramReport:
    """Current allocation for ``device``. Empty report when torch is absent."""
    if not torch_available():
        return VramReport(device=device)

    import torch

    if not torch.cuda.is_available():
        return VramReport(device=device)

    # torch's CUDA API is also the HIP API on ROCm builds.
    index = _device_index(device)
    return VramReport(
        device=device or f"cuda:{index}",
        allocated_mib=_mib(torch.cuda.memory_allocated(index)),
        reserved_mib=_mib(torch.cuda.memory_reserved(index)),
        peak_mib=_mib(torch.cuda.max_memory_allocated(index)),
    )


def reset_peak(device: str | None = None) -> None:
    """Start a fresh peak measurement, e.g. before a chunk."""
    if not torch_available():
        return
    import torch

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats(_device_index(device))


def _device_index(device: str | None) -> int:
    if not device or ":" not in device:
        return 0
    suffix = device.rsplit(":", 1)[-1]
    return int(suffix) if suffix.isdigit() else 0


def _mib(value: int) -> int:
    return round(value / _BYTES_PER_MIB)
