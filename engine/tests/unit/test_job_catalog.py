# SPDX-License-Identifier: Apache-2.0
"""A job listing reads job.json and does not crash-recover it."""

from __future__ import annotations

from pathlib import Path

import pytest

from praelector.domain.enums import JobKind, JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.catalog import list_jobs, load_job
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.state import JobEvent


def _record(job_id: str, stamp: str) -> JobRecord:
    return JobRecord(
        id=job_id,
        project_id="prj_01",
        kind=JobKind.RECORD,
        state=JobState.QUEUED,
        revision=1,
        created_at=stamp,
        updated_at=stamp,
    )


def test_jobs_are_newest_first_and_a_bad_file_is_skipped(tmp_path: Path) -> None:
    older = JobLog(tmp_path / "job_old")
    newer = JobLog(tmp_path / "job_new")
    older.create(_record("job_old", "2026-09-25T00:00:00Z"))
    newer.create(_record("job_new", "2026-09-25T01:00:00Z"))
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "job.json").write_text("{", encoding="utf-8")

    assert [record.id for record in list_jobs(tmp_path)] == ["job_new", "job_old"]


def test_load_refuses_a_missing_job(tmp_path: Path) -> None:
    with pytest.raises(AppError) as excinfo:
        load_job(tmp_path, "job_missing")
    assert excinfo.value.code is ErrorCode.JOB_NOT_FOUND


def test_reading_a_running_job_does_not_pause_it(tmp_path: Path) -> None:
    log = JobLog(tmp_path / "job_live")
    log.apply(log.create(_record("job_live", "2026-09-25T00:00:00Z")), JobEvent.START)

    loaded = load_job(tmp_path, "job_live")

    assert loaded.state is JobState.RUNNING
    assert loaded.paused_reason is None
