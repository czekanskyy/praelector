# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ebook ingest, format detection, DRM refusal, EPUB reading and writing."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from praelector.domain.enums import BlockKind, SourceFormat
from praelector.ebook.blocks import extract_blocks_from_xhtml, normalize_block_text
from praelector.ebook.detect import detect_format
from praelector.ebook.drm import inspect_drm
from praelector.ebook.epub_read import read_epub
from praelector.ebook.epub_write import write_epub
from praelector.ebook.frontmatter import detect_skip_candidates
from praelector.ebook.pdf import probe_pdf
from praelector.errors import AppError
from tests.fixtures.builders import (
    create_drm_encrypted_epub,
    create_empty_text_epub,
    create_encrypted_pdf,
    create_epub2_minimal,
    create_epub3_minimal,
    create_epub3_polish_novel,
    create_font_obfuscated_epub,
    create_no_text_layer_pdf,
    create_text_layer_pdf,
)


def test_detect_format_epub(tmp_path: Path) -> None:
    """Format detection correctly identifies EPUB 2 and EPUB 3 archives."""
    epub2 = create_epub2_minimal(tmp_path / "book2.epub")
    epub3 = create_epub3_minimal(tmp_path / "book3.epub")

    assert detect_format(epub2) == SourceFormat.EPUB
    assert detect_format(epub3) == SourceFormat.EPUB


def test_detect_format_pdf(tmp_path: Path) -> None:
    """Format detection correctly identifies PDF files."""
    pdf = create_text_layer_pdf(tmp_path / "document.pdf")
    assert detect_format(pdf) == SourceFormat.PDF


def test_detect_format_errors(tmp_path: Path) -> None:
    """Format detection fails on missing, empty, or unsupported files."""
    # 1. Missing file
    with pytest.raises(AppError) as exc_info:
        detect_format(tmp_path / "nonexistent.epub")
    assert exc_info.value.code == "internal.not_found"

    # 2. Empty file
    empty_file = tmp_path / "empty.txt"
    empty_file.write_bytes(b"")
    with pytest.raises(AppError) as exc_info:
        detect_format(empty_file)
    assert exc_info.value.code == "ebook.empty_text"

    # 3. Unsupported format
    unsupported = tmp_path / "image.png"
    unsupported.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    with pytest.raises(AppError) as exc_info:
        detect_format(unsupported)
    assert exc_info.value.code == "ebook.unsupported_format"


def test_drm_refusal_content_encryption(tmp_path: Path) -> None:
    """EPUB with encrypted content (DRM) is rejected with ebook.drm_detected."""
    drm_epub = create_drm_encrypted_epub(tmp_path / "drm_content.epub", mode="content")

    with pytest.raises(AppError) as exc_info:
        inspect_drm(drm_epub)
    assert exc_info.value.code == "ebook.drm_detected"
    assert exc_info.value.detail.get("reason") == "content_encrypted"


def test_drm_refusal_marker_files(tmp_path: Path) -> None:
    """EPUB with sinf.xml or rights.xml DRM marker files is rejected."""
    sinf_epub = create_drm_encrypted_epub(tmp_path / "drm_sinf.epub", mode="sinf")
    with pytest.raises(AppError) as exc_info:
        inspect_drm(sinf_epub)
    assert exc_info.value.code == "ebook.drm_detected"
    assert exc_info.value.detail.get("reason") == "drm_metadata_present"


def test_font_obfuscation_allowed(tmp_path: Path) -> None:
    """Legitimate font obfuscation is NOT rejected as DRM (EB-01, EB-02)."""
    font_epub = create_font_obfuscated_epub(tmp_path / "font_obfuscated.epub")

    # Should succeed without raising AppError
    inspect_drm(font_epub)
    extracted = read_epub(font_epub)
    assert len(extracted.chapters) == 2


def test_pdf_drm_refusal(tmp_path: Path) -> None:
    """Encrypted PDF files are rejected with ebook.drm_detected."""
    enc_pdf = create_encrypted_pdf(tmp_path / "protected.pdf")
    with pytest.raises(AppError) as exc_info:
        probe_pdf(enc_pdf)
    assert exc_info.value.code == "ebook.drm_detected"
    assert exc_info.value.detail.get("reason") == "pdf_encrypted"


def test_pdf_text_layer_probe(tmp_path: Path) -> None:
    """PDF text layer probe accepts readable PDF and rejects PDF without text layer."""
    # 1. No text layer (< 200 chars across first 5 pages)
    blank_pdf = create_no_text_layer_pdf(tmp_path / "blank.pdf")
    with pytest.raises(AppError) as exc_info:
        probe_pdf(blank_pdf)
    assert exc_info.value.code == "ebook.no_text_layer"

    # 2. Text layer present
    text_pdf = create_text_layer_pdf(tmp_path / "text.pdf")
    result = probe_pdf(text_pdf)
    assert result["has_text_layer"] is True
    assert result["chars_extracted"] >= 200


def test_empty_text_epub_fail_closed(tmp_path: Path) -> None:
    """EPUB with >3 spine items but <200 chars fails closed with ebook.empty_text."""
    empty_epub = create_empty_text_epub(tmp_path / "empty_spine.epub")
    with pytest.raises(AppError) as exc_info:
        read_epub(empty_epub)
    assert exc_info.value.code == "ebook.empty_text"


def test_read_epub2_minimal(tmp_path: Path) -> None:
    """EPUB 2 minimal reading extracts metadata, TOC, and chapters."""
    epub2 = create_epub2_minimal(tmp_path / "test2.epub")
    data = read_epub(epub2)

    assert data.title == "Minimal EPUB 2"
    assert data.authors == ["Test Author"]
    assert len(data.chapters) == 2
    assert data.chapters[0].title == "First Chapter"
    assert len(data.chapters[0].blocks) == 2
    assert data.chapters[0].blocks[0].kind == BlockKind.HEADING
    assert data.chapters[0].blocks[1].kind == BlockKind.PARAGRAPH


def test_read_epub3_polish_novel(tmp_path: Path) -> None:
    """Polish novel EPUB 3 fixture parses dialogue, cover, metadata, and chapters."""
    novel_path = create_epub3_polish_novel(tmp_path / "novel.epub")
    data = read_epub(novel_path)

    assert data.title == "Kroniki Wrzosowiska"
    assert data.authors == ["Jan Kowalski"]
    assert data.language == "pl"
    assert data.cover_image_bytes is not None
    assert data.cover_image_mime == "image/jpeg"
    assert len(data.chapters) == 4

    # Chapter 2 contains dialogue dashes
    ch1 = data.chapters[1]
    assert "Rozdział 1" in ch1.title
    dialogue_blocks = [b for b in ch1.blocks if b.text.startswith("—")]
    assert len(dialogue_blocks) >= 2
    assert "Czy daleko jeszcze" in dialogue_blocks[0].text


def test_block_normalization() -> None:
    """Block text normalization handles soft hyphens and spaces."""
    raw = "Roz\u00addział   pierw\u00adszy.\n\nKoniec   akapitu."
    normalized = normalize_block_text(raw)
    assert normalized == "Rozdział pierwszy. Koniec akapitu."
    assert "\u00ad" not in normalized


def test_extract_blocks_decorative_images() -> None:
    """Decorative images are stripped, but semantic text is preserved."""
    html = """
    <html><body>
      <h1>Tytuł</h1>
      <img src="flower.jpg" alt="decorative decorative"/>
      <p>Treść akapitu z tekstem.</p>
      <blockquote><p>Cytat w bloku.</p></blockquote>
    </body></html>
    """
    blocks = extract_blocks_from_xhtml(html, source_href="ch1.xhtml")
    assert len(blocks) == 3
    assert blocks[0].kind == BlockKind.HEADING
    assert blocks[1].kind == BlockKind.PARAGRAPH
    assert blocks[2].kind == BlockKind.BLOCKQUOTE
    assert "Tytuł" in blocks[0].text
    assert "Treść akapitu" in blocks[1].text


def test_frontmatter_heuristics(tmp_path: Path) -> None:
    """Frontmatter heuristic detects copyright/ISBN pages and TOCs as skip candidates."""
    novel_path = create_epub3_polish_novel(tmp_path / "novel_fm.epub")
    data = read_epub(novel_path)

    # First chapter is Karta redakcyjna (copyright)
    front_blocks = data.chapters[0].blocks
    skip_cands = detect_skip_candidates(
        front_blocks,
        chapter_title=data.chapters[0].title,
        is_first_chapter=True,
    )
    assert len(skip_cands) >= 1
    assert (
        "copyright" in skip_cands[0].rationale.lower()
        or "redakcyjn" in skip_cands[0].rationale.lower()
    )

    # Second chapter is regular novel chapter -> no frontmatter skips
    ch1_blocks = data.chapters[1].blocks
    novel_skips = detect_skip_candidates(
        ch1_blocks,
        chapter_title=data.chapters[1].title,
        is_first_chapter=False,
    )
    assert len(novel_skips) == 0


def test_deterministic_epub_write_and_roundtrip(tmp_path: Path) -> None:
    """Deterministic EPUB 3 writer produces bit-for-bit identical outputs and roundtrips."""
    novel_path = create_epub3_polish_novel(tmp_path / "original.epub")
    data = read_epub(novel_path)

    out1 = tmp_path / "working1.epub"
    out2 = tmp_path / "working2.epub"

    write_epub(data, out1)
    write_epub(data, out2)

    # 1. Determinism: bit-for-bit identical
    hash1 = hashlib.sha256(out1.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(out2.read_bytes()).hexdigest()
    assert hash1 == hash2

    # 2. Mimetype first uncompressed (offset 30)
    content = out1.read_bytes()
    assert content[30:58] == b"mimetypeapplication/epub+zip"

    # 3. Round-trip read
    roundtrip_data = read_epub(out1)
    assert roundtrip_data.title == data.title
    assert roundtrip_data.language == data.language
    assert roundtrip_data.authors == data.authors
    assert len(roundtrip_data.chapters) == len(data.chapters)

    for orig_ch, rt_ch in zip(data.chapters, roundtrip_data.chapters, strict=True):
        assert orig_ch.title == rt_ch.title
        assert len(orig_ch.blocks) == len(rt_ch.blocks)
        for orig_b, rt_b in zip(orig_ch.blocks, rt_ch.blocks, strict=True):
            assert orig_b.text == rt_b.text
            assert orig_b.kind == rt_b.kind
