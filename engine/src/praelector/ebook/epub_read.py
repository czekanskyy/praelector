# SPDX-License-Identifier: Apache-2.0
"""EPUB 2/3 reader using zipfile and lxml (EB-01, EB-02, EB-05, D-01)."""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from urllib.parse import unquote, urldefrag

from lxml import etree
from pydantic import BaseModel, Field

from praelector.domain.ids import generate_id
from praelector.ebook.blocks import ExtractedBlock, extract_blocks_from_xhtml
from praelector.ebook.drm import inspect_epub_drm
from praelector.errors import AppError


class ExtractedChapter(BaseModel):
    """Chapter extracted from an EPUB document."""

    id: str = Field(default_factory=lambda: generate_id("chp"))
    ordinal: int
    title: str
    source_href: str
    spine_index: int
    blocks: list[ExtractedBlock] = Field(default_factory=list)
    char_count: int = 0


class ExtractedEpub(BaseModel):
    """Full extracted representation of an EPUB book."""

    title: str
    authors: list[str] = Field(default_factory=list)
    language: str = "pl"
    identifier: str | None = None
    cover_image_bytes: bytes | None = None
    cover_image_mime: str | None = None
    chapters: list[ExtractedChapter] = Field(default_factory=list)
    total_char_count: int = 0


def _resolve_zip_path(base_dir: str, rel_path: str, namelist_lower: dict[str, str]) -> str | None:
    """Resolve an href relative to base_dir against zip namelist with case-insensitivity."""
    decoded = unquote(rel_path)
    clean_path, _ = urldefrag(decoded)
    if not clean_path:
        return None

    if base_dir:
        joined = posixpath.normpath(posixpath.join(base_dir, clean_path))
    else:
        joined = posixpath.normpath(clean_path)

    # Direct match
    if joined in namelist_lower.values():
        return joined

    # Case-insensitive match (PLAN §2)
    return namelist_lower.get(joined.lower())


def _xpath_elements(
    node: etree._Element, query: str, namespaces: dict[str, str] | None = None
) -> list[etree._Element]:
    """Execute an XPath query returning only Element nodes."""
    result = node.xpath(query, namespaces=namespaces)
    if isinstance(result, list):
        return [item for item in result if isinstance(item, etree._Element)]
    return []


def read_epub(file_path: Path | str) -> ExtractedEpub:
    """Read and parse an EPUB 2 or 3 file.

    Args:
        file_path: Path to the EPUB file.

    Returns:
        ExtractedEpub with metadata, cover image, and ordered chapters with blocks.

    Raises:
        AppError: On DRM detection, corruption, or empty text.
    """
    path = Path(file_path)
    if not path.is_file():
        raise AppError("internal.not_found", status_code=404, detail={"path": str(path)})

    if not zipfile.is_zipfile(path):
        raise AppError("ebook.corrupt", status_code=422, detail={"message": "Not a valid zip file"})

    with zipfile.ZipFile(path, "r") as zf:
        # 1. DRM Inspection
        inspect_epub_drm(zf)

        namelist_lower = {name.lower(): name for name in zf.namelist()}

        # 2. Locate container.xml
        container_path = namelist_lower.get("meta-inf/container.xml")
        if not container_path:
            raise AppError(
                "ebook.corrupt",
                status_code=422,
                detail={"message": "META-INF/container.xml missing from EPUB"},
            )

        try:
            container_xml = zf.read(container_path)
            c_root = etree.fromstring(container_xml)
        except Exception as exc:
            raise AppError(
                "ebook.corrupt",
                status_code=422,
                detail={"message": f"Failed to parse container.xml: {exc}"},
            ) from exc

        # Find OPF full-path
        rootfiles = _xpath_elements(
            c_root, "//*[local-name()='rootfile'][@media-type='application/oebps-package+xml']"
        )
        if not rootfiles:
            rootfiles = _xpath_elements(c_root, "//*[local-name()='rootfile']")
        if not rootfiles:
            raise AppError(
                "ebook.corrupt",
                status_code=422,
                detail={"message": "No rootfile found in container.xml"},
            )

        opf_rel_path = rootfiles[0].get("full-path", "") or ""
        opf_path = namelist_lower.get(opf_rel_path.lower())
        if not opf_path:
            raise AppError(
                "ebook.corrupt",
                status_code=422,
                detail={"message": f"OPF file '{opf_rel_path}' not found in archive"},
            )

        opf_dir = posixpath.dirname(opf_path)

        # 3. Parse OPF
        try:
            opf_xml = zf.read(opf_path)
            opf_root = etree.fromstring(opf_xml)
        except Exception as exc:
            raise AppError(
                "ebook.corrupt",
                status_code=422,
                detail={"message": f"Failed to parse OPF XML: {exc}"},
            ) from exc

        # Metadata extraction
        title_elems = _xpath_elements(
            opf_root, "//*[local-name()='metadata']/*[local-name()='title']"
        )
        title = (
            str(title_elems[0].text).strip()
            if title_elems and title_elems[0].text is not None
            else path.stem
        )

        creator_elems = _xpath_elements(
            opf_root, "//*[local-name()='metadata']/*[local-name()='creator']"
        )
        authors = [
            str(c.text).strip() for c in creator_elems if c.text is not None and str(c.text).strip()
        ]

        lang_elems = _xpath_elements(
            opf_root, "//*[local-name()='metadata']/*[local-name()='language']"
        )
        language = (
            str(lang_elems[0].text).strip()
            if lang_elems and lang_elems[0].text is not None
            else "pl"
        )

        id_elems = _xpath_elements(
            opf_root, "//*[local-name()='metadata']/*[local-name()='identifier']"
        )
        identifier = (
            str(id_elems[0].text).strip() if id_elems and id_elems[0].text is not None else None
        )

        # Manifest extraction: id -> {href, media_type, properties}
        manifest_items: dict[str, dict[str, str]] = {}
        cover_item_id: str | None = None

        for item in _xpath_elements(
            opf_root, "//*[local-name()='manifest']/*[local-name()='item']"
        ):
            item_id = item.get("id", "") or ""
            href = item.get("href", "") or ""
            media_type = item.get("media-type", "") or ""
            properties = item.get("properties", "") or ""

            manifest_items[item_id] = {
                "href": href,
                "media_type": media_type,
                "properties": properties,
            }

            if "cover-image" in properties.split():
                cover_item_id = item_id

        # Cover image detection fallbacks
        if not cover_item_id:
            cover_metas = _xpath_elements(
                opf_root, "//*[local-name()='metadata']/*[local-name()='meta'][@name='cover']"
            )
            if cover_metas:
                cover_item_id = cover_metas[0].get("content", "")

        if not cover_item_id:
            for i_id, i_data in manifest_items.items():
                if "cover" in i_id.lower() and i_data["media_type"].startswith("image/"):
                    cover_item_id = i_id
                    break

        cover_bytes: bytes | None = None
        cover_mime: str | None = None
        if cover_item_id and cover_item_id in manifest_items:
            cover_info = manifest_items[cover_item_id]
            cover_zip_path = _resolve_zip_path(opf_dir, cover_info["href"], namelist_lower)
            if cover_zip_path:
                try:
                    cover_bytes = zf.read(cover_zip_path)
                    cover_mime = cover_info["media_type"]
                except Exception:
                    pass

        # Spine extraction: ordered list of manifest items
        spine_itemrefs = _xpath_elements(
            opf_root, "//*[local-name()='spine']/*[local-name()='itemref']"
        )
        spine_items: list[tuple[str, str]] = []  # (idref, resolved_zip_path)
        for itemref in spine_itemrefs:
            idref = itemref.get("idref", "") or ""
            if idref in manifest_items:
                href = manifest_items[idref]["href"]
                resolved = _resolve_zip_path(opf_dir, href, namelist_lower)
                if resolved:
                    spine_items.append((idref, resolved))

        # TOC extraction (EPUB 3 nav document or EPUB 2 NCX)
        toc_titles: dict[str, str] = {}  # resolved_zip_path -> title

        # Check EPUB 3 Nav
        nav_item = next(
            (i for i in manifest_items.values() if "nav" in i["properties"].split()), None
        )
        if nav_item:
            nav_zip_path = _resolve_zip_path(opf_dir, nav_item["href"], namelist_lower)
            if nav_zip_path:
                try:
                    nav_content = zf.read(nav_zip_path)
                    nav_root = etree.fromstring(nav_content)
                    nav_links = _xpath_elements(
                        nav_root, "//*[local-name()='nav'][@*[local-name()='type']='toc']//a"
                    )
                    for a in nav_links:
                        link_href = a.get("href", "") or ""
                        link_title = "".join(str(t) for t in a.itertext()).strip()
                        resolved_target = _resolve_zip_path(
                            posixpath.dirname(nav_zip_path), link_href, namelist_lower
                        )
                        if resolved_target and link_title and resolved_target not in toc_titles:
                            toc_titles[resolved_target] = link_title
                except Exception:
                    pass

        # Check EPUB 2 NCX
        ncx_item = next(
            (
                i
                for i in manifest_items.values()
                if i["media_type"] == "application/x-dtbncx+xml"
                or i["href"].lower().endswith(".ncx")
            ),
            None,
        )
        if ncx_item:
            ncx_zip_path = _resolve_zip_path(opf_dir, ncx_item["href"], namelist_lower)
            if ncx_zip_path:
                try:
                    ncx_content = zf.read(ncx_zip_path)
                    ncx_root = etree.fromstring(ncx_content)
                    for nav_point in _xpath_elements(ncx_root, "//*[local-name()='navPoint']"):
                        label_elems = _xpath_elements(
                            nav_point, ".//*[local-name()='navLabel']/*[local-name()='text']"
                        )
                        content_elems = _xpath_elements(nav_point, ".//*[local-name()='content']")
                        if label_elems and content_elems:
                            p_title = (
                                str(label_elems[0].text).strip()
                                if label_elems[0].text is not None
                                else ""
                            )
                            p_src = content_elems[0].get("src", "") or ""
                            resolved_p = _resolve_zip_path(
                                posixpath.dirname(ncx_zip_path), p_src, namelist_lower
                            )
                            if resolved_p and p_title and resolved_p not in toc_titles:
                                toc_titles[resolved_p] = p_title
                except Exception:
                    pass

        # 4. Extract chapters and blocks
        chapters: list[ExtractedChapter] = []
        total_chars = 0
        spine_count = len(spine_items)

        for spine_idx, (_idref, zip_entry_path) in enumerate(spine_items):
            try:
                raw_xhtml = zf.read(zip_entry_path)
            except Exception:
                continue

            # Extract blocks
            blocks = extract_blocks_from_xhtml(raw_xhtml, source_href=zip_entry_path)

            chapter_text_len = sum(len(b.text) for b in blocks)
            total_chars += chapter_text_len

            # Determine title
            ch_title = toc_titles.get(zip_entry_path)
            if not ch_title and blocks:
                # Find first heading block if any
                first_heading = next((b.text for b in blocks if b.kind.value == "heading"), None)
                if first_heading:
                    ch_title = first_heading
            if not ch_title:
                ch_title = f"Chapter {spine_idx + 1}"

            chapter = ExtractedChapter(
                ordinal=spine_idx + 1,
                title=ch_title,
                source_href=zip_entry_path,
                spine_index=spine_idx,
                blocks=blocks,
                char_count=chapter_text_len,
            )
            chapters.append(chapter)

        # 5. Fail-closed empty-text check (EB-02)
        # "spine > 3 items but < 200 extractable chars"
        if spine_count > 3 and total_chars < 200:
            raise AppError(
                "ebook.empty_text",
                status_code=422,
                detail={
                    "spine_count": spine_count,
                    "chars_found": total_chars,
                    "message": (
                        f"Empty text detected: spine has {spine_count} items "
                        f"but only {total_chars} readable characters were found."
                    ),
                },
            )

        if total_chars == 0:
            raise AppError(
                "ebook.empty_text",
                status_code=422,
                detail={
                    "spine_count": spine_count,
                    "chars_found": 0,
                    "message": "The ebook contains no readable text.",
                },
            )

        return ExtractedEpub(
            title=title,
            authors=authors,
            language=language,
            identifier=identifier,
            cover_image_bytes=cover_bytes,
            cover_image_mime=cover_mime,
            chapters=chapters,
            total_char_count=total_chars,
        )
