# SPDX-License-Identifier: Apache-2.0
"""Ebook ingest, format detection, DRM inspection, reading and writing."""

from __future__ import annotations

from praelector.ebook.blocks import ExtractedBlock, extract_blocks_from_xhtml, normalize_block_text
from praelector.ebook.calibre import convert_with_calibre, find_calibre_binary, probe_calibre
from praelector.ebook.detect import detect_format
from praelector.ebook.drm import inspect_drm, inspect_epub_drm, inspect_mobi_drm, inspect_pdf_drm
from praelector.ebook.epub_read import ExtractedChapter, ExtractedEpub, read_epub
from praelector.ebook.epub_write import write_epub
from praelector.ebook.frontmatter import SkipCandidate, detect_skip_candidates
from praelector.ebook.pdf import probe_pdf

__all__ = [
    "ExtractedBlock",
    "ExtractedChapter",
    "ExtractedEpub",
    "SkipCandidate",
    "convert_with_calibre",
    "detect_format",
    "detect_skip_candidates",
    "extract_blocks_from_xhtml",
    "find_calibre_binary",
    "inspect_drm",
    "inspect_epub_drm",
    "inspect_mobi_drm",
    "inspect_pdf_drm",
    "normalize_block_text",
    "probe_calibre",
    "probe_pdf",
    "read_epub",
    "write_epub",
]
