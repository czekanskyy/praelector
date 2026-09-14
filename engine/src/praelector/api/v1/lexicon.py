# SPDX-License-Identifier: Apache-2.0
"""Lexicon endpoints for global and project-level pronunciation rules (AI-09)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from praelector.api.deps import get_project_manager
from praelector.domain.models import (
    LexiconEntryCreate,
    LexiconEntryResponse,
    LexiconEntryUpdate,
)
from praelector.errors import AppError
from praelector.store.project_manager import ProjectManager

router = APIRouter(tags=["lexicon"])


# Global Lexicon
@router.get("/lexicon", response_model=list[LexiconEntryResponse])
async def list_global_lexicon(
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> list[LexiconEntryResponse]:
    """List all global pronunciation lexicon rules."""
    repo = pm.get_lexicon_repo()
    return repo.list_entries(project_id=None)


@router.post("/lexicon", response_model=LexiconEntryResponse, status_code=201)
@router.put("/lexicon", response_model=LexiconEntryResponse)
async def create_global_lexicon_entry(
    payload: LexiconEntryCreate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> LexiconEntryResponse:
    """Add a pronunciation rule to the global lexicon."""
    repo = pm.get_lexicon_repo()
    return repo.create_entry(payload, project_id=None)


@router.patch("/lexicon/{entry_id}", response_model=LexiconEntryResponse)
async def update_global_lexicon_entry(
    entry_id: str,
    payload: LexiconEntryUpdate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> LexiconEntryResponse:
    """Update an existing global lexicon rule."""
    repo = pm.get_lexicon_repo()
    res = repo.update_entry(entry_id, payload, project_id=None)
    if res is None:
        raise AppError("lexicon.not_found", status_code=404, detail={"entry_id": entry_id})
    return res


@router.delete("/lexicon/{entry_id}", status_code=204)
async def delete_global_lexicon_entry(
    entry_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> None:
    """Delete a rule from the global lexicon."""
    repo = pm.get_lexicon_repo()
    deleted = repo.delete_entry(entry_id, project_id=None)
    if not deleted:
        raise AppError("lexicon.not_found", status_code=404, detail={"entry_id": entry_id})


# Project Lexicon
@router.get("/projects/{project_id}/lexicon", response_model=list[LexiconEntryResponse])
async def list_project_lexicon(
    project_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
    effective: Annotated[
        bool, Query(description="If true, returns merged global + project rules")
    ] = True,
) -> list[LexiconEntryResponse]:
    """List lexicon rules for a project (optionally merged with global)."""
    repo = pm.get_lexicon_repo(project_id)
    if effective:
        return repo.get_effective_lexicon(project_id)
    return repo.list_entries(project_id=project_id)


@router.post("/projects/{project_id}/lexicon", response_model=LexiconEntryResponse, status_code=201)
@router.put("/projects/{project_id}/lexicon", response_model=LexiconEntryResponse)
async def create_project_lexicon_entry(
    project_id: str,
    payload: LexiconEntryCreate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> LexiconEntryResponse:
    """Add a pronunciation rule to a specific project's lexicon."""
    repo = pm.get_lexicon_repo(project_id)
    return repo.create_entry(payload, project_id=project_id)


@router.patch("/projects/{project_id}/lexicon/{entry_id}", response_model=LexiconEntryResponse)
async def update_project_lexicon_entry(
    project_id: str,
    entry_id: str,
    payload: LexiconEntryUpdate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> LexiconEntryResponse:
    """Update a project-specific lexicon rule."""
    repo = pm.get_lexicon_repo(project_id)
    res = repo.update_entry(entry_id, payload, project_id=project_id)
    if res is None:
        raise AppError("lexicon.not_found", status_code=404, detail={"entry_id": entry_id})
    return res


@router.delete("/projects/{project_id}/lexicon/{entry_id}", status_code=204)
async def delete_project_lexicon_entry(
    project_id: str,
    entry_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> None:
    """Delete a rule from a project's lexicon."""
    repo = pm.get_lexicon_repo(project_id)
    deleted = repo.delete_entry(entry_id, project_id=project_id)
    if not deleted:
        raise AppError("lexicon.not_found", status_code=404, detail={"entry_id": entry_id})
