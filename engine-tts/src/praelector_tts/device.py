# SPDX-License-Identifier: Apache-2.0
"""Device selection and pinning (PLAN.md D-13: one GPU device per job).

Nothing here imports torch at module scope. The worker must be importable with no
extra installed, and CUDA must not be initialised before the visible-device pin
is in place — initialising first and pinning afterwards silently pins nothing.
"""

from __future__ import annotations

import importlib.util
import os


def torch_available() -> bool:
    """True when a torch extra is installed in this environment."""
    return importlib.util.find_spec("torch") is not None


def pin_visible_device(index: int) -> None:
    """Restrict the process to one physical device before torch initialises.

    Both variables are set because the same worker code runs on CUDA and ROCm
    builds and only one of them is read.
    """
    value = str(max(0, index))
    os.environ["CUDA_VISIBLE_DEVICES"] = value
    os.environ["HIP_VISIBLE_DEVICES"] = value


def select_device(requested: str | None = None, *, device_index: int = 0) -> str:
    """Resolve a torch device string.

    ``requested`` wins when it is explicit ("cpu", "cuda:0"). Otherwise a usable
    accelerator is preferred, and CPU is the fallback — the slow path is a UI
    concern (GPU-08), not something the worker decides.
    """
    if requested:
        return requested
    if not torch_available():
        return "cpu"

    import torch

    if torch.cuda.is_available():
        return f"cuda:{device_index}"
    return "cpu"


def set_low_vram_alloc_conf(vendor: str) -> None:
    """Ask the allocator for expandable segments on a card that is too small.

    ``max(1, …)`` in the budget formula can return one worker for a card that
    cannot really hold it (PLAN.md §7.2); this is the mitigation that keeps that
    worker alive instead of OOMing on the first chunk.
    """
    value = "expandable_segments:True"
    if vendor == "rocm":
        os.environ.setdefault("PYTORCH_HIP_ALLOC_CONF", value)
    else:
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", value)
