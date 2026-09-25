# SPDX-License-Identifier: Apache-2.0
"""Queue one job on disk (JB-06).

A second job is refused while any job for the project is still queued,
running, paused, or muxing. This does not render audio and does not write
a plan; those passes come after the record exists.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from praelector.domain.enums import ACTIVE_JOB_STATES, JobKind, JobState
from praelector.domain.ids import IdPrefix, new_id
from praelector.errors import AppError, ErrorCode
from praelector.jobs.catalog import list_jobs
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.store.manifest import utc_now
from praelector.store.tables import to_db_time

Clock = Callable[[], datetime]


def create_queued(
    jobs_dir: Path,
    *,
    project_id: str,
    kind: JobKind,
    revision: int,
    options: dict[str, Any] | None = None,
    clock: Clock | None = None,
) -> JobRecord:
    """Write a queued ``job.json``. A live job is ``job.already_active``."""
    for existing in list_jobs(jobs_dir):
        if existing.project_id == project_id and existing.state in ACTIVE_JOB_STATES:
            raise AppError(ErrorCode.JOB_ALREADY_ACTIVE, detail={"id": existing.id})
    stamp = to_db_time((clock or utc_now)())
    record = JobRecord(
        id=new_id(IdPrefix.JOB),
        project_id=project_id,
        kind=kind,
        state=JobState.QUEUED,
        revision=revision,
        created_at=stamp,
        updated_at=stamp,
        options=dict(options or {}),
    )
    return JobLog(jobs_dir / record.id).create(record)
