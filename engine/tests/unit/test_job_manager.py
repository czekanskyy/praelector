# SPDX-License-Identifier: Apache-2.0
"""One slot, and audio survives reset unless deletion is explicit."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from praelector.domain.enums import JobKind, JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.manager import JobManager


def _clock() -> datetime:
    return datetime(2026, 9, 24, 15, 0, tzinfo=UTC)


def _record(job_id: str = "job_01") -> JobRecord:
    stamp = "2026-09-24T14:00:00Z"
    return JobRecord(
        id=job_id,
        project_id="prj_01",
        kind=JobKind.RECORD,
        state=JobState.QUEUED,
        revision=1,
        created_at=stamp,
        updated_at=stamp,
    )


def _manager(tmp_path: Path) -> tuple[JobManager, JobLog]:
    manager = JobManager()
    log = JobLog(tmp_path / "job_01", clock=_clock)
    manager.adopt(log, _record())
    return manager, log


def test_a_second_job_is_rejected_while_one_is_live(tmp_path: Path) -> None:
    manager, _log = _manager(tmp_path)
    manager.start()
    with pytest.raises(AppError) as caught:
        manager.adopt(JobLog(tmp_path / "job_02", clock=_clock), _record("job_02"))
    assert caught.value.code is ErrorCode.JOB_ALREADY_ACTIVE


def test_pause_deletes_partials_and_resume_continues(tmp_path: Path) -> None:
    manager, _log = _manager(tmp_path)
    manager.start()
    part = tmp_path / "chunk.wav.part"
    part.write_bytes(b"partial")
    paused = manager.pause(parts=[part])
    assert paused.state is JobState.PAUSED
    assert not part.exists()
    assert manager.resume().state is JobState.RUNNING


def test_stop_frees_the_slot_for_the_next_job(tmp_path: Path) -> None:
    manager, _log = _manager(tmp_path)
    manager.start()
    assert manager.stop().state is JobState.CANCELLED
    manager.reset()
    nxt = manager.adopt(JobLog(tmp_path / "job_02", clock=_clock), _record("job_02"))
    assert nxt.id == "job_02"


def test_reset_keeps_audio_unless_deletion_is_asked(tmp_path: Path) -> None:
    manager, _log = _manager(tmp_path)
    manager.start()
    manager.stop()
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    wav = chunks / "aa" / "abcd.wav"
    wav.parent.mkdir()
    wav.write_bytes(b"RIFF")
    manager.reset(delete_audio=False, chunks_dir=chunks)
    assert wav.is_file()

    manager.adopt(JobLog(tmp_path / "job_02", clock=_clock), _record("job_02"))
    manager.start()
    manager.stop()
    manager.reset(delete_audio=True, chunks_dir=chunks)
    assert not chunks.exists()


def test_reset_of_a_running_job_is_rejected(tmp_path: Path) -> None:
    manager, _log = _manager(tmp_path)
    manager.start()
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    with pytest.raises(AppError) as caught:
        manager.reset(delete_audio=True, chunks_dir=chunks)
    assert caught.value.code is ErrorCode.JOB_INVALID_TRANSITION
    assert chunks.is_dir()
