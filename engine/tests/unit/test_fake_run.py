# SPDX-License-Identifier: Apache-2.0
"""A running record job renders missing speech and then waits in muxing."""

from __future__ import annotations

from pathlib import Path

import pytest

from praelector.audio.render_fake import render_chunk, wav_seconds
from praelector.domain.enums import JobKind, JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.chunker import PlanItem
from praelector.jobs.fake_run import render_pass
from praelector.jobs.reuse import chunk_reusable
from praelector.jobs.state import JobEvent


def _running(root: Path) -> tuple[JobLog, JobRecord]:
    log = JobLog(root / "job")
    stamp = "2026-09-25T00:00:00Z"
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
    return log, running


def _item(ordinal: int) -> PlanItem:
    return PlanItem(ordinal, "chp_1", "narrator", "a" * 14, "tts", f"k{ordinal}")


def _paths(root: Path, item: PlanItem) -> tuple[Path, Path, Path]:
    wav = root / f"{item.render_key}.wav"
    return wav.with_name(wav.name + ".part"), wav, wav.with_suffix(".json")


def _reusable(root: Path, item: PlanItem) -> bool:
    _part, wav, sidecar = _paths(root, item)
    return chunk_reusable(wav, sidecar, probe=wav_seconds)


def test_a_pass_reuses_a_finished_chunk_and_enters_muxing(tmp_path: Path) -> None:
    items = [_item(0), _item(1)]
    part, wav, sidecar = _paths(tmp_path, items[0])
    render_chunk(items[0].spoken_text, part, wav, sidecar)
    log, running = _running(tmp_path)

    done = render_pass(
        log,
        running,
        items,
        paths_for=lambda item: _paths(tmp_path, item),
        reusable=lambda item: _reusable(tmp_path, item),
    )

    assert done.state is JobState.MUXING
    assert done.counts == {"chunks_total": 2, "chunks_done": 2, "chunks_reused": 1}
    assert done.cursor["next_ordinal"] == 2
    assert (tmp_path / "k1.wav").is_file()
    assert any(event["type"] == "job.progress" for event in log.events())


def test_a_paused_job_is_not_rendered(tmp_path: Path) -> None:
    log, running = _running(tmp_path)
    paused = log.apply(running, JobEvent.PAUSE)
    with pytest.raises(AppError) as excinfo:
        render_pass(
            log,
            paused,
            [_item(0)],
            paths_for=lambda item: _paths(tmp_path, item),
            reusable=lambda _item: False,
        )
    assert excinfo.value.code is ErrorCode.JOB_INVALID_TRANSITION
    assert not (tmp_path / "k0.wav").exists()
