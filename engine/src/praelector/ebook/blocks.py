# SPDX-License-Identifier: Apache-2.0
"""XHTML to ordered blocks (EB-07, D-08).

Each block carries a ``source_ref`` of ``href`` (the zip member) and ``path``
(``/html/body/p[12]``). Decorative images are not blocks. The cover image is
not a block either: the reader keeps its bytes separately, and an ``alt`` on
that image is not narrated. A non-cover image with real alt text becomes a
caption, which is the only image text that survives.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Final
from xml.etree import ElementTree as ET

from praelector.domain.enums import BlockKind
from praelector.ebook.markup import attr, elements, local_name, parse_xml, resolve_href
from praelector.errors import AppError

_SKIP_TREES: Final = frozenset(
    {"script", "style", "svg", "math", "template", "nav", "video", "audio", "image"}
)
_HEADING_LEVELS: Final = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCK_KIND: Final = {
    "p": BlockKind.PARAGRAPH,
    "pre": BlockKind.PARAGRAPH,
    "dt": BlockKind.PARAGRAPH,
    "dd": BlockKind.PARAGRAPH,
    "td": BlockKind.PARAGRAPH,
    "th": BlockKind.PARAGRAPH,
    "li": BlockKind.LIST_ITEM,
    "blockquote": BlockKind.BLOCKQUOTE,
    "figcaption": BlockKind.CAPTION,
    "caption": BlockKind.CAPTION,
    **dict.fromkeys(_HEADING_LEVELS, BlockKind.HEADING),
}


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where a block came from. ``path`` is stable across a re-read of the same XHTML."""

    href: str
    path: str


@dataclass(frozen=True, slots=True)
class Block:
    """One narratable unit. ``ordinal`` is the position inside its source document."""

    kind: BlockKind
    text: str
    source_ref: SourceRef
    ordinal: int
    heading_level: int | None = None


def extractable_characters(text: str) -> int:
    """Characters a reader would actually speak. Whitespace, including NBSP, is not."""
    return sum(1 for char in text if not char.isspace())


def blocks_from_xhtml(
    data: bytes,
    *,
    href: str,
    cover_href: str | None = None,
) -> tuple[Block, ...]:
    """The blocks of one spine document, in document order."""
    root = parse_xml(data, path=href)
    body = _direct_child(root, "body")
    if body is None and local_name(root.tag) == "body":
        body = root
    parent = body if body is not None else root
    base = "/html/body" if body is not None or local_name(root.tag) == "html" else "/html"
    sink: list[Block] = []
    _walk_children(
        parent,
        base,
        None,
        _Context(href=href, doc_dir=_doc_dir(href), cover_href=cover_href),
        sink,
    )
    return tuple(sink)


@dataclass(frozen=True, slots=True)
class _Context:
    href: str
    doc_dir: str
    cover_href: str | None


def _doc_dir(href: str) -> str:
    slash = href.rfind("/")
    return href[:slash] if slash >= 0 else ""


def _direct_child(element: ET.Element, name: str) -> ET.Element | None:
    want = name.casefold()
    for child in elements(element):
        if local_name(child.tag).casefold() == want:
            return child
    return None


def _walk_children(
    element: ET.Element,
    path: str,
    force: BlockKind | None,
    ctx: _Context,
    sink: list[Block],
) -> None:
    counts: dict[str, int] = {}
    for child in elements(element):
        name = local_name(child.tag)
        counts[name] = counts.get(name, 0) + 1
        _walk(child, f"{path}/{name}[{counts[name]}]", force, ctx, sink)


def _walk(
    element: ET.Element,
    path: str,
    force: BlockKind | None,
    ctx: _Context,
    sink: list[Block],
) -> None:
    name = local_name(element.tag).casefold()
    if name in _SKIP_TREES:
        return
    if name == "img":
        _image_caption(element, path, ctx, sink)
        return
    kind = _BLOCK_KIND.get(name)
    if kind is not None and not _has_block_child(element):
        text = _render_text(element)
        if text:
            sink.append(
                Block(
                    kind=_forced(kind, force),
                    text=text,
                    source_ref=SourceRef(href=ctx.href, path=path),
                    ordinal=len(sink),
                    heading_level=_HEADING_LEVELS.get(name),
                )
            )
        return
    child_force = force
    if name == "blockquote":
        child_force = BlockKind.BLOCKQUOTE
    _walk_children(element, path, child_force, ctx, sink)


def _forced(kind: BlockKind, force: BlockKind | None) -> BlockKind:
    if force is BlockKind.BLOCKQUOTE and kind is BlockKind.PARAGRAPH:
        return BlockKind.BLOCKQUOTE
    return kind


def _has_block_child(element: ET.Element) -> bool:
    return any(local_name(child.tag).casefold() in _BLOCK_KIND for child in elements(element))


def _image_caption(element: ET.Element, path: str, ctx: _Context, sink: list[Block]) -> None:
    source = attr(element, "src")
    if source:
        try:
            resolved = resolve_href(ctx.doc_dir, source)
        except AppError:
            resolved = ""
        if ctx.cover_href is not None and resolved == ctx.cover_href:
            return
    if (attr(element, "role") or "").casefold() == "presentation":
        return
    alt = (attr(element, "alt") or "").strip()
    if not alt:
        return
    text = unicodedata.normalize("NFC", alt).strip()
    if not text:
        return
    sink.append(
        Block(
            kind=BlockKind.CAPTION,
            text=text,
            source_ref=SourceRef(href=ctx.href, path=path),
            ordinal=len(sink),
        )
    )


def _render_text(element: ET.Element) -> str:
    parts: list[str] = []
    _append_text(element, parts)
    return unicodedata.normalize("NFC", "".join(parts)).strip()


def _append_text(element: ET.Element, parts: list[str]) -> None:
    if element.text:
        parts.append(element.text)
    for child in elements(element):
        name = local_name(child.tag).casefold()
        if name == "br":
            parts.append("\n")
        elif name not in _SKIP_TREES and name != "img":
            _append_text(child, parts)
        if child.tail:
            parts.append(child.tail)
