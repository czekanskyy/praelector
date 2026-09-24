# SPDX-License-Identifier: Apache-2.0
"""Publish one rendered chunk (JB-02).

The worker leaves audio in a ``.part`` file. This renames it onto the
content-addressed WAV only after the probe agrees with the claimed
duration, then writes the sidecar. A crash before the rename leaves no
reusable chunk.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from praelector.errors import AppError, ErrorCode
from praelector.store.atomic import write_json_atomic

Probe = Callable[[Path], float]


def commit_chunk(
    part: Path,
    wav: Path,
    sidecar: Path,
    *,
    duration_s: float,
    probe: Probe,
    extra: dict[str, Any] | None = None,
) -> None:
    """Move ``part`` into place. A duration mismatch deletes the partial."""
    if not part.is_file():
        raise AppError(ErrorCode.AUDIO_PROBE_FAILED, detail={"reason": "missing_part"})
    size = part.stat().st_size
    if size <= 0:
        part.unlink(missing_ok=True)
        raise AppError(ErrorCode.AUDIO_PROBE_FAILED, detail={"reason": "empty_part"})
    measured = probe(part)
    if measured != duration_s:
        part.unlink(missing_ok=True)
        raise AppError(
            ErrorCode.AUDIO_PROBE_FAILED,
            detail={"duration_s": duration_s, "measured": measured},
        )
    wav.parent.mkdir(parents=True, exist_ok=True)
    part.replace(wav)
    payload = dict(extra or {})
    payload["size"] = size
    payload["duration_s"] = duration_s
    write_json_atomic(sidecar, payload)
