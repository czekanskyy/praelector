# SPDX-License-Identifier: Apache-2.0
"""Job routes (OPENAPI_SKETCH.md §7).

History, the event replay a reconnecting UI needs, and pause / resume / cancel.
Creating a job is still not on this router.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi import Path as PathParam

from praelector.domain.enums import JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.catalog import job_events, list_jobs, load_job
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.state import JobEvent
from praelector.state import AppState, get_state
from praelector.store.projects import OpenProject

router = APIRouter(tags=["jobs"])

ProjectId = Annotated[str, PathParam(min_length=4, max_length=64, pattern=r"^prj_[0-9A-Z]{26}$")]
JobId = Annotated[str, PathParam(min_length=4, max_length=64, pattern=r"^job_[0-9A-Z]{26}$")]


def _open(state: AppState, project_id: str) -> OpenProject:
    return state.projects.require_open(project_id)


@router.get("/projects/{project_id}/jobs")
def list_project_jobs(
    project_id: ProjectId, state: AppState = Depends(get_state)
) -> dict[str, list[dict[str, Any]]]:
    """Newest first. Only records whose ``project_id`` matches the open project."""
    opened = _open(state, project_id)
    jobs = [
        record.to_json()
        for record in list_jobs(opened.layout.jobs)
        if record.project_id == project_id
    ]
    return {"jobs": jobs}


@router.get("/jobs/{job_id}")
def get_job(job_id: JobId, state: AppState = Depends(get_state)) -> dict[str, Any]:
    """The open project's job. A job from any other project is ``job.not_found``."""
    opened = state.projects.require_current()
    record = load_job(opened.layout.jobs, job_id)
    if record.project_id != opened.id:
        raise AppError(ErrorCode.JOB_NOT_FOUND, detail={"job_id": job_id})
    return record.to_json()


@router.get("/jobs/{job_id}/events")
def get_job_events(
    job_id: JobId,
    since: Annotated[int, Query(ge=0)] = 0,
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Events strictly after ``since``, for a WebSocket reconnect."""
    opened = state.projects.require_current()
    record = load_job(opened.layout.jobs, job_id)
    if record.project_id != opened.id:
        raise AppError(ErrorCode.JOB_NOT_FOUND, detail={"job_id": job_id})
    return {"events": job_events(opened.layout.jobs, job_id, since=since)}


def _owned(state: AppState, job_id: str) -> tuple[OpenProject, JobRecord]:
    opened = state.projects.require_current()
    record = load_job(opened.layout.jobs, job_id)
    if record.project_id != opened.id:
        raise AppError(ErrorCode.JOB_NOT_FOUND, detail={"job_id": job_id})
    return opened, record


def _apply(opened: OpenProject, record: JobRecord, event: JobEvent) -> dict[str, Any]:
    updated = JobLog(opened.layout.job_dir(record.id)).apply(record, event)
    return updated.to_json()


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: JobId, state: AppState = Depends(get_state)) -> dict[str, Any]:
    """Pause and delete ``*.part`` files under the project chunks directory."""
    opened, record = _owned(state, job_id)
    body = _apply(opened, record, JobEvent.PAUSE)
    _drop_partials(opened.layout.chunks)
    return body


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: JobId, state: AppState = Depends(get_state)) -> dict[str, Any]:
    opened, record = _owned(state, job_id)
    return _apply(opened, record, JobEvent.RESUME)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: JobId, state: AppState = Depends(get_state)) -> dict[str, Any]:
    """Cancel a queued job. Any other live state is a stop, which keeps finished audio."""
    opened, record = _owned(state, job_id)
    event = JobEvent.CANCEL if record.state is JobState.QUEUED else JobEvent.STOP
    return _apply(opened, record, event)


def _drop_partials(chunks: Path) -> None:
    if not chunks.is_dir():
        return
    for path in chunks.rglob("*.part"):
        if path.is_file():
            path.unlink()
