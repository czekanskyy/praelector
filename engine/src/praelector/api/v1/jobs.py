# SPDX-License-Identifier: Apache-2.0
"""Job lifecycle and execution management API endpoints (JB-01..JB-07, AI-01, D-14)."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, status

from praelector.api.deps import get_job_manager, get_llm_router, get_project_manager
from praelector.domain.enums import JobKind
from praelector.domain.models import JobCreateRequest, JobResponse
from praelector.errors import PraelectorError
from praelector.jobs.manager import JobManager
from praelector.jobs.prep_job import PrepJob
from praelector.llm.router import LlmRouter
from praelector.store.project_manager import ProjectManager

router = APIRouter(tags=["jobs"])


@router.post(
    "/projects/{pid}/jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    pid: str,
    payload: JobCreateRequest,
    job_manager: Annotated[JobManager, Depends(get_job_manager)],
    project_manager: Annotated[ProjectManager, Depends(get_project_manager)],
    llm_router: Annotated[LlmRouter, Depends(get_llm_router)],
) -> JobResponse:
    """Create and start a background job (AI-01, JB-06, D-14)."""
    if payload.kind == JobKind.PREP.value or payload.kind == "prep":
        job = job_manager.create_job(
            project_id=pid,
            kind=JobKind.PREP.value,
            options=payload.options,
        )

        prep_job = PrepJob(
            job_id=job.id,
            project_id=pid,
            job_manager=job_manager,
            project_manager=project_manager,
            llm_router=llm_router,
            options=payload.options,
        )

        task = asyncio.create_task(prep_job.run())
        job_manager.attach_task(job.id, task)
        return job

    raise PraelectorError(
        code="job.unsupported_kind",
        message=f"Job kind '{payload.kind}' is not supported yet.",
    )


@router.get("/projects/{pid}/jobs", response_model=list[JobResponse])
def list_jobs(
    pid: str,
    job_manager: Annotated[JobManager, Depends(get_job_manager)],
) -> list[JobResponse]:
    """List all jobs for a project, newest first (JB-04)."""
    return job_manager.list_jobs(pid)


@router.get("/jobs/{jid}", response_model=JobResponse)
def get_job(
    jid: str,
    job_manager: Annotated[JobManager, Depends(get_job_manager)],
) -> JobResponse:
    """Get full state, stage, counts, and metrics for a job (UI-01..UI-06)."""
    job = job_manager.get_job(jid)
    if job is None:
        raise PraelectorError(code="job.not_found", message=f"Job '{jid}' not found")
    return job


@router.post("/jobs/{jid}/cancel", response_model=JobResponse)
def cancel_job(
    jid: str,
    job_manager: Annotated[JobManager, Depends(get_job_manager)],
) -> JobResponse:
    """Cancel an active or running job, preserving partial results (AI-01, JB-04)."""
    return job_manager.cancel_job(jid)
