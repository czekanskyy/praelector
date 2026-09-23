# SPDX-License-Identifier: Apache-2.0
"""System routes: liveness, version, graceful shutdown (OPENAPI_SKETCH.md §1)."""

from __future__ import annotations

import logging
import platform
import sys
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from praelector import SCHEMA_VERSION, __version__
from praelector.state import AppState, get_state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])

#: The shell polls ``/v1/health`` every 5 s and restarts the engine after three
#: consecutive failures, so this route must stay cheap and dependency-free.
HEALTH_POLL_INTERVAL_S = 5.0


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "shutting_down"]
    uptime_s: float = Field(ge=0)
    project_open: bool
    active_job_id: str | None = None


class PlatformInfo(BaseModel):
    os: str
    arch: str
    python: str
    #: True when running from the PyInstaller bundle rather than a source tree.
    frozen: bool


class VersionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    app: str
    engine: str
    schema_version: int = Field(serialization_alias="schema")
    python: str
    platform: PlatformInfo


class ShutdownResponse(BaseModel):
    accepted: bool
    #: False under TestClient, where there is no server loop to stop.
    server_signalled: bool


@router.get("/health", response_model=HealthResponse)
async def health(state: AppState = Depends(get_state)) -> HealthResponse:
    status: Literal["ok", "degraded", "shutting_down"] = (
        "shutting_down" if state.shutting_down else "ok"
    )
    return HealthResponse(
        status=status,
        uptime_s=round(state.uptime_s, 3),
        project_open=state.current_project_id is not None,
        active_job_id=state.active_job_id,
    )


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(
        app=__version__,
        engine=__version__,
        schema_version=SCHEMA_VERSION,
        python=platform.python_version(),
        platform=PlatformInfo(
            os=platform.system(),
            arch=platform.machine(),
            python=platform.python_version(),
            frozen=bool(getattr(sys, "frozen", False)),
        ),
    )


@router.post("/shutdown", response_model=ShutdownResponse)
async def shutdown(state: AppState = Depends(get_state)) -> ShutdownResponse:
    """Graceful stop: run the shutdown hooks, then let uvicorn drain and exit.

    The shell waits 10 s for this to finish before it resorts to
    ``TerminateProcess``/SIGTERM (PLAN.md §1.6).
    """
    logger.info("shutdown requested")
    state.shutting_down = True
    await state.run_shutdown_hooks()
    signalled = state.request_shutdown()
    return ShutdownResponse(accepted=True, server_signalled=signalled)
