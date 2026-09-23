# SPDX-License-Identifier: Apache-2.0
"""Projects: the Library's backing API (OPENAPI_SKETCH.md §3, PRD §5.1-§5.2)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

from praelector.domain.enums import VoiceMode
from praelector.domain.models import ProjectDetail, ProjectSummary
from praelector.state import AppState, get_state
from praelector.store.projects import ProjectPatch

router = APIRouter(tags=["projects"])

ProjectId = Annotated[
    str, PathParam(min_length=4, max_length=64, pattern=r"^[a-z]{3}_[0-9A-Z]{26}$")
]


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    #: Optional override for where the project directory is created.
    dir: str | None = None
    voice_mode: VoiceMode = VoiceMode.SINGLE
    spoken_language: str = Field(default="pl", min_length=2, max_length=8)
    backend_id: str | None = None


class PatchProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    voice_mode: VoiceMode | None = None
    backend_id: str | None = None
    spoken_language: str | None = Field(default=None, min_length=2, max_length=8)
    #: LM-05 / NF-02: the only switch that lets book text leave the machine.
    cloud_llm_enabled: bool | None = None


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]
    projects_dir: str
    open_project_id: str | None = None


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(state: AppState = Depends(get_state)) -> ProjectListResponse:
    return ProjectListResponse(
        projects=state.projects.list_summaries(),
        projects_dir=state.env.paths.projects_dir.as_posix(),
        open_project_id=state.current_project_id,
    )


@router.post("/projects", response_model=ProjectDetail, status_code=201)
async def create_project(
    payload: CreateProjectRequest,
    state: AppState = Depends(get_state),
) -> ProjectDetail:
    """Create the directory, manifest and an empty database. Does not ingest."""
    # The folder is chosen by the authenticated local user (PRD §5.2).
    # codeql[py/path-injection]
    chosen = Path(payload.dir).expanduser() if payload.dir else None
    return state.projects.create(
        name=payload.name,
        voice_mode=payload.voice_mode,
        spoken_language=payload.spoken_language,
        backend_id=payload.backend_id,
        directory=chosen,
    )


@router.get("/projects/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: ProjectId, state: AppState = Depends(get_state)) -> ProjectDetail:
    return state.projects.get(project_id)


@router.patch("/projects/{project_id}", response_model=ProjectDetail)
async def patch_project(
    project_id: ProjectId,
    payload: PatchProjectRequest,
    state: AppState = Depends(get_state),
) -> ProjectDetail:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    # `cloud_llm_enabled: false` is a meaningful change, so it must survive the
    # exclude_none above.
    if payload.cloud_llm_enabled is not None:
        changes["cloud_llm_enabled"] = payload.cloud_llm_enabled
    return state.projects.patch(project_id, ProjectPatch(**changes))


@router.post("/projects/{project_id}/open", response_model=ProjectDetail)
async def open_project(
    project_id: ProjectId, state: AppState = Depends(get_state)
) -> ProjectDetail:
    """Acquire ``project.lock``, migrate forward, and hold the database open."""
    state.projects.open(project_id)
    return state.projects.get(project_id)


@router.post("/projects/{project_id}/close", status_code=204)
async def close_project(project_id: ProjectId, state: AppState = Depends(get_state)) -> None:
    state.projects.close(project_id)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: ProjectId,
    state: AppState = Depends(get_state),
    delete_files: Annotated[
        bool,
        Query(description="true removes the whole directory, rendered audio included"),
    ] = False,
) -> None:
    state.projects.delete(project_id, delete_files=delete_files)
