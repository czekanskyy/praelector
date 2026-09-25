# SPDX-License-Identifier: Apache-2.0
"""``GET /jobs/{id}/plan`` — paginated items and whether each chunk can be reused."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi import Path as PathParam

from praelector.audio.render_fake import wav_seconds
from praelector.errors import AppError, ErrorCode
from praelector.jobs.catalog import load_job
from praelector.jobs.chunker import PlanItem
from praelector.jobs.plan_view import annotate_plan
from praelector.jobs.planfile import read_plan
from praelector.jobs.reuse import chunk_reusable
from praelector.state import AppState, get_state
from praelector.store.projects import OpenProject

router = APIRouter(tags=["jobs"])

JobId = Annotated[str, PathParam(min_length=4, max_length=64, pattern=r"^job_[0-9A-Z]{26}$")]


@router.get("/jobs/{job_id}/plan")
def get_job_plan(
    job_id: JobId,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Items from ``plan.jsonl``. A missing file is an empty plan, not an error."""
    opened = state.projects.require_current()
    record = load_job(opened.layout.jobs, job_id)
    if record.project_id != opened.id:
        raise AppError(ErrorCode.JOB_NOT_FOUND, detail={"job_id": job_id})
    items = read_plan(opened.layout.job_dir(job_id) / "plan.jsonl")
    return annotate_plan(items, reusable=_reusable(opened), offset=offset, limit=limit)


def _reusable(opened: OpenProject) -> Callable[[PlanItem], bool]:
    def probe(item: PlanItem) -> bool:
        return chunk_reusable(
            opened.layout.chunk_wav(item.render_key),
            opened.layout.chunk_sidecar(item.render_key),
            probe=wav_seconds,
        )

    return probe
