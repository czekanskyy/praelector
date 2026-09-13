# SPDX-License-Identifier: Apache-2.0
"""PDF text-layer probe using pypdf (EB-04)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader

from praelector.errors import AppError


def probe_pdf(file_path: Path | str) -> dict[str, Any]:
    """Probe a PDF document for an extractable text layer.

    Inspects the first 5 pages. If fewer than 200 total characters can be extracted,
    it rejects the file with 'ebook.no_text_layer' (no OCR in v1).

    Args:
        file_path: Path to the PDF file.

    Returns:
        Dictionary with probe metrics: has_text_layer, page_count, chars_extracted.

    Raises:
        AppError: If encrypted ('ebook.drm_detected'), corrupt, or lacks a text layer ('ebook.no_text_layer').
    """
    path = Path(file_path)
    if not path.is_file():
        raise AppError("internal.not_found", status_code=404, detail={"path": str(path)})

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise AppError(
            "ebook.corrupt",
            status_code=422,
            detail={"message": f"Failed to read PDF file: {exc}"},
        ) from exc

    if reader.is_encrypted:
        raise AppError(
            "ebook.drm_detected",
            status_code=422,
            detail={
                "reason": "pdf_encrypted",
                "message": "PDF file is encrypted or password-protected.",
            },
        )

    page_count = len(reader.pages)
    if page_count == 0:
        raise AppError(
            "ebook.empty_text",
            status_code=422,
            detail={"message": "PDF document contains 0 pages."},
        )

    pages_to_probe = min(5, page_count)
    total_chars = 0

    for i in range(pages_to_probe):
        try:
            page_text = reader.pages[i].extract_text() or ""
            total_chars += len(page_text.strip())
        except Exception:
            continue

    if total_chars < 200:
        raise AppError(
            "ebook.no_text_layer",
            status_code=422,
            detail={
                "page_count": page_count,
                "pages_probed": pages_to_probe,
                "chars_extracted": total_chars,
                "message": (
                    f"PDF document lacks an extractable text layer (found {total_chars} "
                    f"characters in the first {pages_to_probe} pages). OCR is not supported in v1."
                ),
            },
        )

    return {
        "has_text_layer": True,
        "page_count": page_count,
        "chars_extracted": total_chars,
    }
