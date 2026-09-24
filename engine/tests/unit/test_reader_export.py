# SPDX-License-Identifier: Apache-2.0
"""Reader EPUB export keeps printed words and encodes the lector spans."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tests.ebook_factory import tiny_epub3

from praelector.domain.enums import EpubVariant
from praelector.ebook.epub_read import read_epub
from praelector.ebook.reader_export import ReaderExport, ReaderSpan, render_lector_epub

_APRIL = "It was a bright cold day in April."
_APRIL_AT = _APRIL.index("April")


def test_reader_variant_writes_attributes_and_companion(tmp_path: Path) -> None:
    book = read_epub(_write(tmp_path / "in.epub", tiny_epub3()))
    paragraph = book.chapters[0].blocks[1]
    key = (paragraph.source_ref.href, paragraph.source_ref.path)
    export = ReaderExport(
        variant=EpubVariant.READER,
        spans={
            key: (
                ReaderSpan(0, len(paragraph.text), "dialogue", gender="male", speaker_id="Walker"),
                ReaderSpan(_APRIL_AT, _APRIL_AT + len("April"), "pronunciation", spoken="ejpryl"),
                ReaderSpan(len(paragraph.text), len(paragraph.text), "pause", pause_ms=600),
                ReaderSpan(0, 2, "narration"),
            )
        },
    )
    rendered = render_lector_epub(book, export)
    assert rendered == render_lector_epub(book, export)

    out = tmp_path / "reader.epub"
    out.write_bytes(rendered)
    with zipfile.ZipFile(out) as archive:
        chapter = archive.read("OEBPS/ch01.xhtml").decode("utf-8")
        opf = archive.read("OEBPS/content.opf").decode("utf-8")
        companion = json.loads(archive.read("OEBPS/prl-spans.json"))
    assert 'data-prl-kind="dialogue"' in chapter
    assert 'data-prl-gender="male"' in chapter
    assert 'data-prl-speaker="Walker"' in chapter
    assert 'data-prl-kind="pronunciation" data-prl-spoken="ejpryl"' in chapter
    assert 'data-prl-pause="600"' in chapter
    assert "April" in chapter
    assert "ejpryl" not in chapter.split('data-prl-spoken="ejpryl"')[0]
    assert 'media-type="application/json" properties="prl-sidecar"' in opf
    assert companion["schema_version"] == 1
    kinds = [row["kind"] for row in companion["spans"]]
    assert kinds == ["dialogue", "pronunciation", "pause", "narration"]
    assert companion["spans"][1]["source_ref"] == {"href": key[0], "path": key[1]}
    assert companion["spans"][1]["spoken"] == "ejpryl"

    again = read_epub(out)
    assert again.title == book.title
    assert [block.text for block in again.chapters[0].blocks] == [
        block.text for block in book.chapters[0].blocks
    ]


def test_clean_variant_is_display_text_only(tmp_path: Path) -> None:
    book = read_epub(_write(tmp_path / "in.epub", tiny_epub3()))
    paragraph = book.chapters[0].blocks[1]
    key = (paragraph.source_ref.href, paragraph.source_ref.path)
    export = ReaderExport(
        variant=EpubVariant.CLEAN,
        spans={key: (ReaderSpan(_APRIL_AT, _APRIL_AT + 5, "pronunciation", spoken="ejpryl"),)},
    )
    out = tmp_path / "clean.epub"
    out.write_bytes(render_lector_epub(book, export))
    with zipfile.ZipFile(out) as archive:
        names = set(archive.namelist())
        chapter = archive.read("OEBPS/ch01.xhtml").decode("utf-8")
        opf = archive.read("OEBPS/content.opf").decode("utf-8")
    assert "prl-spans.json" not in names
    assert "data-prl-" not in chapter
    assert "prl-sidecar" not in opf
    assert "April" in chapter
    again = read_epub(out)
    assert again.title == "Tiny Book"
    assert len(again.chapters) == 1


def test_skip_span_keeps_the_printed_words(tmp_path: Path) -> None:
    book = read_epub(_write(tmp_path / "in.epub", tiny_epub3()))
    paragraph = book.chapters[0].blocks[1]
    key = (paragraph.source_ref.href, paragraph.source_ref.path)
    export = ReaderExport(
        variant=EpubVariant.READER,
        spans={key: (ReaderSpan(0, 2, "skip"),)},
    )
    out = tmp_path / "skip.epub"
    out.write_bytes(render_lector_epub(book, export))
    with zipfile.ZipFile(out) as archive:
        chapter = archive.read("OEBPS/ch01.xhtml").decode("utf-8")
    assert '<span data-prl-kind="skip">It</span>' in chapter


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path
