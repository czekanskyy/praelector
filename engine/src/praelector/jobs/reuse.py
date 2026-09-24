# SPDX-License-Identifier: Apache-2.0
"""Decide whether a finished chunk can be reused (JB-05, PLAN.md §8.3).

A chunk is reused only when the sidecar and the WAV are both present and
the file size and duration agree with the sidecar.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path


def chunk_reusable(wav: Path, sidecar: Path, *, probe: Callable[[Path], float]) -> bool:
    """True when this render can be skipped. A bad sidecar is not reusable."""
    if not wav.is_file() or not sidecar.is_file():
        return False
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        size = meta["size"]
        duration = float(meta["duration_s"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return False
    if not isinstance(size, int) or wav.stat().st_size != size:
        return False
    return probe(wav) == duration
