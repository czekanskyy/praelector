# SPDX-License-Identifier: Apache-2.0
"""EPUB ingest: read, write, DRM, empty text, front matter, PDF and Calibre."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest
from tests.ebook_factory import (
    ADOBE_FONT_OBFUSCATION,
    AES_128_CBC,
    IDPF_FONT_OBFUSCATION,
    container_xml,
    encryption_xml,
    epub_bytes,
    package,
    pdf_bytes,
    spine_epub,
    tiny_epub2,
    tiny_epub3,
    with_meta,
    xhtml,
)

from praelector.config import PathSettings, Settings
from praelector.domain.enums import BlockKind, SourceFormat
from praelector.ebook.calibre import ConvertResult, convert_to_epub, locate_ebook_convert
from praelector.ebook.detect import detect_format
from praelector.ebook.drm import FONT_OBFUSCATION_ALGORITHMS
from praelector.ebook.epub_read import read_epub
from praelector.ebook.epub_write import render_epub, stage_epub
from praelector.ebook.frontmatter import skip_candidates
from praelector.ebook.pdf import TEXT_LAYER_MIN_CHARS, assert_pdf_text_layer
from praelector.errors import AppError, ErrorCode

_PNG = b"\x89PNG\r\n\x1a\ncover-bytes"


def test_font_obfuscation_uris_are_the_two_spec_allows() -> None:
    assert {
        IDPF_FONT_OBFUSCATION,
        ADOBE_FONT_OBFUSCATION,
    } == FONT_OBFUSCATION_ALGORITHMS


def test_epub3_round_trip_keeps_metadata_chapter_and_nav(tmp_path: Path) -> None:
    source = tmp_path / "in.epub"
    source.write_bytes(tiny_epub3())
    book = read_epub(source)
    assert book.title == "Tiny Book"
    assert book.authors == ("Ada Lovelace",)
    assert book.language == "en"
    assert book.identifier == "urn:uuid:11111111-2222-3333-4444-000000000003"
    assert book.toc_title == "Contents"
    assert [entry.title for entry in book.toc] == ["Chapter One"]
    assert len(book.chapters) == 1
    assert [block.text for block in book.chapters[0].blocks] == [
        "Chapter One",
        "It was a bright cold day in April.",
    ]
    assert book.chapters[0].blocks[1].source_ref.href == "OEBPS/ch01.xhtml"
    assert book.chapters[0].blocks[1].source_ref.path == "/html/body/p[1]"

    rendered = render_epub(book)
    assert rendered == render_epub(book)
    with zipfile.ZipFile(tmp_path / "out.epub", "w") as archive:
        pass
    (tmp_path / "out.epub").write_bytes(rendered)
    with zipfile.ZipFile(tmp_path / "out.epub") as archive:
        info = archive.infolist()[0]
        assert info.filename == "mimetype"
        assert info.compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"
    again = read_epub(tmp_path / "out.epub")
    assert again.title == book.title
    assert again.authors == book.authors
    assert again.language == book.language
    assert again.identifier == book.identifier
    assert again.epub_version == "3.0"
    assert [block.text for block in again.chapters[0].blocks] == [
        block.text for block in book.chapters[0].blocks
    ]
    assert [entry.title for entry in again.toc] == ["Chapter One"]
    assert again.toc_title == "Contents"


def test_epub2_ncx_is_read(tmp_path: Path) -> None:
    path = tmp_path / "epub2.epub"
    path.write_bytes(tiny_epub2())
    book = read_epub(path)
    assert book.title == "Minimal EPUB 2"
    assert book.epub_version == "2.0"
    assert [entry.title for entry in book.toc] == ["Chapter One"]
    assert book.chapters[0].blocks[1].text == "It was a bright cold day in April."


def test_stage_copies_the_original_and_never_mutates_it(tmp_path: Path) -> None:
    source = tmp_path / "upload.epub"
    payload = tiny_epub3()
    source.write_bytes(payload)
    book = read_epub(source)
    original, working = stage_epub(source, tmp_path / "source", book)
    assert source.read_bytes() == payload
    assert original.name == "original.epub"
    assert original.read_bytes() == payload
    assert working.name == "working.epub"
    assert read_epub(working).title == "Tiny Book"
    with pytest.raises(AppError) as excinfo:
        stage_epub(original, original.parent, book)
    assert excinfo.value.code is ErrorCode.EBOOK_PARSE_FAILED
    assert excinfo.value.detail["reason"] == "would_mutate_original"
    assert original.read_bytes() == payload


def test_drm_on_xhtml_refuses_and_font_obfuscation_does_not(tmp_path: Path) -> None:
    locked = tmp_path / "locked.epub"
    locked.write_bytes(
        with_meta(
            (
                (
                    "META-INF/encryption.xml",
                    encryption_xml(AES_128_CBC, "OEBPS/ch01.xhtml"),
                ),
            )
        )
    )
    with pytest.raises(AppError) as excinfo:
        read_epub(locked)
    assert excinfo.value.code is ErrorCode.EBOOK_DRM_DETECTED
    assert excinfo.value.detail["reason"] == "encrypted_content"

    for algorithm in (IDPF_FONT_OBFUSCATION, ADOBE_FONT_OBFUSCATION):
        allowed = tmp_path / f"{algorithm.rsplit('/', 1)[-1].replace('#', '-')}.epub"
        allowed.write_bytes(
            with_meta(
                (
                    (
                        "META-INF/encryption.xml",
                        encryption_xml(
                            algorithm,
                            "OEBPS/fonts/font.otf",
                            wrapped_key=True,
                        ),
                    ),
                )
            )
        )
        book = read_epub(allowed)
        assert book.chapters[0].blocks[-1].text == "The text stays readable."


def test_font_algorithm_on_xhtml_still_refuses(tmp_path: Path) -> None:
    path = tmp_path / "font-on-xhtml.epub"
    path.write_bytes(
        with_meta(
            (
                (
                    "META-INF/encryption.xml",
                    encryption_xml(IDPF_FONT_OBFUSCATION, "OEBPS/ch01.xhtml"),
                ),
            )
        )
    )
    with pytest.raises(AppError) as excinfo:
        read_epub(path)
    assert excinfo.value.code is ErrorCode.EBOOK_DRM_DETECTED


@pytest.mark.parametrize("member", ["rights.xml", "sinf.xml"])
def test_rights_and_sinf_refuse(tmp_path: Path, member: str) -> None:
    path = tmp_path / f"{member}.epub"
    path.write_bytes(with_meta(((f"META-INF/{member}", b"<rights/>"),)))
    with pytest.raises(AppError) as excinfo:
        read_epub(path)
    assert excinfo.value.code is ErrorCode.EBOOK_DRM_DETECTED
    assert excinfo.value.detail["reason"] in {"rights_xml", "sinf_xml"}


def test_empty_text_fails_closed_only_past_three_spine_items(tmp_path: Path) -> None:
    empty = tmp_path / "empty.epub"
    empty.write_bytes(spine_epub(["", "", "", "", ""]))
    with pytest.raises(AppError) as excinfo:
        read_epub(empty)
    assert excinfo.value.code is ErrorCode.EBOOK_EMPTY_TEXT
    assert excinfo.value.detail["spine_items"] == 5
    assert excinfo.value.detail["characters"] == 0

    short = tmp_path / "short.epub"
    short.write_bytes(spine_epub(["", "", "", "a" * 199]))
    with pytest.raises(AppError) as excinfo:
        read_epub(short)
    assert excinfo.value.code is ErrorCode.EBOOK_EMPTY_TEXT
    assert excinfo.value.detail["characters"] == 199

    enough = tmp_path / "enough.epub"
    enough.write_bytes(spine_epub(["", "", "", "a" * 200]))
    book = read_epub(enough)
    assert book.spine_count == 4
    assert len(book.chapters) == 1

    three = tmp_path / "three.epub"
    three.write_bytes(spine_epub(["", "", ""]))
    assert read_epub(three).spine_count == 3


def test_cover_is_kept_and_decorative_images_are_not_blocks(tmp_path: Path) -> None:
    chapter = xhtml(
        "Chapter",
        "<h1>Chapter</h1>\n"
        "<p>Hello there.</p>\n"
        '<div><img src="images/spot.png" alt=""/></div>\n'
        '<div><img src="images/map.png" alt="Map of the city"/></div>\n',
    )
    cover_page = xhtml(
        "Cover",
        '<div><img src="images/cover.png" alt="Okładka"/></div>\n',
    )
    opf = package(
        title="Covered",
        language="pl",
        creator="Marta",
        identifier="urn:uuid:cover",
        items=(
            ("cover-image", "images/cover.png", "image/png", "cover-image"),
            ("spot", "images/spot.png", "image/png", ""),
            ("map", "images/map.png", "image/png", ""),
            ("cover", "cover.xhtml", "application/xhtml+xml", ""),
            ("ch01", "ch01.xhtml", "application/xhtml+xml", ""),
        ),
        spine=("cover", "ch01"),
    )
    path = tmp_path / "cover.epub"
    path.write_bytes(
        epub_bytes(
            (
                ("mimetype", b"application/epub+zip"),
                ("META-INF/container.xml", container_xml()),
                ("OEBPS/content.opf", opf),
                ("OEBPS/cover.xhtml", cover_page),
                ("OEBPS/ch01.xhtml", chapter),
                ("OEBPS/images/cover.png", _PNG),
                ("OEBPS/images/spot.png", b"spot"),
                ("OEBPS/images/map.png", b"map"),
            )
        )
    )
    book = read_epub(path)
    assert book.cover is not None
    assert book.cover.data == _PNG
    texts = [block.text for block in book.chapters[0].blocks]
    assert "Okładka" not in texts
    assert "Hello there." in texts
    captions = [block for block in book.chapters[0].blocks if block.kind is BlockKind.CAPTION]
    assert [block.text for block in captions] == ["Map of the city"]
    written = read_epub(_written(tmp_path, book))
    assert written.cover is not None
    assert written.cover.data == _PNG


def test_named_html_entity_does_not_fail_the_parse(tmp_path: Path) -> None:
    path = tmp_path / "nbsp.epub"
    path.write_bytes(
        spine_epub(["<p>Hello&nbsp;world, this is enough text. " + ("word " * 30) + "</p>"])
    )
    book = read_epub(path)
    assert "Hello" in book.chapters[0].blocks[0].text
    assert "world" in book.chapters[0].blocks[0].text


def test_front_matter_heuristics_flag_spans_and_keep_the_blocks() -> None:
    blocks = [
        "ISBN 978-83-000000-0-0",
        "Wszelkie prawa zastrzeżone",
        "12",
        "Anna odłożyła raport i spojrzała na zegar.",
    ]
    original = list(blocks)
    spans = skip_candidates(blocks)
    assert blocks == original
    assert [(span.block_index, span.reason, span.start, span.end) for span in spans] == [
        (0, "isbn", 0, len(blocks[0])),
        (1, "copyright", 0, len(blocks[1])),
        (2, "page_number", 0, len(blocks[2])),
    ]

    more = skip_candidates(
        [
            "Copyright © 2026 Marta Zaremba",
            "All rights reserved",
            "Tytuł oryginału: The Left Hand of Darkness",
            "Skład i łamanie: pracownia własna wydawnictwa",
            "Projekt okładki: Anna Nowak",
        ]
    )
    assert [span.reason for span in more] == [
        "copyright",
        "copyright",
        "original_title",
        "editorial",
        "editorial",
    ]
    narrative = "Copyright " + ("law " * 120)
    assert len(narrative) > 400
    assert skip_candidates([narrative]) == []


def test_toc_run_needs_five_chapter_titles() -> None:
    titles = [f"Rozdział {number}" for number in range(1, 6)]
    blocks = ["Spis treści", *titles, "To jest prawdziwy akapit o archiwum i niczym innym."]
    flagged = {span.block_index for span in skip_candidates(blocks, chapter_titles=titles)}
    assert flagged == {0, 1, 2, 3, 4, 5}
    short = titles[:4]
    assert skip_candidates(["Spis treści", *short], chapter_titles=short) == []


def test_format_detection_uses_magic_and_extension(tmp_path: Path) -> None:
    epub = tmp_path / "book.epub"
    epub.write_bytes(tiny_epub3())
    assert detect_format(epub).format is SourceFormat.EPUB
    assert detect_format(epub).needs_conversion is False

    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(pdf_bytes("Hello"))
    detected = detect_format(pdf)
    assert detected.format is SourceFormat.PDF
    assert detected.needs_conversion is True

    palm = b"\x00" * 60 + b"BOOKMOBI" + b"\x00" * 16
    assert detect_format(_touch(tmp_path / "book.mobi", palm)).format is SourceFormat.MOBI
    assert detect_format(_touch(tmp_path / "book.azw3", palm)).format is SourceFormat.AZW3
    assert detect_format(_touch(tmp_path / "book.azw", palm)).format is SourceFormat.AZW

    clash = tmp_path / "nope.epub"
    clash.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(AppError) as excinfo:
        detect_format(clash)
    assert excinfo.value.code is ErrorCode.EBOOK_UNSUPPORTED_FORMAT
    assert excinfo.value.detail["reason"] == "conflict"

    unknown = tmp_path / "notes.txt"
    unknown.write_bytes(b"hello")
    with pytest.raises(AppError) as excinfo:
        detect_format(unknown)
    assert excinfo.value.code is ErrorCode.EBOOK_UNSUPPORTED_FORMAT


def test_pdf_text_layer_accepts_a_sentence_and_refuses_an_empty_page(tmp_path: Path) -> None:
    sentence = tmp_path / "text.pdf"
    sentence.write_bytes(pdf_bytes("This page has a real text layer. " * 12))
    assert assert_pdf_text_layer(sentence) >= TEXT_LAYER_MIN_CHARS

    blank = tmp_path / "blank.pdf"
    blank.write_bytes(pdf_bytes(""))
    with pytest.raises(AppError) as excinfo:
        assert_pdf_text_layer(blank)
    assert excinfo.value.code is ErrorCode.EBOOK_NO_TEXT_LAYER
    assert excinfo.value.detail["characters"] == 0


def test_calibre_missing_is_structured_when_the_path_is_absent(tmp_path: Path) -> None:
    missing = tmp_path / "ebook-convert"
    settings = Settings(paths=PathSettings(calibre_path=str(missing)))
    with pytest.raises(AppError) as excinfo:
        locate_ebook_convert(settings)
    assert excinfo.value.code is ErrorCode.EBOOK_CALIBRE_MISSING
    detail = excinfo.value.detail
    assert detail["binary"] == "ebook-convert"
    assert detail["install_hint_key"] in {"calibre_windows", "calibre_linux", "calibre_macos"}
    if sys.platform == "win32":
        assert detail["install_hint_key"] == "calibre_windows"
        assert detail["winget_id"] == "calibre.calibre"
    elif sys.platform != "darwin":
        assert detail["package"] == "calibre"
        assert detail["package_manager"] == "pacman"

    source = tmp_path / "book.pdf"
    source.write_bytes(pdf_bytes(""))
    with pytest.raises(AppError) as excinfo:
        convert_to_epub(source, tmp_path / "out", binary=str(missing))
    assert excinfo.value.code is ErrorCode.EBOOK_CALIBRE_MISSING


def test_conversion_failure_surfaces_stderr_without_a_real_binary(tmp_path: Path) -> None:
    binary = tmp_path / "ebook-convert"
    binary.write_bytes(b"")
    source = tmp_path / "book.mobi"
    source.write_bytes(b"mobi")

    def runner(argv: list[str] | tuple[str, ...]) -> ConvertResult:
        assert Path(argv[1]) == source
        assert argv[2].endswith("converted.epub")
        return ConvertResult(returncode=2, stderr="calibre exploded: bad mobi\n")

    with pytest.raises(AppError) as excinfo:
        convert_to_epub(source, tmp_path / "work", binary=str(binary), runner=runner)
    assert excinfo.value.code is ErrorCode.EBOOK_CONVERSION_FAILED
    assert excinfo.value.detail["returncode"] == 2
    assert "calibre exploded" in str(excinfo.value.detail["stderr"])


def _touch(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def _written(tmp_path: Path, book: object) -> Path:
    from praelector.ebook.epub_read import Book
    from praelector.ebook.epub_write import write_epub

    assert isinstance(book, Book)
    dest = tmp_path / "working.epub"
    write_epub(book, dest)
    return dest
