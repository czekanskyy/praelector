# SPDX-License-Identifier: Apache-2.0
"""Read job records without changing them (JB-04, PLAN.md §8.1).

``JobLog.open`` crash-recovers a job that was left running. Listing and
gap-fill must not do that: a GET is not an engine start.
"""

from __future__ import annotations

import json
from pathlib import Path

from praelector.errors import AppError, ErrorCode
from praelector.jobs.checkpoint import JobLog, JobRecord


def list_jobs(jobs_dir: Path) -> list[JobRecord]:
    """Newest ``created_at`` first. A directory without a readable ``job.json`` is skipped."""
    if not jobs_dir.is_dir():
        return []
    records: list[JobRecord] = []
    for child in jobs_dir.iterdir():
        if not child.is_dir():
            continue
        record = _read(child / "job.json")
        if record is not None:
            records.append(record)
    records.sort(key=lambda record: record.created_at, reverse=True)
    return records


def load_job(jobs_dir: Path, job_id: str) -> JobRecord:
    """The record for ``job_id``. Missing or unreadable is ``job.not_found``."""
    directory = jobs_dir / job_id
    if directory.parent != jobs_dir or not directory.is_dir():
        raise AppError(ErrorCode.JOB_NOT_FOUND, detail={"job_id": job_id})
    record = _read(directory / "job.json")
    if record is None or record.id != job_id:
        raise AppError(ErrorCode.JOB_NOT_FOUND, detail={"job_id": job_id})
    return record


def job_events(jobs_dir: Path, job_id: str, *, since: int) -> list[dict[str, object]]:
    """Events with ``seq`` strictly greater than ``since``. Does not create the log."""
    load_job(jobs_dir, job_id)
    return JobLog(jobs_dir / job_id).events_since(since)


def _read(path: Path) -> JobRecord | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return JobRecord.from_json(payload)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
