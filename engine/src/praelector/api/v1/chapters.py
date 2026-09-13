# SPDX-License-Identifier: Apache-2.0
"""Chapters, Blocks, and Spans API router (ED-01..ED-09)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from praelector.api.deps import get_project_manager
from praelector.domain.models import (
    BlockResponse,
    ChapterMergeRequest,
    ChapterReorderRequest,
    ChapterResponse,
    ChapterSplitRequest,
    ChapterTextResponse,
    ChapterTextUpdate,
    ChapterTextUpdateResponse,
    ChapterUpdate,
    ReplaceRequest,
    ReplaceResponse,
    SearchRequest,
    SearchResponse,
    SpanCreate,
    SpanResponse,
    SpanUpdate,
)
from praelector.errors import AppError
from praelector.store.manifest import read_manifest, write_manifest
from praelector.store.project_manager import ProjectManager

router = APIRouter(tags=["chapters"])


# ---------------------------------------------------------------------------
# Chapter Tree Endpoints (ED-01)
# ---------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/chapters",
    response_model=list[ChapterResponse],
    status_code=status.HTTP_200_OK,
)
def list_chapters(
    project_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> list[ChapterResponse]:
    """List all chapters in their reading sequence."""
    ch_repo, _ = pm.get_open_chapter_repo(project_id)
    return ch_repo.list_chapters(project_id)


@router.patch(
    "/chapters/{chapter_id}",
    response_model=ChapterResponse,
    status_code=status.HTTP_200_OK,
)
def update_chapter(
    chapter_id: str,
    payload: ChapterUpdate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ChapterResponse:
    """Update chapter title or included status."""
    if not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    return pm.active_chapter_repo.update_chapter(
        chapter_id, title=payload.title, included=payload.included
    )


@router.post(
    "/projects/{project_id}/chapters/reorder",
    response_model=list[ChapterResponse],
    status_code=status.HTTP_200_OK,
)
def reorder_chapters(
    project_id: str,
    payload: ChapterReorderRequest,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> list[ChapterResponse]:
    """Reorder chapter reading sequence."""
    ch_repo, _ = pm.get_open_chapter_repo(project_id)
    return ch_repo.reorder_chapters(project_id, payload.order)


@router.post(
    "/chapters/{chapter_id}/split",
    response_model=list[ChapterResponse],
    status_code=status.HTTP_200_OK,
)
def split_chapter(
    chapter_id: str,
    payload: ChapterSplitRequest,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> list[ChapterResponse]:
    """Split a chapter at a block ID and character offset into two chapters."""
    if not pm.active_project_id or not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    proj_id = pm.active_project_id
    ch1, ch2 = pm.active_chapter_repo.split_chapter(
        proj_id, chapter_id, payload.block_id, offset=payload.offset
    )
    return [ch1, ch2]


@router.post(
    "/projects/{project_id}/chapters/merge",
    response_model=ChapterResponse,
    status_code=status.HTTP_200_OK,
)
def merge_chapters(
    project_id: str,
    payload: ChapterMergeRequest,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ChapterResponse:
    """Merge multiple chapters into the first chapter."""
    ch_repo, _ = pm.get_open_chapter_repo(project_id)
    return ch_repo.merge_chapters(project_id, payload.ids)


# ---------------------------------------------------------------------------
# Chapter Plain Text & Editor (ED-02, ED-06, ED-07)
# ---------------------------------------------------------------------------


@router.get(
    "/chapters/{chapter_id}/blocks",
    response_model=list[BlockResponse],
    status_code=status.HTTP_200_OK,
)
def list_chapter_blocks(
    chapter_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> list[BlockResponse]:
    """Get all semantic blocks for a chapter at current revision."""
    if not pm.active_project_id or not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    proj = pm.get_project(pm.active_project_id)
    return pm.active_chapter_repo.get_blocks(chapter_id, revision=proj.current_revision)


@router.get(
    "/chapters/{chapter_id}/text",
    response_model=ChapterTextResponse,
    status_code=status.HTTP_200_OK,
)
def get_chapter_text(
    chapter_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
    view: str = Query("display", pattern="^(display|spoken)$"),
) -> ChapterTextResponse:
    """Get chapter plain text formatted for display or spoken preview."""
    if not pm.active_project_id or not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    proj = pm.get_project(pm.active_project_id)
    return pm.active_chapter_repo.get_chapter_text(
        chapter_id, revision=proj.current_revision, view=view
    )


@router.put(
    "/chapters/{chapter_id}/text",
    response_model=ChapterTextUpdateResponse,
    status_code=status.HTTP_200_OK,
)
def update_chapter_text(
    chapter_id: str,
    payload: ChapterTextUpdate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ChapterTextUpdateResponse:
    """Commit plain text changes back to the block and span models."""
    if not pm.active_project_id or not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    proj_id = pm.active_project_id
    new_rev, orphaned = pm.active_chapter_repo.update_chapter_text(
        proj_id, chapter_id, payload.text, base_revision=payload.base_revision
    )
    paths = pm.find_project_dir(proj_id)
    manifest = read_manifest(paths.manifest)
    manifest.current_revision = new_rev
    write_manifest(paths.manifest, manifest)
    return ChapterTextUpdateResponse(revision=new_rev, orphaned_span_ids=orphaned)


# ---------------------------------------------------------------------------
# Spans (ED-03, ED-04, ED-09)
# ---------------------------------------------------------------------------


@router.get(
    "/chapters/{chapter_id}/spans",
    response_model=list[SpanResponse],
    status_code=status.HTTP_200_OK,
)
def list_chapter_spans(
    chapter_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> list[SpanResponse]:
    """Get all active spans for a chapter at current revision."""
    if not pm.active_project_id or not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    proj = pm.get_project(pm.active_project_id)
    return pm.active_chapter_repo.get_spans(chapter_id, revision=proj.current_revision)


@router.post(
    "/chapters/{chapter_id}/spans",
    response_model=SpanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_span(
    chapter_id: str,
    payload: SpanCreate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> SpanResponse:
    """Create a manual span annotation on a block."""
    if not pm.active_project_id or not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    _ = pm.active_chapter_repo.get_chapter(chapter_id)
    proj = pm.get_project(pm.active_project_id)
    return pm.active_chapter_repo.create_span(
        payload=payload, current_revision=proj.current_revision
    )


@router.patch(
    "/spans/{span_id}",
    response_model=SpanResponse,
    status_code=status.HTTP_200_OK,
)
def update_span(
    span_id: str,
    payload: SpanUpdate,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> SpanResponse:
    """Update properties of an existing span."""
    if not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    return pm.active_chapter_repo.update_span(span_id, payload)


@router.delete(
    "/spans/{span_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_span(
    span_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> None:
    """Delete a span annotation."""
    if not pm.active_chapter_repo:
        raise AppError(
            "project.not_open", status_code=400, detail={"message": "No project is open"}
        )
    pm.active_chapter_repo.delete_span(span_id)


# ---------------------------------------------------------------------------
# Search and Replace (ED-05)
# ---------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
)
def search_project_text(
    project_id: str,
    payload: SearchRequest,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> SearchResponse:
    """Search for text across chapter or entire book."""
    ch_repo, _ = pm.get_open_chapter_repo(project_id)
    return ch_repo.search_text(
        project_id,
        query=payload.query,
        regex=payload.regex,
        case_sensitive=payload.case_sensitive,
        scope=payload.scope,
        chapter_id=payload.chapter_id,
    )


@router.post(
    "/projects/{project_id}/replace",
    response_model=ReplaceResponse,
    status_code=status.HTTP_200_OK,
)
def replace_project_text(
    project_id: str,
    payload: ReplaceRequest,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ReplaceResponse:
    """Find and replace text with dry-run support."""
    ch_repo, _ = pm.get_open_chapter_repo(project_id)
    res = ch_repo.replace_text(
        project_id,
        query=payload.query,
        replacement=payload.replacement,
        regex=payload.regex,
        case_sensitive=payload.case_sensitive,
        scope=payload.scope,
        chapter_id=payload.chapter_id,
        dry_run=payload.dry_run,
    )
    if not payload.dry_run and res.revision is not None:
        paths = pm.find_project_dir(project_id)
        manifest = read_manifest(paths.manifest)
        manifest.current_revision = res.revision
        write_manifest(paths.manifest, manifest)
    return res
