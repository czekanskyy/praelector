# SPDX-License-Identifier: Apache-2.0
"""Project management and workspace API endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from praelector.api.deps import get_project_manager
from praelector.domain.models import (
    ProjectCreate,
    ProjectOpenResponse,
    ProjectResponse,
    ProjectStats,
    ProjectSummary,
    ProjectUpdate,
)
from praelector.store.project_manager import ProjectManager

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
def list_projects(
    manager: Annotated[ProjectManager, Depends(get_project_manager)],
) -> list[ProjectSummary]:
    """Scan configured projects directory and list available projects."""
    return manager.list_projects()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    manager: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ProjectResponse:
    """Create a new project workspace, manifest, and SQLite database with baseline schema."""
    return manager.create_project(payload)


@router.get("/{pid}", response_model=ProjectResponse)
def get_project(
    pid: str,
    manager: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ProjectResponse:
    """Retrieve details, counts, and settings for a single project."""
    return manager.get_project(pid)


@router.patch("/{pid}", response_model=ProjectResponse)
def update_project(
    pid: str,
    payload: ProjectUpdate,
    manager: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ProjectResponse:
    """Update project metadata, voice mode, or backend settings."""
    return manager.update_project(pid, payload)


@router.post("/{pid}/open", response_model=ProjectOpenResponse)
def open_project(
    pid: str,
    manager: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ProjectOpenResponse:
    """Acquire project lock, apply any pending migrations, and mark project as active."""
    project = manager.open_project(pid)
    return ProjectOpenResponse(project=project, status="opened")


@router.post("/{pid}/close")
def close_project(
    pid: str,
    manager: Annotated[ProjectManager, Depends(get_project_manager)],
) -> dict[str, str]:
    """Release exclusive lock and close active project."""
    manager.close_project(pid)
    return {"status": "closed"}


@router.delete("/{pid}")
def delete_project(
    pid: str,
    manager: Annotated[ProjectManager, Depends(get_project_manager)],
    delete_files: Annotated[bool, Query()] = False,
) -> dict[str, str]:
    """Delete project reference and optionally remove project directory from disk."""
    manager.delete_project(pid, delete_files=delete_files)
    return {"status": "deleted"}


@router.get("/{pid}/stats", response_model=ProjectStats)
def get_project_stats(
    pid: str,
    manager: Annotated[ProjectManager, Depends(get_project_manager)],
) -> dict[str, Any]:
    """Retrieve aggregated suggestion, chapter, word, and character counts."""
    stats = manager.get_project_stats(pid)
    return stats.model_dump()
