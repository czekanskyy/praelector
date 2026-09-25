# SPDX-License-Identifier: Apache-2.0
"""Trust chunk files over any index (JB-07, DATA_MODEL.md §9.1).

A sidecar is reusable only when its WAV is present and the size and duration
agree. Anything else is a torn write: both files move to the quarantine
directory and the render key is not returned. Partial files are left where
the worker put them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, delete

from praelector.jobs.reuse import chunk_reusable
from praelector.store.db import session_scope
from praelector.store.project_dir import ProjectLayout
from praelector.store.tables import ChunkRow

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


def write_chunk_index(engine: Engine, project_id: str, root: Path, keys: Sequence[str]) -> None:
    """Replace this project's chunk rows with the keys that just reconciled.

    A sidecar that disappeared between the scan and this write is omitted.
    Rows for keys that are no longer on disk are deleted.
    """
    layout = ProjectLayout(root=root)
    rows: list[ChunkRow] = []
    for key in keys:
        sidecar = layout.chunk_sidecar(key)
        wav = layout.chunk_wav(key)
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            size = meta["size"]
            duration = float(meta["duration_s"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if not isinstance(size, int) or not wav.is_file():
            continue
        rows.append(
            ChunkRow(
                render_key=key,
                project_id=project_id,
                size=size,
                duration_s=duration,
                rel_path=layout.relative(wav),
            )
        )
    with session_scope(engine) as session:
        session.execute(delete(ChunkRow).where(ChunkRow.project_id == project_id))
        session.add_all(rows)


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
