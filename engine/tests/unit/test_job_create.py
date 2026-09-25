# SPDX-License-Identifier: Apache-2.0
"""Queuing a job refuses a second live one."""

from __future__ import annotations

from pathlib import Path

import pytest

from praelector.domain.enums import JobKind, JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.checkpoint import JobLog
from praelector.jobs.create import create_queued
from praelector.jobs.state import JobEvent

PROJECT = "prj_" + "A" * 26


def test_a_live_job_blocks_the_next_one(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs"
    first = create_queued(
        jobs,
        project_id=PROJECT,
        kind=JobKind.RECORD,
        revision=3,
        options={"auto_mux": True},
    )
    assert first.state is JobState.QUEUED
    assert first.revision == 3
    assert first.options == {"auto_mux": True}
    assert (jobs / first.id / "job.json").is_file()

    with pytest.raises(AppError) as caught:
        create_queued(jobs, project_id=PROJECT, kind=JobKind.PREP, revision=3)
    assert caught.value.code is ErrorCode.JOB_ALREADY_ACTIVE
    assert caught.value.detail["id"] == first.id

    JobLog(jobs / first.id).apply(first, JobEvent.CANCEL)
    second = create_queued(jobs, project_id=PROJECT, kind=JobKind.PREP, revision=3)
    assert second.id != first.id
    assert second.kind is JobKind.PREP
