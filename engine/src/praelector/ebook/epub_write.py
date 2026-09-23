# SPDX-License-Identifier: Apache-2.0
"""Deterministic EPUB 3 writer (EB-06, D-01).

``mimetype`` is the first zip entry and is stored uncompressed. The same book
always produces the same bytes: the zip timestamp, the ``dcterms:modified``
value and the chapter names do not depend on the clock. The writer's
destinations are ``source/original.<ext>`` (a copy) and ``source/working.epub``.
The path the user supplied is only ever read.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Final

from praelector.domain.enums import BlockKind
from praelector.ebook.blocks import Block
from praelector.ebook.epub_read import Book, Chapter, TocEntry
from praelector.errors import AppError, ErrorCode

_ZIP_TIME: Final = (1980, 1, 1, 0, 0, 0)
_MODIFIED: Final = "1980-01-01T00:00:00Z"
_MIMETYPE: Final = b"application/epub+zip"
_ILLEGAL_XML: Final = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_LANGUAGE: Final = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
_IMAGE_EXT: Final = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}


def render_epub(book: Book) -> bytes:
    """Serialise ``book`` as EPUB 3. Pure: no path is opened."""
    return _zip(_entries(book))


def write_epub(book: Book, dest: Path) -> None:
    """Atomically replace ``dest`` with ``render_epub(book)``."""
    _atomic_bytes(dest, render_epub(book))


def stage_epub(source: Path, source_dir: Path, book: Book) -> tuple[Path, Path]:
    """Copy ``source`` to ``original.<ext>`` and write ``working.epub``.

    ``source`` is opened for reading only. Refuses when either destination is
    that same file, which is the EB-06 guard against editing the upload.
    """
    if not source.is_file():
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "not_a_file"},
            message="cannot stage an ebook that is not a file",
        )
    suffix = _original_suffix(source)
    original = source_dir / f"original{suffix}"
    working = source_dir / "working.epub"
    source_real = source.resolve()
    if original.resolve() == source_real or working.resolve() == source_real:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "would_mutate_original"},
            message="refusing to write the working epub over the original file",
        )
    payload = source.read_bytes()
    _atomic_bytes(original, payload)
    write_epub(book, working)
    if source.read_bytes() != payload:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "original_changed"},
            message="the original ebook changed while it was being copied",
        )
    return original, working


def _original_suffix(source: Path) -> str:
    suffix = source.suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        return suffix
    return ".bin"


def _atomic_bytes(dest: Path, payload: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(f".{dest.name}.partial")
    temporary.write_bytes(payload)
    temporary.replace(dest)


def _entries(book: Book) -> list[tuple[str, bytes]]:
    language = _language(book.language)
    chapters = _named_chapters(book.chapters)
    cover_name, cover_bytes, cover_media = _cover_parts(book)
    entries: list[tuple[str, bytes]] = [
        ("mimetype", _MIMETYPE),
        ("META-INF/container.xml", _container()),
        ("OEBPS/content.opf", _opf(book, language, chapters, cover_name, cover_media)),
        ("OEBPS/nav.xhtml", _nav(book, language, chapters)),
    ]
    if cover_name is not None and cover_bytes is not None:
        entries.append(("OEBPS/cover.xhtml", _cover_xhtml(language, cover_name)))
        entries.append((f"OEBPS/{cover_name}", cover_bytes))
    for href, chapter in chapters:
        entries.append((f"OEBPS/{href}", _chapter_xhtml(chapter, language)))
    return entries


def _named_chapters(chapters: Sequence[Chapter]) -> tuple[tuple[str, Chapter], ...]:
    return tuple(
        (f"ch{index:02d}.xhtml", chapter) for index, chapter in enumerate(chapters, start=1)
    )


def _cover_parts(book: Book) -> tuple[str | None, bytes | None, str | None]:
    if book.cover is None or not book.cover.data:
        return None, None, None
    media, ext = _image_type(book.cover.data, book.cover.media_type)
    return f"images/cover.{ext}", book.cover.data, media


def _image_type(data: bytes, declared: str) -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", "gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    media = declared.split(";", 1)[0].strip().casefold() or "application/octet-stream"
    return media, _IMAGE_EXT.get(media, "img")


def _zip(entries: Sequence[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for index, (name, payload) in enumerate(entries):
            info = zipfile.ZipInfo(filename=name, date_time=_ZIP_TIME)
            # Pinned so Windows and Linux emit the same archive bytes.
            info.create_system = 3
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED if index == 0 else zipfile.ZIP_DEFLATED
            info.flag_bits |= 0x800
            bundle.writestr(info, payload)
    return buffer.getvalue()


def _container() -> bytes:
    return _xml(
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "  <rootfiles>\n"
        '    <rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>\n"
    )


def _opf(
    book: Book,
    language: str,
    chapters: Sequence[tuple[str, Chapter]],
    cover_name: str | None,
    cover_media: str | None,
) -> bytes:
    identifier = book.identifier.strip() or "urn:uuid:00000000-0000-0000-0000-000000000000"
    title = book.title.strip() or "untitled"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<package xmlns="http://www.idpf.org/2007/opf" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0" unique-identifier="pub-id">',
        "  <metadata>",
        f'    <dc:identifier id="pub-id">{_xml_text(identifier)}</dc:identifier>',
        f"    <dc:title>{_xml_text(title)}</dc:title>",
        f"    <dc:language>{_xml_text(language)}</dc:language>",
    ]
    for author in book.authors:
        cleaned = author.strip()
        if cleaned:
            lines.append(f"    <dc:creator>{_xml_text(cleaned)}</dc:creator>")
    if book.description and book.description.strip():
        lines.append(f"    <dc:description>{_xml_text(book.description.strip())}</dc:description>")
    lines.append(f'    <meta property="dcterms:modified">{_MODIFIED}</meta>')
    lines.append("  </metadata>")
    lines.append("  <manifest>")
    lines.append(
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    )
    if cover_name is not None and cover_media is not None:
        lines.append(
            f'    <item id="cover-image" href="{_xml_attr(cover_name)}" '
            f'media-type="{_xml_attr(cover_media)}" properties="cover-image"/>'
        )
        lines.append('    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
    for index, (href, _chapter) in enumerate(chapters, start=1):
        lines.append(
            f'    <item id="ch{index:02d}" href="{_xml_attr(href)}" '
            f'media-type="application/xhtml+xml"/>'
        )
    lines.append("  </manifest>")
    lines.append("  <spine>")
    if cover_name is not None:
        lines.append('    <itemref idref="cover"/>')
    for index, (_href, chapter) in enumerate(chapters, start=1):
        linear = "" if chapter.linear else ' linear="no"'
        lines.append(f'    <itemref idref="ch{index:02d}"{linear}/>')
    lines.append("  </spine>")
    lines.append("</package>")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _nav(book: Book, language: str, chapters: Sequence[tuple[str, Chapter]]) -> bytes:
    by_source = {chapter.href: href for href, chapter in chapters}
    entries = _retarget(book.toc, by_source)
    if not entries:
        entries = tuple(
            TocEntry(title=chapter.title or PurePosixPath(href).stem, href=href)
            for href, chapter in chapters
        )
    title = book.toc_title.strip() or "Contents"
    items = "\n".join(_nav_items(entries, 4))
    body = (
        f'<nav xmlns:epub="http://www.idpf.org/2007/ops" epub:type="toc" id="toc">\n'
        f"      <h1>{_xml_text(title)}</h1>\n"
        f"      <ol>\n{items}\n      </ol>\n"
        f"    </nav>"
    )
    return _xhtml(title, body, language)


def _nav_items(entries: Sequence[TocEntry], indent: int) -> list[str]:
    pad = " " * indent
    lines: list[str] = []
    for entry in entries:
        label = entry.title.strip() or entry.href
        href = entry.href or ""
        if entry.children:
            nested = "\n".join(_nav_items(entry.children, indent + 4))
            lines.append(
                f'{pad}<li><a href="{_xml_attr(href)}">{_xml_text(label)}</a>\n'
                f"{pad}  <ol>\n{nested}\n{pad}  </ol></li>"
            )
        else:
            lines.append(f'{pad}<li><a href="{_xml_attr(href)}">{_xml_text(label)}</a></li>')
    return lines


def _retarget(entries: Sequence[TocEntry], by_source: dict[str, str]) -> tuple[TocEntry, ...]:
    kept: list[TocEntry] = []
    for entry in entries:
        children = _retarget(entry.children, by_source)
        href = by_source.get(entry.href, "")
        if not href and not children:
            continue
        if not href and children:
            href = children[0].href
        kept.append(TocEntry(title=entry.title, href=href, children=children))
    return tuple(kept)


def _chapter_xhtml(chapter: Chapter, language: str) -> bytes:
    title = chapter.title.strip() or "untitled"
    body = "\n".join(_body_lines(chapter.blocks))
    return _xhtml(title, body, language)


def _body_lines(blocks: Sequence[Block]) -> list[str]:
    lines: list[str] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        if block.kind is BlockKind.LIST_ITEM:
            items: list[str] = []
            while index < len(blocks) and blocks[index].kind is BlockKind.LIST_ITEM:
                items.append(f"<li>{_xml_text(blocks[index].text)}</li>")
                index += 1
            lines.append("<ul>" + "".join(items) + "</ul>")
            continue
        lines.append(_render_block(block))
        index += 1
    return lines


def _render_block(block: Block) -> str:
    text = _xml_text(block.text)
    if block.kind is BlockKind.HEADING:
        level = block.heading_level if block.heading_level in range(1, 7) else 1
        return f"<h{level}>{text}</h{level}>"
    if block.kind is BlockKind.BLOCKQUOTE:
        return f"<blockquote>{text}</blockquote>"
    if block.kind is BlockKind.CAPTION:
        return f"<figcaption>{text}</figcaption>"
    return f"<p>{text}</p>"


def _cover_xhtml(language: str, cover_name: str) -> bytes:
    body = f'<div><img src="{_xml_attr(cover_name)}" alt=""/></div>'
    return _xhtml("Cover", body, language)


def _xhtml(title: str, body: str, language: str) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{_xml_attr(language)}" '
        f'lang="{_xml_attr(language)}">\n'
        "<head>\n"
        f"<title>{_xml_text(title)}</title>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )
    return document.encode("utf-8")


def _language(value: str) -> str:
    cleaned = value.strip()
    if _LANGUAGE.fullmatch(cleaned):
        return cleaned
    return "und"


def _xml(body: str) -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body).encode("utf-8")


def _xml_text(value: str) -> str:
    cleaned = _ILLEGAL_XML.sub("", value).replace("\r\n", "\n").replace("\r", "\n")
    return cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _xml_attr(value: str) -> str:
    return _xml_text(value).replace('"', "&quot;")
