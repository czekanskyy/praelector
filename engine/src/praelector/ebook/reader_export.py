# SPDX-License-Identifier: Apache-2.0
"""Reader EPUB export (EX-01, EX-02, EX-03).

The reader variant keeps the printed words and wraps lector spans in
``data-prl-*`` attributes. A ``prl-spans.json`` companion sits in the manifest
so a later import can restore the spans even if a reading app drops unknown
attributes. The clean variant is the same book with display text only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from praelector.domain.enums import EpubVariant
from praelector.ebook.epub_read import Book

_MARKED = frozenset({"pronunciation", "dialogue", "skip", "pause"})
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


@dataclass(frozen=True, slots=True)
class ReaderSpan:
    """One span inside a block. Offsets are into that block's printed text."""

    start: int
    end: int
    kind: str
    spoken: str = ""
    gender: str = ""
    speaker_id: str = ""
    pause_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ReaderExport:
    """``spans`` is keyed by ``(source_ref.href, source_ref.path)``."""

    variant: EpubVariant
    spans: Mapping[tuple[str, str], tuple[ReaderSpan, ...]]


def render_lector_epub(book: Book, export: ReaderExport) -> bytes:
    """Serialise ``book`` with or without lector markup. Pure: no path is opened."""
    from praelector.ebook.epub_write import render_epub

    return render_epub(book, lector=export)


def annotate_text(text: str, spans: Sequence[ReaderSpan]) -> str:
    """Escaped HTML for one block, with marked spans wrapped and pauses inserted."""
    return _emit(text, spans, 0, len(text), top=True)


def sidecar_bytes(book: Book, export: ReaderExport) -> bytes:
    """The companion document, in chapter and block order."""
    rows: list[dict[str, object]] = []
    for chapter in book.chapters:
        for block in chapter.blocks:
            key = (block.source_ref.href, block.source_ref.path)
            for span in export.spans.get(key, ()):
                rows.append(
                    {
                        "source_ref": {
                            "href": block.source_ref.href,
                            "path": block.source_ref.path,
                        },
                        "start": span.start,
                        "end": span.end,
                        "kind": span.kind,
                        "spoken": span.spoken or None,
                        "gender": span.gender or None,
                        "speaker_id": span.speaker_id or None,
                        "pause_ms": span.pause_ms,
                    }
                )
    payload = {"schema_version": 1, "spans": rows}
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _emit(text: str, spans: Sequence[ReaderSpan], start: int, end: int, *, top: bool) -> str:
    parts: list[str] = []
    cursor = start
    for span in _siblings(spans, start, end, top=top):
        parts.append(_xml_text(text[cursor : span.start]))
        if span.kind == "pause":
            millis = span.pause_ms if span.pause_ms is not None else 0
            parts.append(f'<span data-prl-pause="{millis}"></span>')
            cursor = span.start
            continue
        inner = _emit(text, spans, span.start, span.end, top=False)
        parts.append(f"{_open(span)}{inner}</span>")
        cursor = span.end
    parts.append(_xml_text(text[cursor:end]))
    return "".join(parts)


def _siblings(spans: Sequence[ReaderSpan], start: int, end: int, *, top: bool) -> list[ReaderSpan]:
    contained: list[ReaderSpan] = []
    for span in spans:
        if span.kind not in _MARKED:
            continue
        if span.start < start or span.end > end:
            continue
        if not top and span.start == start and span.end == end:
            continue
        if span.kind != "pause" and span.end <= span.start:
            continue
        contained.append(span)
    contained.sort(key=lambda span: (span.start, -(span.end - span.start), span.kind))
    chosen: list[ReaderSpan] = []
    cursor = start
    for span in contained:
        if span.start < cursor:
            continue
        chosen.append(span)
        if span.kind != "pause":
            cursor = span.end
    return chosen


def _open(span: ReaderSpan) -> str:
    attrs = [f'data-prl-kind="{_xml_attr(span.kind)}"']
    if span.kind == "pronunciation" and span.spoken:
        attrs.append(f'data-prl-spoken="{_xml_attr(span.spoken)}"')
    if span.kind == "dialogue" and span.gender:
        attrs.append(f'data-prl-gender="{_xml_attr(span.gender)}"')
    if span.kind == "dialogue" and span.speaker_id:
        attrs.append(f'data-prl-speaker="{_xml_attr(span.speaker_id)}"')
    return f"<span {' '.join(attrs)}>"


def _xml_text(value: str) -> str:
    cleaned = _ILLEGAL_XML.sub("", value).replace("\r\n", "\n").replace("\r", "\n")
    return cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xml_attr(value: str) -> str:
    return _xml_text(value).replace('"', "&quot;")
