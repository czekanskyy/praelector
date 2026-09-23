# SPDX-License-Identifier: Apache-2.0
"""Ingest probe (OPENAPI_SKETCH.md §4).

Cheap and read-only: format, DRM, the PDF text layer, Calibre availability and
an EPUB metadata preview. Persisting chapters would need the chapter and block
tables, which are not in the project schema yet, so this route does not write
``source/`` and does not migrate anything. ``ebook/epub_write.py`` already
knows how to stage ``source/original.<ext>`` and ``source/working.epub`` for
the route that lands with those tables.
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


def _span(span: SkipSpan) -> IngestSkipSpanModel:
    return IngestSkipSpanModel(
        block_index=span.block_index,
        start=span.start,
        end=span.end,
        reason=span.reason,
    )
