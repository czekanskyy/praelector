# SPDX-License-Identifier: Apache-2.0
"""Health check endpoint polled by Desktop supervisor."""

from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["System"])

_start_time = time.time()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = Field(default="ok", description="Server health status")
    uptime_s: float = Field(..., description="Engine uptime in seconds")
    project_open: bool = Field(default=False, description="Whether a project is currently open")
    active_job_id: str | None = Field(
        default=None, description="Currently executing job ID, if any"
    )


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Returns engine health status and uptime."""
    uptime = time.time() - _start_time
    return HealthResponse(
        status="ok",
        uptime_s=round(uptime, 2),
        project_open=False,
        active_job_id=None,
    )
