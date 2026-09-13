# SPDX-License-Identifier: Apache-2.0
"""XHTML to ordered semantic block extraction (EB-07, D-08)."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from pydantic import BaseModel, Field

from praelector.domain.enums import BlockKind
from praelector.domain.ids import generate_id


class ExtractedBlock(BaseModel):
    """Semantic text block extracted from an ebook XHTML chapter document."""

    id: str = Field(default_factory=lambda: generate_id("blk"))
    ordinal: int
    kind: BlockKind
    heading_level: int | None = None
    text: str
    source_ref: dict[str, Any]
    source_ref_json: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.source_ref_json:
            self.source_ref_json = json.dumps(self.source_ref, sort_keys=True)


BLOCK_TAGS = frozenset(
    {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "li",
        "figcaption",
        "pre",
        "div",
        "section",
        "article",
    }
)

DROP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "svg",
        "math",
        "iframe",
        "object",
        "embed",
        "audio",
        "video",
    }
)


def normalize_block_text(raw_text: str) -> str:
    """Normalize extracted text for TTS preparation.

    Applies Unicode NFC normalization, removes soft hyphens and zero-width spaces,
    and collapses internal line breaks and consecutive horizontal whitespace into single spaces.
    """
    if not raw_text:
        return ""

    # 1. Unicode NFC
    text = unicodedata.normalize("NFC", raw_text)

    # 2. Strip soft hyphens and zero-width artifacts
    text = text.replace("\u00ad", "")  # soft hyphen
    text = text.replace("\u200b", "")  # zero-width space
    text = text.replace("\ufeff", "")  # BOM

    # 3. Collapse multiple spaces and newlines
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_blocks_from_xhtml(
    content: bytes | str,
    source_href: str,
    start_ordinal: int = 0,
) -> list[ExtractedBlock]:
    """Parse XHTML content and extract ordered semantic blocks.

    Args:
        content: Raw XHTML bytes or string.
        source_href: Relative path of the document inside the EPUB (e.g. 'OEBPS/ch01.xhtml').
        start_ordinal: Starting ordinal index for extracted blocks.

    Returns:
        List of ordered ExtractedBlock items.
    """
    soup = BeautifulSoup(content, "xml")

    # 1. Remove comments and blacklisted elements
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag_name in DROP_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()

    # 2. Drop decorative images (EB-07)
    for img in soup.find_all("img"):
        role = img.get("role", "")
        epub_type = img.get("epub:type", "")
        # Preserve cover image if tagged
        if "cover" in role or "cover" in epub_type:
            continue
        img.decompose()

    body = soup.body if soup.body is not None else soup

    blocks: list[ExtractedBlock] = []
    current_ordinal = start_ordinal

    def get_xpath_path(tag: Tag) -> str:
        parts: list[str] = []
        curr: Tag | None = tag
        while curr is not None and curr.name not in ("[document]", None):
            tag_name = curr.name.lower()
            name_count = 1
            if curr.parent:
                siblings = [
                    s for s in curr.parent.children if isinstance(s, Tag) and s.name == curr.name
                ]
                if len(siblings) > 1:
                    try:
                        name_count = siblings.index(curr) + 1
                    except ValueError:
                        name_count = 1
            parts.append(f"{tag_name}[{name_count}]" if name_count > 1 else tag_name)
            curr = curr.parent
        return "/" + "/".join(reversed(parts))

    def process_element(elem: Tag | NavigableString) -> None:
        nonlocal current_ordinal

        if isinstance(elem, NavigableString):
            text = normalize_block_text(str(elem))
            if text:
                source_ref = {"href": source_href, "path": "/html/body/text()"}
                block = ExtractedBlock(
                    ordinal=current_ordinal,
                    kind=BlockKind.PARAGRAPH,
                    heading_level=None,
                    text=text,
                    source_ref=source_ref,
                )
                blocks.append(block)
                current_ordinal += 1
            return

        tag_name = elem.name.lower()

        # Check for headings
        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = normalize_block_text(elem.get_text())
            if text:
                level = int(tag_name[1])
                xpath = get_xpath_path(elem)
                block = ExtractedBlock(
                    ordinal=current_ordinal,
                    kind=BlockKind.HEADING,
                    heading_level=level,
                    text=text,
                    source_ref={"href": source_href, "path": xpath},
                )
                blocks.append(block)
                current_ordinal += 1
            return

        # Check for paragraph
        if tag_name == "p":
            text = normalize_block_text(elem.get_text())
            if text:
                xpath = get_xpath_path(elem)
                block = ExtractedBlock(
                    ordinal=current_ordinal,
                    kind=BlockKind.PARAGRAPH,
                    heading_level=None,
                    text=text,
                    source_ref={"href": source_href, "path": xpath},
                )
                blocks.append(block)
                current_ordinal += 1
            return

        # Check for blockquote
        if tag_name == "blockquote":
            text = normalize_block_text(elem.get_text())
            if text:
                xpath = get_xpath_path(elem)
                block = ExtractedBlock(
                    ordinal=current_ordinal,
                    kind=BlockKind.BLOCKQUOTE,
                    heading_level=None,
                    text=text,
                    source_ref={"href": source_href, "path": xpath},
                )
                blocks.append(block)
                current_ordinal += 1
            return

        # Check for list items
        if tag_name == "li":
            text = normalize_block_text(elem.get_text())
            if text:
                xpath = get_xpath_path(elem)
                block = ExtractedBlock(
                    ordinal=current_ordinal,
                    kind=BlockKind.LIST_ITEM,
                    heading_level=None,
                    text=text,
                    source_ref={"href": source_href, "path": xpath},
                )
                blocks.append(block)
                current_ordinal += 1
            return

        # Check for caption
        if tag_name == "figcaption":
            text = normalize_block_text(elem.get_text())
            if text:
                xpath = get_xpath_path(elem)
                block = ExtractedBlock(
                    ordinal=current_ordinal,
                    kind=BlockKind.CAPTION,
                    heading_level=None,
                    text=text,
                    source_ref={"href": source_href, "path": xpath},
                )
                blocks.append(block)
                current_ordinal += 1
            return

        # Container elements (div, section, article, ul, ol, body, etc.)
        # Check if it has child block elements
        has_child_blocks = any(
            isinstance(child, Tag) and child.name.lower() in BLOCK_TAGS for child in elem.children
        )

        if has_child_blocks:
            for child in elem.children:
                if isinstance(child, (Tag, NavigableString)):
                    process_element(child)
        else:
            # Flat container without block children: treat as paragraph if non-empty
            text = normalize_block_text(elem.get_text())
            if text:
                xpath = get_xpath_path(elem)
                block = ExtractedBlock(
                    ordinal=current_ordinal,
                    kind=BlockKind.PARAGRAPH,
                    heading_level=None,
                    text=text,
                    source_ref={"href": source_href, "path": xpath},
                )
                blocks.append(block)
                current_ordinal += 1

    for child in body.children:
        if isinstance(child, (Tag, NavigableString)):
            process_element(child)

    return blocks
