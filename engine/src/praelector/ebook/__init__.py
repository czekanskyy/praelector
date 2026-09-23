# SPDX-License-Identifier: Apache-2.0
"""Ebook ingest: detect, refuse DRM, read and write EPUB (EB-01…EB-09, D-01).

The reader and writer are hand-rolled on ``zipfile`` and the stdlib XML parser.
EbookLib is AGPL-3.0 and is not a dependency.
"""

from __future__ import annotations

from praelector.ebook.blocks import Block, SourceRef, blocks_from_xhtml
from praelector.ebook.calibre import convert_to_epub, locate_ebook_convert
from praelector.ebook.detect import FormatDetection, detect_format
from praelector.ebook.epub_read import Book, Chapter, Cover, TocEntry, read_epub
from praelector.ebook.epub_write import render_epub, stage_epub, write_epub
from praelector.ebook.frontmatter import SkipSpan, skip_candidates
from praelector.ebook.pdf import assert_pdf_text_layer

__all__ = [
    "Block",
    "Book",
    "Chapter",
    "Cover",
    "FormatDetection",
    "SkipSpan",
    "SourceRef",
    "TocEntry",
    "assert_pdf_text_layer",
    "blocks_from_xhtml",
    "convert_to_epub",
    "detect_format",
    "locate_ebook_convert",
    "read_epub",
    "render_epub",
    "skip_candidates",
    "stage_epub",
    "write_epub",
]
