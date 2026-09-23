# SPDX-License-Identifier: Apache-2.0
"""EPUB 2/3 reader (EB-01, EB-05, EB-02).

``META-INF/container.xml`` points at the OPF. The OPF yields metadata, the
manifest, the spine and the cover; the TOC comes from the nav document or,
failing that, the NCX. Spine documents become chapters of blocks. The user's
file is only read.

More than three spine items and fewer than 200 extractable characters refuses
with ``ebook.empty_text`` (EB-02). A nav document in the spine counts toward
that total and is not narrated. A spine document with no text — a cover page,
a full-page image — is kept as the cover when it is one, and otherwise dropped
from the chapter list, but it still counts as a spine item.
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final
from xml.etree import ElementTree as ET

from praelector.domain.enums import BlockKind
from praelector.ebook.blocks import Block, blocks_from_xhtml, extractable_characters
from praelector.ebook.drm import refuse_drm
from praelector.ebook.markup import (
    attr,
    direct,
    directory_of,
    element_text,
    first,
    local_name,
    parse_xml,
    resolve_href,
)
from praelector.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

#: EB-02: refuse only once the spine is longer than this and the text is short.
#: Three empty documents are not the failure mode the check is aimed at.
_EMPTY_SPINE_MIN: Final = 3
_EMPTY_TEXT_MIN_CHARS: Final = 200
_MAX_ENTRY_BYTES: Final = 32 * 1024 * 1024
_MAX_TOTAL_BYTES: Final = 256 * 1024 * 1024
_XHTML_SUFFIXES: Final = frozenset({".xhtml", ".html", ".htm", ".xht"})


@dataclass(frozen=True, slots=True)
class TocEntry:
    """One contents entry. ``href`` is the zip path with any fragment removed."""

    title: str
    href: str
    children: tuple[TocEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class Chapter:
    """One spine document that has text. ``href`` is the zip member it came from."""

    id: str
    title: str
    href: str
    blocks: tuple[Block, ...]
    linear: bool = True


@dataclass(frozen=True, slots=True)
class Cover:
    """The cover image bytes. Decorative images are not stored."""

    href: str
    media_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class Book:
    """A parsed EPUB. ``spine_count`` includes documents that produced no blocks."""

    title: str
    authors: tuple[str, ...]
    language: str
    identifier: str
    chapters: tuple[Chapter, ...]
    toc: tuple[TocEntry, ...]
    cover: Cover | None
    spine_count: int
    description: str | None = None
    epub_version: str = ""
    toc_title: str = "Contents"


@dataclass(frozen=True, slots=True)
class _Item:
    id: str
    href: str
    media_type: str
    properties: frozenset[str]


@dataclass
class _Archive:
    zip: zipfile.ZipFile
    exact: dict[str, str]
    folded: dict[str, str]
    total: int = 0

    def read(self, href: str) -> bytes:
        member = self._member(href)
        info = self.zip.getinfo(member)
        size = info.file_size or info.compress_size
        if size > _MAX_ENTRY_BYTES or self.total + size > _MAX_TOTAL_BYTES:
            raise AppError(
                ErrorCode.EBOOK_PARSE_FAILED,
                detail={"reason": "too_large", "path": href},
                message="epub member is too large",
            )
        try:
            payload = self.zip.read(member)
        except (KeyError, OSError, zipfile.BadZipFile) as exc:
            raise AppError(
                ErrorCode.EBOOK_PARSE_FAILED,
                detail={"reason": "zip", "path": href},
                message="epub member could not be read",
            ) from exc
        if len(payload) > _MAX_ENTRY_BYTES or self.total + len(payload) > _MAX_TOTAL_BYTES:
            raise AppError(
                ErrorCode.EBOOK_PARSE_FAILED,
                detail={"reason": "too_large", "path": href},
                message="epub member is too large",
            )
        self.total += len(payload)
        return payload

    def _member(self, href: str) -> str:
        found = self.exact.get(href)
        if found is not None:
            return found
        folded = self.folded.get(href.casefold())
        if folded is None:
            raise AppError(
                ErrorCode.EBOOK_PARSE_FAILED,
                detail={"reason": "missing_href", "href": href},
                message="epub href does not name a member",
            )
        # PLAN.md §2: case-insensitive fallback, with a warning rather than a
        # silent rename. The bytes are still the member the author packed.
        logger.warning("epub href case mismatch", extra={"href": href, "member": folded})
        return folded


def read_epub(path: Path) -> Book:
    """Read one EPUB. DRM and the empty-text check refuse before a book is returned."""
    if not path.is_file():
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "not_a_file"},
            message="epub path is not a file",
        )
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "zip"},
            message="epub is not a zip archive",
        ) from exc
    with archive:
        # DRM before the member-name check: a locked book is ``ebook.drm_detected``
        # even when another member path is also hostile.
        refuse_drm(archive)
        exact, folded = _index(archive)
        index = _Archive(archive, exact, folded)
        opf_href = _opf_href(index)
        opf = parse_xml(index.read(opf_href), path=opf_href)
        book = _parse_opf(index, opf, opf_href)
    _refuse_if_empty(book)
    return book


def iter_toc(entries: tuple[TocEntry, ...]) -> tuple[TocEntry, ...]:
    """``entries`` and their descendants, pre-order."""
    flat: list[TocEntry] = []
    pending: list[TocEntry] = list(entries)
    while pending:
        current = pending.pop(0)
        flat.append(current)
        pending[0:0] = list(current.children)
    return tuple(flat)


def _index(archive: zipfile.ZipFile) -> tuple[dict[str, str], dict[str, str]]:
    exact: dict[str, str] = {}
    folded: dict[str, str] = {}
    for name in archive.namelist():
        posix = name.replace("\\", "/")
        if not posix or posix.endswith("/"):
            continue
        path = PurePosixPath(posix)
        if path.is_absolute() or ".." in path.parts:
            raise AppError(
                ErrorCode.EBOOK_PARSE_FAILED,
                detail={"reason": "path_escape", "path": posix},
                message="epub member path escapes the archive",
            )
        exact.setdefault(posix, name)
        folded.setdefault(posix.casefold(), name)
    return exact, folded


def _opf_href(index: _Archive) -> str:
    container = index.exact.get("META-INF/container.xml") or index.folded.get(
        "meta-inf/container.xml"
    )
    if container is None:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "missing_container"},
            message="epub has no container.xml",
        )
    root = parse_xml(index.read(container), path="META-INF/container.xml")
    chosen: str | None = None
    for node in root.iter():
        if not isinstance(node.tag, str) or local_name(node.tag) != "rootfile":
            continue
        full = attr(node, "full-path")
        if not full:
            continue
        media = (attr(node, "media-type") or "").casefold()
        href = resolve_href("", full)
        if media == "application/oebps-package+xml" or chosen is None:
            chosen = href
        if media == "application/oebps-package+xml":
            break
    if chosen is None:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "missing_opf"},
            message="epub container has no rootfile",
        )
    return chosen


def _parse_opf(index: _Archive, opf: ET.Element, opf_href: str) -> Book:
    if local_name(opf.tag).casefold() != "package":
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "opf", "path": opf_href},
            message="epub package element is missing",
        )
    opf_dir = directory_of(opf_href)
    metadata = _child(opf, "metadata")
    manifest = _child(opf, "manifest")
    spine = _child(opf, "spine")
    if metadata is None or manifest is None or spine is None:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "opf", "path": opf_href},
            message="epub package is missing metadata, manifest or spine",
        )
    items = _manifest(manifest, opf_dir)
    title, authors, language, identifier, description = _metadata(metadata, opf)
    cover = _cover(index, opf, items, opf_dir)
    toc_title, toc = _toc(index, items, spine, opf_dir)
    chapters = _chapters(index, items, spine, cover.href if cover else None, toc)
    version = (attr(opf, "version") or "").strip()
    if not identifier:
        identifier = _fallback_identifier(title, tuple(chapter.href for chapter in chapters))
    return Book(
        title=title,
        authors=authors,
        language=language,
        identifier=identifier,
        chapters=chapters,
        toc=toc,
        cover=cover,
        spine_count=len(direct(spine, "itemref")),
        description=description,
        epub_version=version,
        toc_title=toc_title or "Contents",
    )


def _child(element: ET.Element, name: str) -> ET.Element | None:
    found = direct(element, name)
    return found[0] if found else None


def _manifest(manifest: ET.Element, opf_dir: str) -> dict[str, _Item]:
    items: dict[str, _Item] = {}
    for node in direct(manifest, "item"):
        item_id = (attr(node, "id") or "").strip()
        href = (attr(node, "href") or "").strip()
        if not item_id or not href:
            raise AppError(
                ErrorCode.EBOOK_PARSE_FAILED,
                detail={"reason": "manifest_item"},
                message="epub manifest item is missing id or href",
            )
        if item_id in items:
            raise AppError(
                ErrorCode.EBOOK_PARSE_FAILED,
                detail={"reason": "duplicate_id", "id": item_id},
                message="epub manifest id is duplicated",
            )
        items[item_id] = _Item(
            id=item_id,
            href=resolve_href(opf_dir, href),
            media_type=(attr(node, "media-type") or "").strip(),
            properties=frozenset((attr(node, "properties") or "").split()),
        )
    return items


def _metadata(
    metadata: ET.Element, package: ET.Element
) -> tuple[str, tuple[str, ...], str, str, str | None]:
    titles = [_text(node) for node in direct(metadata, "title")]
    title = next((item for item in titles if item), "")
    authors = tuple(_text(node) for node in direct(metadata, "creator") if _text(node))
    languages = [_text(node) for node in direct(metadata, "language")]
    language = next((item for item in languages if item), "")
    descriptions = [_text(node) for node in direct(metadata, "description")]
    description = next((item for item in descriptions if item), None)
    identifier = _identifier(metadata, package)
    return title, authors, language, identifier, description


def _text(node: ET.Element) -> str:
    return " ".join(element_text(node).split())


def _identifier(metadata: ET.Element, package: ET.Element) -> str:
    nodes = direct(metadata, "identifier")
    wanted = (attr(package, "unique-identifier") or "").strip()
    if wanted:
        for node in nodes:
            if (attr(node, "id") or "").strip() == wanted and _text(node):
                return _text(node)
    for node in nodes:
        if _text(node):
            return _text(node)
    return ""


def _fallback_identifier(title: str, hrefs: tuple[str, ...]) -> str:
    digest = hashlib.sha256((title + "\n" + "\n".join(hrefs)).encode()).hexdigest()
    raw = digest[:32]
    return f"urn:uuid:{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def _cover(
    index: _Archive, package: ET.Element, items: dict[str, _Item], opf_dir: str
) -> Cover | None:
    chosen = _cover_item(package, items)
    if chosen is None:
        guide = _child(package, "guide")
        if guide is not None:
            chosen = _cover_from_guide(index, guide, opf_dir, items)
    if chosen is None:
        return None
    try:
        payload = index.read(chosen.href)
    except AppError:
        logger.warning("epub cover could not be read", extra={"href": chosen.href})
        return None
    media = chosen.media_type or "application/octet-stream"
    return Cover(href=chosen.href, media_type=media, data=payload)


def _cover_item(package: ET.Element, items: dict[str, _Item]) -> _Item | None:
    for item in items.values():
        if "cover-image" in item.properties and _is_image(item):
            return item
    metadata = _child(package, "metadata")
    if metadata is not None:
        for node in direct(metadata, "meta"):
            if (attr(node, "name") or "").casefold() != "cover":
                continue
            item_id = (attr(node, "content") or "").strip()
            named = items.get(item_id)
            if named is not None and _is_image(named):
                return named
    for key in ("cover-image", "cover"):
        named = items.get(key)
        if named is not None and _is_image(named):
            return named
    return None


def _cover_from_guide(
    index: _Archive, guide: ET.Element, opf_dir: str, items: dict[str, _Item]
) -> _Item | None:
    for node in direct(guide, "reference"):
        if (attr(node, "type") or "").casefold() != "cover":
            continue
        href = (attr(node, "href") or "").strip()
        if not href:
            continue
        target = resolve_href(opf_dir, href)
        for item in items.values():
            if item.href == target and _is_image(item):
                return item
        image = _first_image_href(index, target)
        if image is None:
            continue
        for item in items.values():
            if item.href == image and _is_image(item):
                return item
    return None


def _first_image_href(index: _Archive, href: str) -> str | None:
    if not _is_xhtml_href(href):
        return None
    try:
        root = parse_xml(index.read(href), path=href)
    except AppError:
        return None
    base = directory_of(href)
    for node in root.iter():
        if isinstance(node.tag, str) and local_name(node.tag).casefold() == "img":
            source = attr(node, "src")
            if source:
                return resolve_href(base, source)
    return None


def _is_image(item: _Item) -> bool:
    return item.media_type.casefold().startswith("image/")


def _toc(
    index: _Archive, items: dict[str, _Item], spine: ET.Element, opf_dir: str
) -> tuple[str, tuple[TocEntry, ...]]:
    nav = next((item for item in items.values() if "nav" in item.properties), None)
    if nav is not None and _is_xhtml(nav):
        try:
            return _nav_toc(parse_xml(index.read(nav.href), path=nav.href), directory_of(nav.href))
        except AppError:
            logger.warning("epub nav could not be read", extra={"href": nav.href})
    ncx_id = (attr(spine, "toc") or "").strip()
    ncx = items.get(ncx_id) if ncx_id else None
    if ncx is None:
        ncx = next(
            (
                item
                for item in items.values()
                if item.media_type.casefold() == "application/x-dtbncx+xml"
                or item.href.casefold().endswith(".ncx")
            ),
            None,
        )
    if ncx is None:
        return "Contents", ()
    try:
        return "Contents", _ncx_toc(
            parse_xml(index.read(ncx.href), path=ncx.href), directory_of(ncx.href)
        )
    except AppError:
        logger.warning("epub ncx could not be read", extra={"href": ncx.href})
        return "Contents", ()


def _nav_toc(root: ET.Element, base: str) -> tuple[str, tuple[TocEntry, ...]]:
    nav = _toc_nav(root)
    if nav is None:
        return "Contents", ()
    title = ""
    for heading in ("h1", "h2", "h3"):
        node = first(nav, heading)
        if node is not None and element_text(node):
            title = element_text(node)
            break
    listing = _child(nav, "ol")
    entries = _nav_list(listing, base) if listing is not None else ()
    return title or "Contents", entries


def _toc_nav(root: ET.Element) -> ET.Element | None:
    navs = [
        node for node in root.iter() if isinstance(node.tag, str) and local_name(node.tag) == "nav"
    ]
    for nav in navs:
        kind = (attr(nav, "type") or "").casefold()
        if "toc" in kind.split():
            return nav
    return navs[0] if navs else None


def _nav_list(listing: ET.Element, base: str) -> tuple[TocEntry, ...]:
    entries: list[TocEntry] = []
    for item in direct(listing, "li"):
        anchor = _child(item, "a")
        title = element_text(anchor) if anchor is not None else ""
        href = ""
        if anchor is not None and (attr(anchor, "href") or "").strip():
            href = resolve_href(base, attr(anchor, "href") or "")
        nested = _child(item, "ol")
        children = _nav_list(nested, base) if nested is not None else ()
        if not title and not children:
            continue
        entries.append(TocEntry(title=title, href=href, children=children))
    return tuple(entries)


def _ncx_toc(root: ET.Element, base: str) -> tuple[TocEntry, ...]:
    nav_map = first(root, "navMap")
    if nav_map is None:
        return ()
    return _ncx_points(nav_map, base)


def _ncx_points(parent: ET.Element, base: str) -> tuple[TocEntry, ...]:
    entries: list[TocEntry] = []
    for point in direct(parent, "navPoint"):
        label = first(point, "text")
        content = _child(point, "content")
        title = element_text(label) if label is not None else ""
        src = (attr(content, "src") or "").strip() if content is not None else ""
        href = resolve_href(base, src) if src else ""
        children = _ncx_points(point, base)
        if not title and not children:
            continue
        entries.append(TocEntry(title=title, href=href, children=children))
    return tuple(entries)


def _chapters(
    index: _Archive,
    items: dict[str, _Item],
    spine: ET.Element,
    cover_href: str | None,
    toc: tuple[TocEntry, ...],
) -> tuple[Chapter, ...]:
    chapters: list[Chapter] = []
    titles = {entry.href: entry.title for entry in iter_toc(toc) if entry.href and entry.title}
    for node in direct(spine, "itemref"):
        idref = (attr(node, "idref") or "").strip()
        item = items.get(idref)
        if item is None:
            raise AppError(
                ErrorCode.EBOOK_PARSE_FAILED,
                detail={"reason": "spine_idref", "id": idref},
                message="epub spine idref is not in the manifest",
            )
        if "nav" in item.properties or not _is_xhtml(item):
            continue
        blocks = blocks_from_xhtml(index.read(item.href), href=item.href, cover_href=cover_href)
        if not blocks:
            continue
        ordinal = len(chapters) + 1
        chapters.append(
            Chapter(
                id=_safe_id(item.id, f"ch{ordinal:02d}"),
                title=_chapter_title(item, blocks, titles),
                href=item.href,
                blocks=blocks,
                linear=(attr(node, "linear") or "yes").casefold() != "no",
            )
        )
    return tuple(chapters)


def _chapter_title(item: _Item, blocks: tuple[Block, ...], titles: dict[str, str]) -> str:
    labelled = titles.get(item.href, "").strip()
    if labelled:
        return labelled
    for block in blocks:
        if block.kind is BlockKind.HEADING and block.text.strip():
            return block.text.strip()
    return PurePosixPath(item.href).stem or item.id


def _safe_id(value: str, fallback: str) -> str:
    if value and all(char.isalnum() or char in "._-" for char in value) and not value[0].isdigit():
        return value
    return fallback


def _is_xhtml(item: _Item) -> bool:
    media = item.media_type.casefold()
    if "html" in media or "xhtml" in media:
        return True
    return _is_xhtml_href(item.href)


def _is_xhtml_href(href: str) -> bool:
    return PurePosixPath(href).suffix.casefold() in _XHTML_SUFFIXES


def _refuse_if_empty(book: Book) -> None:
    if book.spine_count <= _EMPTY_SPINE_MIN:
        return
    total = sum(
        extractable_characters(block.text) for chapter in book.chapters for block in chapter.blocks
    )
    if total < _EMPTY_TEXT_MIN_CHARS:
        raise AppError(
            ErrorCode.EBOOK_EMPTY_TEXT,
            detail={"spine_items": book.spine_count, "characters": total},
            message="epub spine has almost no extractable text",
        )
