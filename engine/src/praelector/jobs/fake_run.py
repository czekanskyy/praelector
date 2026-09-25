# SPDX-License-Identifier: Apache-2.0
"""One pass of the fake voice over a running record job.

No worker process and no GPU. Speech that already has a matching sidecar
is counted as reused. When every speech line is done the job moves to
``muxing``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from praelector.audio.render_fake import render_chunk
from praelector.domain.enums import JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.chunker import PlanItem
from praelector.jobs.cursor import cursor_after
from praelector.jobs.metrics import Progress
from praelector.jobs.state import JobEvent

Paths = Callable[[PlanItem], tuple[Path, Path, Path]]
Reusable = Callable[[PlanItem], bool]


def render_pass(
    log: JobLog,
    record: JobRecord,
    items: Sequence[PlanItem],
    *,
    paths_for: Paths,
    reusable: Reusable,
) -> JobRecord:
    """Render what is missing, then note progress. A finished plan enters muxing."""
    if record.state is not JobState.RUNNING:
        raise AppError(
            ErrorCode.JOB_INVALID_TRANSITION,
            detail={"state": record.state, "event": "progress"},
        )
    progress = Progress()
    done: set[int] = set()
    reused = 0
    for item in items:
        if item.kind == "silence":
            continue
        if reusable(item):
            done.add(item.ordinal)
            reused += 1
            continue
        part, wav, sidecar = paths_for(item)
        started = time.perf_counter()
        duration = render_chunk(item.spoken_text, part, wav, sidecar)
        wall = max(time.perf_counter() - started, 1e-6)
        progress.observe(chars=len(item.spoken_text), duration_s=duration, wall_s=wall)
        done.add(item.ordinal)
    speech_total = sum(1 for item in items if item.kind != "silence")
    cursor = cursor_after(items, done)
    metrics: dict[str, float] = {
        "throughput": progress.throughput,
        "chars_per_audio_s": progress.chars_per_audio_s,
    }
    if progress.rtf_instant is not None:
        metrics["rtf_instant"] = progress.rtf_instant
    updated = log.note_progress(
        record,
        cursor={"next_ordinal": cursor},
        counts={
            "chunks_total": speech_total,
            "chunks_done": len(done),
            "chunks_reused": reused,
        },
        metrics=metrics,
    )
    finished = all(item.kind == "silence" or item.ordinal in done for item in items)
    if finished:
        return log.apply(updated, JobEvent.RENDERED)
    return updated
