# SPDX-License-Identifier: Apache-2.0
"""Ingest probe and commit (OPENAPI_SKETCH.md §4).

``POST /ingest/probe`` is cheap and read-only: format, DRM, the PDF text layer,
Calibre availability and an EPUB metadata preview. It does not write ``source/``.

``POST /ingest`` commits an EPUB the user already probed. The project must be
open. The upload is copied to ``source/original.<ext>`` and a working EPUB is
written beside it; the path the user supplied is only read. Calibre conversion
is not this route — anything that is not already an EPUB is
``ebook.unsupported_format``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from praelector.api.v1.projects import ProjectId
from praelector.config import probe_calibre
from praelector.domain.enums import SourceFormat
from praelector.ebook.detect import detect_format
from praelector.ebook.epub_read import Book, iter_toc, read_epub
from praelector.ebook.frontmatter import SkipSpan, skip_candidates
from praelector.ebook.pdf import assert_pdf_text_layer
from praelector.state import AppState, get_state
from praelector.store.chapters import ChapterStore

router = APIRouter(tags=["ingest"])


class IngestProbeRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class IngestDrmStatus(BaseModel):
    detected: bool = False
    reason: str | None = None


class IngestMetadataPreview(BaseModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    language: str | None = None
    chapter_count: int | None = None


class IngestSkipSpanModel(BaseModel):
    block_index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    reason: str


class IngestProbeResponse(BaseModel):
    format: SourceFormat
    needs_conversion: bool
    drm: IngestDrmStatus
    has_text_layer: bool | None = None
    metadata_preview: IngestMetadataPreview | None = None
    #: ``calibre`` when the format is not already an EPUB (EB-03).
    converter: str | None = None
    calibre_available: bool | None = None
    skip_spans: list[IngestSkipSpanModel] = Field(default_factory=list)


@router.post("/projects/{project_id}/ingest/probe", response_model=IngestProbeResponse)
def probe_ingest(
    project_id: ProjectId,
    payload: IngestProbeRequest,
    state: AppState = Depends(get_state),
) -> IngestProbeResponse:
    """Classify ``path`` without copying it or opening the project database for write.

    A missing project is ``project.not_found``. DRM, an empty EPUB and a PDF
    without a text layer are the ebook error codes, not a 200 with a flag.
    """
    state.projects.get(project_id)
    # The file is chosen by the authenticated local user (OPENAPI_SKETCH.md §4).
    # codeql[py/path-injection]
    path = Path(payload.path).expanduser()
    detected = detect_format(path)
    if detected.format is SourceFormat.EPUB:
        return _epub(read_epub(path))
    if detected.format is SourceFormat.PDF:
        assert_pdf_text_layer(path)
        return _needs_calibre(state, detected.format, has_text_layer=True)
    return _needs_calibre(state, detected.format, has_text_layer=None)


def _epub(book: Book) -> IngestProbeResponse:
    texts = [block.text for chapter in book.chapters for block in chapter.blocks]
    titles = [chapter.title for chapter in book.chapters]
    titles.extend(entry.title for entry in iter_toc(book.toc))
    return IngestProbeResponse(
        format=SourceFormat.EPUB,
        needs_conversion=False,
        drm=IngestDrmStatus(detected=False),
        has_text_layer=True,
        metadata_preview=IngestMetadataPreview(
            title=book.title or None,
            authors=list(book.authors),
            language=book.language or None,
            chapter_count=len(book.chapters),
        ),
        skip_spans=[_span(span) for span in skip_candidates(texts, chapter_titles=titles)],
    )


def _needs_calibre(
    state: AppState, format: SourceFormat, *, has_text_layer: bool | None
) -> IngestProbeResponse:
    probe = probe_calibre(state.env.settings)
    return IngestProbeResponse(
        format=format,
        needs_conversion=True,
        drm=IngestDrmStatus(detected=False),
        has_text_layer=has_text_layer,
        converter="calibre",
        calibre_available=bool(probe.present and probe.path),
    )


class IngestCommitRequest(BaseModel):
    """An EPUB path the user already probed. The file is not modified."""

    path: str = Field(min_length=1, max_length=4096)


class IngestCommitResponse(BaseModel):
    chapter_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    original_rel: str
    working_epub_rel: str
    revision: int = Field(ge=0)


@router.post("/projects/{project_id}/ingest", response_model=IngestCommitResponse)
def commit_ingest(
    project_id: ProjectId,
    payload: IngestCommitRequest,
    state: AppState = Depends(get_state),
) -> IngestCommitResponse:
    """Store chapters from an EPUB into the open project.

    DRM and empty text use the same codes as the probe. The project has to be
    open; a closed one is ``project.not_open`` and nothing is copied.
    """
    opened = state.projects.require_open(project_id)
    # The file is chosen by the authenticated local user (OPENAPI_SKETCH.md §4).
    # codeql[py/path-injection]
    path = Path(payload.path).expanduser()
    committed = ChapterStore(opened).commit_epub(path)
    return IngestCommitResponse(
        chapter_count=committed.chapter_count,
        block_count=committed.block_count,
        original_rel=committed.original_rel,
        working_epub_rel=committed.working_epub_rel,
        revision=committed.revision,
    )


def _span(span: SkipSpan) -> IngestSkipSpanModel:
    return IngestSkipSpanModel(
        block_index=span.block_index,
        start=span.start,
        end=span.end,
        reason=span.reason,
    )
