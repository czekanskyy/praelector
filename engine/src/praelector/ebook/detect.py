# SPDX-License-Identifier: Apache-2.0
"""Format detection by magic bytes plus extension (EB-01).

EPUB is a zip whose ``mimetype`` member is ``application/epub+zip`` (or a
``.epub`` that is at least a zip). PDF is ``%PDF``. MOBI, AZW and AZW3 share
the Palm ``BOOKMOBI`` header and are told apart by extension; all three, and
PDF, need Calibre (EB-03, EB-09). A magic and an extension that name different
formats is ``ebook.unsupported_format`` rather than a guess.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from praelector.domain.enums import SourceFormat
from praelector.errors import AppError, ErrorCode

_ZIP_MAGICS: Final = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_PALM_MAGICS: Final = (b"BOOKMOBI", b"TEXtREAd")
_EPUB_MIMETYPE: Final = b"application/epub+zip"
_HEAD_BYTES: Final = 128

_EPUB_EXT: Final = frozenset({".epub"})
_PDF_EXT: Final = frozenset({".pdf"})
_MOBI_EXT: Final = frozenset({".mobi", ".prc"})
_AZW3_EXT: Final = frozenset({".azw3"})
_AZW_EXT: Final = frozenset({".azw"})


@dataclass(frozen=True, slots=True)
class FormatDetection:
    """What ``detect_format`` decided, and whether Calibre has to run."""

    format: SourceFormat
    needs_conversion: bool


def detect_format(path: Path) -> FormatDetection:
    """Identify one ebook file. Does not parse it and does not convert it."""
    if not path.is_file():
        raise AppError(
            ErrorCode.EBOOK_UNSUPPORTED_FORMAT,
            detail={"reason": "not_a_file", "suffix": path.suffix.lower()},
            message="ebook path is not a file",
        )
    try:
        head = path.read_bytes()[:_HEAD_BYTES]
    except OSError as exc:
        raise AppError(
            ErrorCode.EBOOK_UNSUPPORTED_FORMAT,
            detail={"reason": "unreadable", "suffix": path.suffix.lower()},
            message="ebook path could not be read",
        ) from exc

    by_magic = _magic_format(head, path)
    by_ext = _extension_format(path.suffix.lower())
    if by_magic is not None and by_ext is not None and by_magic is not by_ext:
        raise AppError(
            ErrorCode.EBOOK_UNSUPPORTED_FORMAT,
            detail={
                "reason": "conflict",
                "magic": by_magic.value,
                "extension": by_ext.value,
            },
            message="ebook magic bytes and extension disagree",
        )
    chosen = by_magic or by_ext
    if chosen is None:
        raise AppError(
            ErrorCode.EBOOK_UNSUPPORTED_FORMAT,
            detail={"reason": "unknown", "suffix": path.suffix.lower()},
            message="ebook format is not supported",
        )
    return FormatDetection(
        format=chosen,
        needs_conversion=chosen is not SourceFormat.EPUB,
    )


def _extension_format(suffix: str) -> SourceFormat | None:
    if suffix in _EPUB_EXT:
        return SourceFormat.EPUB
    if suffix in _PDF_EXT:
        return SourceFormat.PDF
    if suffix in _MOBI_EXT:
        return SourceFormat.MOBI
    if suffix in _AZW3_EXT:
        return SourceFormat.AZW3
    if suffix in _AZW_EXT:
        return SourceFormat.AZW
    return None


def _magic_format(head: bytes, path: Path) -> SourceFormat | None:
    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"%PDF") or stripped.startswith(b"%PDF"):
        return SourceFormat.PDF
    if len(head) >= 68 and head[60:68] in _PALM_MAGICS:
        return _palm_format(path.suffix.lower())
    # A zip named .epub is an EPUB even when ``mimetype`` is missing or not
    # first; the reader then fails closed if the container is absent. Any other
    # zip is an EPUB only when the mimetype member says so.
    if head.startswith(_ZIP_MAGICS) and (
        path.suffix.lower() in _EPUB_EXT or _zip_mimetype_is_epub(path)
    ):
        return SourceFormat.EPUB
    return None


def _palm_format(suffix: str) -> SourceFormat:
    if suffix in _AZW3_EXT:
        return SourceFormat.AZW3
    if suffix in _AZW_EXT:
        return SourceFormat.AZW
    return SourceFormat.MOBI


def _zip_mimetype_is_epub(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                payload = archive.read("mimetype")
            except KeyError:
                return False
    except (zipfile.BadZipFile, OSError):
        return False
    return (
        payload.strip() == _EPUB_MIMETYPE
        or payload.startswith(_EPUB_MIMETYPE + b"\r")
        or (payload.startswith(_EPUB_MIMETYPE + b"\n"))
    )
