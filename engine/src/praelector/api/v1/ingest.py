# SPDX-License-Identifier: Apache-2.0
"""Ebook ingest and source document API router (EB-01..EB-08)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, status

from praelector.api.deps import get_project_manager
from praelector.domain.enums import SourceFormat
from praelector.domain.models import (
    DrmStatus,
    IngestProbeRequest,
    IngestProbeResponse,
    IngestRequest,
    IngestResponse,
    MetadataPreview,
    ProjectSourceResponse,
)
from praelector.ebook.calibre import convert_with_calibre
from praelector.ebook.detect import detect_format
from praelector.ebook.drm import inspect_drm
from praelector.ebook.epub_read import read_epub
from praelector.ebook.epub_write import write_epub
from praelector.ebook.pdf import probe_pdf
from praelector.errors import AppError
from praelector.store.manifest import read_manifest, write_manifest
from praelector.store.project_manager import ProjectManager

router = APIRouter(tags=["ingest"])


@router.post(
    "/projects/{project_id}/ingest/probe",
    response_model=IngestProbeResponse,
    status_code=status.HTTP_200_OK,
)
def probe_ebook_file(
    project_id: str,
    payload: IngestProbeRequest,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> IngestProbeResponse:
    """Probe an ebook file before import to check format, DRM, text layer, and metadata."""
    _ = pm.find_project_dir(project_id)
    path = Path(payload.path)
    if not path.is_file():
        raise AppError("internal.not_found", status_code=404, detail={"path": str(path)})

    # 1. Detect Format
    fmt = detect_format(path)

    # 2. Inspect DRM
    drm_status = DrmStatus(detected=False)
    try:
        inspect_drm(path, format_hint=fmt)
    except AppError as exc:
        if exc.code == "ebook.drm_detected":
            drm_status = DrmStatus(
                detected=True,
                reason=exc.detail.get("reason"),
                file=exc.detail.get("file"),
            )
        else:
            raise

    # 3. PDF Text Layer Probe
    has_text_layer = True
    if fmt == SourceFormat.PDF and not drm_status.detected:
        try:
            pdf_info = probe_pdf(path)
            has_text_layer = pdf_info["has_text_layer"]
        except AppError as exc:
            if exc.code == "ebook.no_text_layer":
                has_text_layer = False
            else:
                raise

    # 4. Extract metadata preview if non-DRM EPUB
    metadata_preview: MetadataPreview | None = None
    if fmt == SourceFormat.EPUB and not drm_status.detected:
        try:
            extracted = read_epub(path)
            metadata_preview = MetadataPreview(
                title=extracted.title,
                authors=extracted.authors,
                language=extracted.language,
                chapter_count=len(extracted.chapters),
                total_chars=extracted.total_char_count,
                cover_detected=bool(extracted.cover_image_bytes),
            )
        except Exception:
            pass

    needs_conversion = fmt in (SourceFormat.PDF, SourceFormat.MOBI, SourceFormat.AZW3)

    return IngestProbeResponse(
        format=fmt,
        needs_conversion=needs_conversion,
        drm=drm_status,
        has_text_layer=has_text_layer,
        metadata_preview=metadata_preview,
    )


@router.post(
    "/projects/{project_id}/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
)
def ingest_ebook_file(
    project_id: str,
    payload: IngestRequest,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> IngestResponse:
    """Import an ebook file into an open project."""
    ch_repo, paths = pm.get_open_chapter_repo(project_id)
    src_path = Path(payload.path)
    if not src_path.is_file():
        raise AppError("internal.not_found", status_code=404, detail={"path": str(src_path)})

    # 1. Format detection & DRM inspection
    fmt = detect_format(src_path)
    inspect_drm(src_path, format_hint=fmt)

    # 2. Text layer check for PDF
    if fmt == SourceFormat.PDF:
        probe_pdf(src_path)

    # 3. Copy original file to source/ directory
    orig_ext = src_path.suffix.lower()
    source_dir = paths.source_dir
    source_dir.mkdir(parents=True, exist_ok=True)
    orig_target = source_dir / f"original{orig_ext}"
    shutil.copy2(src_path, orig_target)
    orig_rel = f"source/original{orig_ext}"

    # 4. Convert to EPUB if needed via Calibre
    converter_info: str | None = None
    epub_to_read = orig_target

    if fmt != SourceFormat.EPUB:
        if not payload.convert.enabled:
            raise AppError(
                "ebook.conversion_required",
                status_code=400,
                detail={
                    "format": fmt.value,
                    "message": "Conversion must be enabled for this format",
                },
            )
        converted_epub = source_dir / "converted.epub"
        convert_with_calibre(orig_target, converted_epub)
        epub_to_read = converted_epub
        converter_info = "calibre"

    # 5. Parse EPUB
    extracted = read_epub(epub_to_read)

    # 6. Save cover image if extracted
    if extracted.cover_image_bytes:
        cover_ext = "jpg" if "jpeg" in (extracted.cover_image_mime or "") else "png"
        cover_path = source_dir / f"cover.{cover_ext}"
        cover_path.write_bytes(extracted.cover_image_bytes)

    # 7. Write working.epub
    working_epub = source_dir / "working.epub"
    write_epub(extracted, working_epub)
    working_rel = "source/working.epub"

    # 8. Insert chapters, blocks, and initial skip spans into SQLite
    ch_repo.insert_ingest_data(
        project_id=project_id,
        extracted_epub=extracted,
        source_format=fmt,
        source_original_rel=orig_rel,
        working_epub_rel=working_rel,
        converter=converter_info,
    )

    # 9. Update manifest
    manifest = read_manifest(paths.manifest)
    manifest.name = extracted.title or manifest.name
    manifest.spoken_language = extracted.language or manifest.spoken_language
    manifest.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_manifest(paths.manifest, manifest)

    return IngestResponse(
        project_id=project_id,
        format=fmt,
        chapter_count=len(extracted.chapters),
        total_chars=extracted.total_char_count,
        working_epub_path=str(working_epub),
    )


@router.get(
    "/projects/{project_id}/source",
    response_model=ProjectSourceResponse,
    status_code=status.HTTP_200_OK,
)
def get_project_source_info(
    project_id: str,
    pm: Annotated[ProjectManager, Depends(get_project_manager)],
) -> ProjectSourceResponse:
    """Retrieve source and working ebook file info for a project."""
    proj = pm.get_project(project_id)
    return ProjectSourceResponse(
        original_path=proj.source_original_rel,
        working_epub_path=proj.working_epub_rel,
        imported_at=proj.updated_at,
        converter=proj.converter,
    )
