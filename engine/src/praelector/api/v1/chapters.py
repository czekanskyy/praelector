# SPDX-License-Identifier: Apache-2.0
"""Chapter tree, plain text and find/replace (OPENAPI_SKETCH.md §5, ED-01…ED-06).

Every route uses the open project. Spoken text matches the print text until
span rows exist; the view is still part of the response so the editor can
switch the label.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

from praelector.api.v1.projects import ProjectId
from praelector.domain.enums import BlockKind
from praelector.state import AppState, get_state
from praelector.store.chapters import ChapterStore, StoredChapter
from praelector.store.projects import OpenProject

router = APIRouter(tags=["chapters"])

ChapterId = Annotated[str, PathParam(min_length=4, max_length=64, pattern=r"^chp_[0-9A-Z]{26}$")]
_CHAPTER_ID = r"^chp_[0-9A-Z]{26}$"
_BLOCK_ID = r"^blk_[0-9A-Z]{26}$"

#: PLAN.md UI-05. The job metrics replace this once a book has been recorded.
_CHARS_PER_AUDIO_SECOND = 14

TextView = Literal["display", "spoken"]


class ChapterTreeItem(BaseModel):
    """One live chapter, in narration order."""

    id: str
    ordinal: int = Field(ge=0)
    title: str
    included: bool
    block_count: int = Field(ge=0)
    char_count: int = Field(ge=0)
    #: Rough narration length at 14 characters per second (PLAN.md UI-05).
    est_audio_s: int = Field(ge=0)


class ChapterTreeResponse(BaseModel):
    revision: int = Field(ge=0)
    chapters: list[ChapterTreeItem]


class PatchChapterRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    included: bool | None = None


class ReorderChaptersRequest(BaseModel):
    order: list[Annotated[str, Field(pattern=_CHAPTER_ID)]] = Field(min_length=1)


class SplitChapterRequest(BaseModel):
    """``offset`` is a character offset into ``block_id`` (ED-01, split at caret)."""

    block_id: Annotated[str, Field(pattern=_BLOCK_ID)]
    offset: int = Field(ge=0)


class SplitChapterResponse(BaseModel):
    revision: int = Field(ge=0)
    chapters: list[ChapterTreeItem]


class MergeChaptersRequest(BaseModel):
    ids: list[Annotated[str, Field(pattern=_CHAPTER_ID)]] = Field(min_length=2, max_length=2)


class MergeChaptersResponse(BaseModel):
    revision: int = Field(ge=0)
    chapter: ChapterTreeItem


class ChapterBlock(BaseModel):
    id: str
    ordinal: int = Field(ge=0)
    kind: BlockKind
    text: str


class ChapterTextResponse(BaseModel):
    view: TextView
    revision: int = Field(ge=0)
    text: str
    blocks: list[ChapterBlock]


class PutChapterTextRequest(BaseModel):
    text: str = Field(max_length=2_000_000)
    base_revision: int = Field(ge=0)


class PutChapterTextResponse(BaseModel):
    """``orphaned_span_ids`` is empty until spans are stored."""

    revision: int = Field(ge=0)
    orphaned_span_ids: list[str]
    text: str
    blocks: list[ChapterBlock]


class ReplaceTextHit(BaseModel):
    chapter_id: str
    block_id: str
    count: int = Field(ge=1)


class ReplaceTextRequest(BaseModel):
    """Case-sensitive literal replace. ``all_chapters`` is what crosses chapters."""

    query: str = Field(min_length=1, max_length=2_000)
    replacement: str = Field(default="", max_length=2_000)
    dry_run: bool = True
    chapter_id: str | None = Field(default=None, pattern=_CHAPTER_ID)
    all_chapters: bool = False


class ReplaceTextResponse(BaseModel):
    count: int = Field(ge=0)
    dry_run: bool
    revision: int | None = Field(default=None, ge=0)
    preview: list[ReplaceTextHit]


def _store_for(state: AppState, project_id: str) -> ChapterStore:
    return ChapterStore(state.projects.require_open(project_id))


def _current_store(state: AppState) -> tuple[OpenProject, ChapterStore]:
    opened = state.projects.require_current()
    return opened, ChapterStore(opened)


def _item(chapter: StoredChapter) -> ChapterTreeItem:
    return ChapterTreeItem(
        id=chapter.id,
        ordinal=chapter.ordinal,
        title=chapter.title,
        included=chapter.included,
        block_count=chapter.block_count,
        char_count=chapter.char_count,
        est_audio_s=chapter.char_count // _CHARS_PER_AUDIO_SECOND,
    )


@router.get("/projects/{project_id}/chapters", response_model=ChapterTreeResponse)
def list_chapters(
    project_id: ProjectId, state: AppState = Depends(get_state)
) -> ChapterTreeResponse:
    tree = _store_for(state, project_id).tree()
    return ChapterTreeResponse(
        revision=tree.revision, chapters=[_item(chapter) for chapter in tree.chapters]
    )


@router.patch("/chapters/{chapter_id}", response_model=ChapterTreeItem)
def patch_chapter(
    chapter_id: ChapterId,
    payload: PatchChapterRequest,
    state: AppState = Depends(get_state),
) -> ChapterTreeItem:
    _opened, store = _current_store(state)
    changes = payload.model_dump(exclude_unset=True)
    chapter = store.update(
        chapter_id,
        title=changes.get("title"),
        included=changes.get("included"),
    )
    return _item(chapter)


@router.post("/projects/{project_id}/chapters/reorder", response_model=ChapterTreeResponse)
def reorder_chapters(
    project_id: ProjectId,
    payload: ReorderChaptersRequest,
    state: AppState = Depends(get_state),
) -> ChapterTreeResponse:
    tree = _store_for(state, project_id).reorder(payload.order)
    return ChapterTreeResponse(
        revision=tree.revision, chapters=[_item(chapter) for chapter in tree.chapters]
    )


@router.post("/chapters/{chapter_id}/split", response_model=SplitChapterResponse)
def split_chapter(
    chapter_id: ChapterId,
    payload: SplitChapterRequest,
    state: AppState = Depends(get_state),
) -> SplitChapterResponse:
    _opened, store = _current_store(state)
    result = store.split(chapter_id, payload.block_id, payload.offset)
    return SplitChapterResponse(
        revision=result.revision,
        chapters=[_item(result.first), _item(result.second)],
    )


@router.post("/projects/{project_id}/chapters/merge", response_model=MergeChaptersResponse)
def merge_chapters(
    project_id: ProjectId,
    payload: MergeChaptersRequest,
    state: AppState = Depends(get_state),
) -> MergeChaptersResponse:
    result = _store_for(state, project_id).merge(payload.ids)
    return MergeChaptersResponse(revision=result.revision, chapter=_item(result.chapter))


@router.get("/chapters/{chapter_id}/text", response_model=ChapterTextResponse)
def get_chapter_text(
    chapter_id: ChapterId,
    state: AppState = Depends(get_state),
    view: Annotated[TextView, Query()] = "display",
) -> ChapterTextResponse:
    _opened, store = _current_store(state)
    loaded = store.text(chapter_id, view)
    return ChapterTextResponse(
        view=view,
        revision=loaded.revision,
        text=loaded.text,
        blocks=[
            ChapterBlock(id=block.id, ordinal=block.ordinal, kind=block.kind, text=block.text)
            for block in loaded.blocks
        ],
    )


@router.put("/chapters/{chapter_id}/text", response_model=PutChapterTextResponse)
def put_chapter_text(
    chapter_id: ChapterId,
    payload: PutChapterTextRequest,
    state: AppState = Depends(get_state),
) -> PutChapterTextResponse:
    _opened, store = _current_store(state)
    committed = store.put_text(chapter_id, payload.text, payload.base_revision)
    return PutChapterTextResponse(
        revision=committed.revision,
        orphaned_span_ids=list(committed.orphaned_span_ids),
        text=committed.text,
        blocks=[
            ChapterBlock(id=block.id, ordinal=block.ordinal, kind=block.kind, text=block.text)
            for block in committed.blocks
        ],
    )


@router.post("/projects/{project_id}/replace", response_model=ReplaceTextResponse)
def replace_text(
    project_id: ProjectId,
    payload: ReplaceTextRequest,
    state: AppState = Depends(get_state),
) -> ReplaceTextResponse:
    outcome = _store_for(state, project_id).replace(
        query=payload.query,
        replacement=payload.replacement,
        dry_run=payload.dry_run,
        chapter_id=payload.chapter_id,
        all_chapters=payload.all_chapters,
    )
    return ReplaceTextResponse(
        count=outcome.count,
        dry_run=outcome.dry_run,
        revision=outcome.revision,
        preview=[
            ReplaceTextHit(chapter_id=hit.chapter_id, block_id=hit.block_id, count=hit.count)
            for hit in outcome.preview
        ],
    )
