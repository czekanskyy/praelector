# SPDX-License-Identifier: Apache-2.0
"""Trust chunk files over any index (JB-07, DATA_MODEL.md §9.1).

A sidecar is reusable only when its WAV is present and the size and duration
agree. Anything else is a torn write: both files move to the quarantine
directory and the render key is not returned. Partial files are left where
the worker put them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from praelector.jobs.reuse import chunk_reusable

Probe = Callable[[Path], float]


@dataclass(frozen=True, slots=True)
class ChunkReconcile:
    """Render keys still on disk, and the files moved aside."""

    reusable: list[str]
    quarantined: list[str]


def reconcile_chunks(
    chunks_dir: Path,
    quarantine_dir: Path,
    *,
    probe: Probe,
) -> ChunkReconcile:
    """Scan one shard level under ``chunks_dir``. Missing dir means nothing to do."""
    if not chunks_dir.is_dir():
        return ChunkReconcile([], [])
    reusable: list[str] = []
    quarantined: list[str] = []
    shards = sorted(path for path in chunks_dir.iterdir() if path.is_dir())
    for shard in shards:
        for stem in _stems(shard):
            wav = shard / f"{stem}.wav"
            sidecar = shard / f"{stem}.json"
            if chunk_reusable(wav, sidecar, probe=probe):
                reusable.append(stem)
                continue
            dest = quarantine_dir / shard.name
            for path in (wav, sidecar):
                moved = _quarantine(path, dest)
                if moved is not None:
                    quarantined.append(moved)
    return ChunkReconcile(reusable, quarantined)


def _stems(shard: Path) -> list[str]:
    stems: set[str] = set()
    for path in shard.iterdir():
        name = path.name
        if name.endswith(".wav.part") or name.endswith(".json.part"):
            continue
        if name.endswith(".wav"):
            stems.add(name[: -len(".wav")])
        elif name.endswith(".json"):
            stems.add(name[: -len(".json")])
    return sorted(stems)


def _quarantine(path: Path, dest_dir: Path) -> str | None:
    if not path.is_file():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / path.name
    if target.exists():
        target = dest_dir / f"{path.name}.{path.stat().st_mtime_ns}"
    path.replace(target)
    return path.name
