# SPDX-License-Identifier: Apache-2.0
"""Suggestion endpoints for review queue, filtering, and pre-pass execution (AI-02, AI-04, AI-06)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from praelector.api.deps import get_project_manager
from praelector.domain.enums import DetectorKind, SuggestionCategory, SuggestionStatus
from praelector.domain.models import (
    ChapterResponse,
    SuggestionBulkAction,
    SuggestionBulkResponse,
    SuggestionResponse,
    SuggestionUpdate,
)
from praelector.errors import AppError
from praelector.store.project_manager import ProjectManager
from praelector.text.lexicon import LexiconMatcher
from praelector.text.pipeline import DeterministicPrepassPipeline

router = APIRouter(tags=["suggestions"])


@router.get("/projects/{project_id}/suggestions", response_model=list[SuggestionResponse])
async def list_suggestions(
    project_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
    chapter_id: Annotated[str | None, Query()] = None,
    category: Annotated[list[SuggestionCategory] | None, Query()] = None,
    status: Annotated[list[SuggestionStatus] | None, Query()] = None,
    detector: Annotated[list[DetectorKind] | None, Query()] = None,
    min_confidence: Annotated[float | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SuggestionResponse]:
    """Query suggestions for an open project with multi-criteria filtering."""
    repo, _ = pm.get_open_suggestion_repo(project_id)
    return repo.list(
        project_id=project_id,
        chapter_id=chapter_id,
        category=category,
        status=status,
        detector=detector,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
    )


@router.get("/suggestions/{suggestion_id}", response_model=SuggestionResponse)
async def get_suggestion(
    suggestion_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> SuggestionResponse:
    """Retrieve a single suggestion by ID."""
    if pm.active_project_id is None or pm.active_suggestion_repo is None:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project currently open."}
        )

    item = pm.active_suggestion_repo.get_by_id(suggestion_id)
    if item is None:
        raise AppError(
            "suggestion.not_found", status_code=404, detail={"suggestion_id": suggestion_id}
        )
    return item


@router.patch("/suggestions/{suggestion_id}", response_model=SuggestionResponse)
async def update_suggestion(
    suggestion_id: str,
    payload: SuggestionUpdate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> SuggestionResponse:
    """Update status (accept/reject/edit) of a suggestion."""
    if pm.active_project_id is None or pm.active_suggestion_repo is None:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project currently open."}
        )

    updated = pm.active_suggestion_repo.update(suggestion_id, payload)
    if updated is None:
        raise AppError(
            "suggestion.not_found", status_code=404, detail={"suggestion_id": suggestion_id}
        )
    return updated


@router.post("/projects/{project_id}/suggestions/bulk", response_model=SuggestionBulkResponse)
async def bulk_update_suggestions(
    project_id: str,
    payload: SuggestionBulkAction,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> SuggestionBulkResponse:
    """Perform bulk accept or reject on filtered suggestions."""
    repo, _ = pm.get_open_suggestion_repo(project_id)
    batch_id, count = repo.bulk_update_status(
        project_id=project_id,
        action=payload.action,
        category=payload.category,
        status=payload.status,
        chapter_id=payload.chapter_id,
        limit=payload.limit,
    )
    return SuggestionBulkResponse(batch_id=batch_id, affected=count)


@router.post("/projects/{project_id}/suggestions/prepass", response_model=list[SuggestionResponse])
async def run_prepass(
    project_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
    chapter_id: Annotated[str | None, Query()] = None,
) -> list[SuggestionResponse]:
    """Execute deterministic linguistic pre-pass across chapters and save generated suggestions."""
    sug_repo, _ = pm.get_open_suggestion_repo(project_id)
    chap_repo, _ = pm.get_open_chapter_repo(project_id)

    # Load effective lexicon
    lex_repo = pm.get_lexicon_repo(project_id)
    effective_lex = lex_repo.get_effective_lexicon(project_id)
    lexicon_matcher = LexiconMatcher(effective_lex)

    pipeline = DeterministicPrepassPipeline(lexicon_matcher=lexicon_matcher)

    # Chapters to process
    chaps: list[ChapterResponse]
    if chapter_id is not None:
        ch = chap_repo.get_chapter(chapter_id)
        if ch is None:
            raise AppError("chapter.not_found", status_code=404, detail={"chapter_id": chapter_id})
        chaps = [ch]
    else:
        chaps = chap_repo.list_chapters(project_id)

    manifest = pm.get_project(project_id)
    cur_rev = manifest.current_revision

    all_created: list[SuggestionResponse] = []

    for c in chaps:
        blocks = chap_repo.get_blocks(c.id, revision=cur_rev)
        for blk in blocks:
            sugs = pipeline.process_block(
                text=blk.text,
                project_id=project_id,
                chapter_id=c.id,
                block_id=blk.id,
                base_revision=cur_rev,
            )
            if sugs:
                created = sug_repo.create_many(sugs)
                all_created.extend(created)

    return all_created
