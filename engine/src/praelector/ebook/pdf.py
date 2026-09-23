# SPDX-License-Identifier: Apache-2.0
"""PDF text-layer probe (EB-04). No OCR.

Fewer than 200 extractable characters across the first five pages is
``ebook.no_text_layer``. A user password refuses with ``ebook.drm_detected``.
An owner-password restriction that opens with the empty user password is not
DRM: those files still have a text layer, and no other password is ever tried.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, NoReturn

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from praelector.errors import AppError, ErrorCode

TEXT_LAYER_MIN_CHARS: Final = 200
TEXT_LAYER_PAGES: Final = 5


def assert_pdf_text_layer(path: Path) -> int:
    """Return the extractable character count, or raise ``ebook.no_text_layer``."""
    count = pdf_text_characters(path)
    if count < TEXT_LAYER_MIN_CHARS:
        raise AppError(
            ErrorCode.EBOOK_NO_TEXT_LAYER,
            detail={"characters": count, "pages": TEXT_LAYER_PAGES},
            message="pdf has no text layer",
        )
    return count


def pdf_text_characters(path: Path) -> int:
    """Non-whitespace characters from the first five pages. Raises on DRM or a broken file."""
    reader = _open(path)
    total = 0
    for index, page in enumerate(reader.pages):
        if index >= TEXT_LAYER_PAGES:
            break
        try:
            extracted = page.extract_text() or ""
        except (PdfReadError, ValueError, KeyError, TypeError) as exc:
            # One unreadable page is an empty page, not a crashed probe. A
            # password wall was already refused in ``_open``.
            if _is_encrypted_error(exc):
                _refuse_drm()
            extracted = ""
        total += _characters(extracted)
    return total


def _open(path: Path) -> PdfReader:
    try:
        reader = PdfReader(path, strict=False)
    except (PdfReadError, OSError, ValueError) as exc:
        if _is_encrypted_error(exc):
            _refuse_drm()
        raise _parse_failed(exc) from exc
    if reader.is_encrypted and not _unlock_empty_user_password(reader):
        _refuse_drm()
    return reader


def _unlock_empty_user_password(reader: PdfReader) -> bool:
    """True when the file has no user password.

    ``decrypt("")`` is the documented way to open a permissions-only PDF. It is
    not a key search: any other password, including one the caller might know,
    is out of scope (EB-01).
    """
    try:
        return reader.decrypt("") != 0
    except (PdfReadError, OSError, ValueError) as exc:
        if _is_encrypted_error(exc):
            return False
        raise _parse_failed(exc) from exc


def _is_encrypted_error(exc: BaseException) -> bool:
    return type(exc).__name__ in {"FileNotDecryptedError", "WrongPasswordError"}


def _refuse_drm() -> NoReturn:
    raise AppError(
        ErrorCode.EBOOK_DRM_DETECTED,
        detail={"format": "pdf", "reason": "encrypted"},
        message="pdf is encrypted",
    )


def _parse_failed(exc: BaseException) -> AppError:
    return AppError(
        ErrorCode.EBOOK_PARSE_FAILED,
        detail={"reason": "pdf", "type": type(exc).__name__},
        message=f"pdf could not be read: {type(exc).__name__}",
    )


def _characters(text: str) -> int:
    return sum(1 for char in text if not char.isspace())
