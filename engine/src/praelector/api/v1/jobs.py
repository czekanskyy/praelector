# SPDX-License-Identifier: Apache-2.0
"""Read-only job routes (OPENAPI_SKETCH.md §7).

History and the event replay a reconnecting UI needs. Creating, pausing
and resuming a job are still not on this router.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi import Path as PathParam

from praelector.errors import AppError, ErrorCode
from praelector.jobs.catalog import job_events, list_jobs, load_job
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
