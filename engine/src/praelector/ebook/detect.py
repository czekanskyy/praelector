# SPDX-License-Identifier: Apache-2.0
"""Ebook format detection by magic bytes and extension (EB-01)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from praelector.domain.enums import SourceFormat
from praelector.errors import AppError


def detect_format(file_path: Path | str) -> SourceFormat:
    """Detect ebook format using magic bytes with extension fallback.

    Args:
        file_path: Path to the ebook file.

    Returns:
        Detected SourceFormat enum.

    Raises:
        AppError: If the file is empty, inaccessible, or in an unsupported format.
    """
    path = Path(file_path)
    if not path.is_file():
        raise AppError(
            "internal.not_found",
            status_code=404,
            detail={"path": str(path), "message": "File does not exist"},
        )

    file_size = path.stat().st_size
    if file_size == 0:
        raise AppError(
            "ebook.empty_text",
            status_code=422,
            detail={"path": str(path), "message": "File is empty (0 bytes)"},
        )

    with open(path, "rb") as f:
        header = f.read(2048)

    ext = path.suffix.lower()

    # 1. PDF Detection: starts with %PDF-
    if header.startswith(b"%PDF-") or b"%PDF-" in header[:1024]:
        return SourceFormat.PDF

    # 2. EPUB Detection: ZIP archive containing mimetype application/epub+zip
    if header.startswith(b"PK\x03\x04"):
        # Check if valid EPUB zip
        if zipfile.is_zipfile(path):
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    # An EPUB standard requires 'mimetype' as uncompressed first file
                    if "mimetype" in zf.namelist():
                        mime_data = zf.read("mimetype").decode("ascii", errors="ignore").strip()
                        if "application/epub+zip" in mime_data:
                            return SourceFormat.EPUB
                    if "META-INF/container.xml" in zf.namelist():
                        return SourceFormat.EPUB
            except Exception:
                pass
        if ext == ".epub":
            return SourceFormat.EPUB

    # 3. MOBI / AZW3 Detection (PalmDOC / Mobipocket)
    # Palm database format: offset 60-67 typically has type 'BOOK' and creator 'MOBI'
    if len(header) >= 68:
        db_type = header[60:64]
        db_creator = header[64:68]
        if db_type == b"BOOK" and db_creator == b"MOBI":
            # Distinguish MOBI vs AZW3 (KF8)
            if b"KF8" in header[:512] or ext == ".azw3":
                return SourceFormat.AZW3
            return SourceFormat.MOBI

    if b"BOOKMOBI" in header[:512]:
        if b"KF8" in header[:512] or ext == ".azw3":
            return SourceFormat.AZW3
        return SourceFormat.MOBI

    if b"TPZ" in header[:16] or ext == ".tpz":
        return SourceFormat.AZW3

    # Fallback by extension if magic bytes were ambiguous but non-corrupted
    if ext == ".epub":
        return SourceFormat.EPUB
    if ext == ".pdf":
        return SourceFormat.PDF
    if ext == ".mobi":
        return SourceFormat.MOBI
    if ext in (".azw3", ".azw"):
        return SourceFormat.AZW3

    raise AppError(
        "ebook.unsupported_format",
        status_code=422,
        detail={
            "path": str(path),
            "extension": ext,
            "message": f"Unsupported ebook format: {ext or 'unknown'}",
        },
    )
