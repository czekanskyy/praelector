# SPDX-License-Identifier: Apache-2.0
"""A crash after two chunks does not make those chunks render again."""

from __future__ import annotations

from pathlib import Path

from praelector.audio.render_fake import wav_seconds
from praelector.audio.render_missing import render_missing
from praelector.domain.enums import JobKind, JobState
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.chunker import PlanItem
from praelector.jobs.cursor import cursor_after
from praelector.jobs.reuse import chunk_reusable
from praelector.jobs.state import JobEvent


def _item(ordinal: int) -> PlanItem:
    return PlanItem(ordinal, "chp_1", "narrator", "a" * 14, "tts", f"k{ordinal}")


def _paths(root: Path, item: PlanItem) -> tuple[Path, Path, Path]:
    wav = root / "chunks" / f"{item.render_key}.wav"
    return wav.with_name(wav.name + ".part"), wav, wav.with_suffix(".json")


def _reusable(root: Path, item: PlanItem) -> bool:
    _part, wav, sidecar = _paths(root, item)
    return chunk_reusable(wav, sidecar, probe=wav_seconds)


def test_committed_chunks_survive_a_crash_and_are_not_rendered_again(tmp_path: Path) -> None:
    items = [_item(index) for index in range(4)]
    first = render_missing(
        items[:2],
        paths_for=lambda item: _paths(tmp_path, item),
        reusable=lambda item: _reusable(tmp_path, item),
    )
    assert first == [0, 1]

    stamp = "2026-09-25T00:00:00Z"
    log = JobLog(tmp_path / "job_01")
    running = log.apply(
        log.create(
            JobRecord(
                id="job_01",
                project_id="prj_01",
                kind=JobKind.RECORD,
                state=JobState.QUEUED,
                revision=1,
                created_at=stamp,
                updated_at=stamp,
            )
        ),
        JobEvent.START,
    )
    assert running.state is JobState.RUNNING
    recovered = log.open()
    assert recovered.state is JobState.PAUSED
    assert recovered.paused_reason == "crash_recovery"

    second = render_missing(
        items,
        paths_for=lambda item: _paths(tmp_path, item),
        reusable=lambda item: _reusable(tmp_path, item),
    )
    assert second == [2, 3]
    assert cursor_after(items, {0, 1, 2, 3}) == 4
