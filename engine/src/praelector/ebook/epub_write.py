# SPDX-License-Identifier: Apache-2.0
"""Deterministic EPUB 3 writer (EB-06, D-01)."""

from __future__ import annotations

import html
import time
import zipfile
from pathlib import Path

from praelector.domain.enums import BlockKind
from praelector.ebook.epub_read import ExtractedEpub

FIXED_ZIP_DATETIME = (2026, 1, 1, 0, 0, 0)


def _create_zip_info(filename: str, compress: bool = True) -> zipfile.ZipInfo:
    """Create a deterministic ZipInfo entry with fixed timestamps and permissions."""
    zinfo = zipfile.ZipInfo(filename=filename, date_time=FIXED_ZIP_DATETIME)
    zinfo.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    zinfo.external_attr = 0o644 << 16
    return zinfo


def write_epub(epub_data: ExtractedEpub, output_path: Path | str) -> Path:
    """Write an ExtractedEpub object to a deterministic, valid EPUB 3 file.

    Args:
        epub_data: Extracted or updated ebook data.
        output_path: Target destination path for the .epub file.

    Returns:
        Path to the written file.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 1. Prepare XHTML content for each chapter
    chapter_entries: list[tuple[str, str, str]] = []  # (filename, item_id, title)
    chapter_files: dict[str, str] = {}

    for ch in epub_data.chapters:
        ch_filename = f"ch_{ch.ordinal:04d}.xhtml"
        ch_id = f"ch_{ch.ordinal:04d}"
        chapter_entries.append((ch_filename, ch_id, ch.title))

        body_elements: list[str] = []
        has_initial_heading = bool(ch.blocks) and ch.blocks[0].kind == BlockKind.HEADING
        if not has_initial_heading:
            body_elements.append(f"  <h1 data-prl-title='true'>{html.escape(ch.title)}</h1>")

        for blk in ch.blocks:
            escaped_text = html.escape(blk.text)
            attr_block_id = f'data-prl-block-id="{html.escape(blk.id)}"'

            if blk.kind == BlockKind.HEADING:
                lvl = blk.heading_level or 2
                body_elements.append(f"  <h{lvl} {attr_block_id}>{escaped_text}</h{lvl}>")
            elif blk.kind == BlockKind.BLOCKQUOTE:
                body_elements.append(
                    f"  <blockquote {attr_block_id}><p>{escaped_text}</p></blockquote>"
                )
            elif blk.kind == BlockKind.LIST_ITEM:
                body_elements.append(f"  <ul><li {attr_block_id}>{escaped_text}</li></ul>")
            elif blk.kind == BlockKind.CAPTION:
                body_elements.append(
                    f"  <figure><figcaption {attr_block_id}>{escaped_text}</figcaption></figure>"
                )
            else:  # Paragraph or fallback
                body_elements.append(f"  <p {attr_block_id}>{escaped_text}</p>")

        xhtml_content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<!DOCTYPE html>\n"
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            f'xml:lang="{html.escape(epub_data.language)}" lang="{html.escape(epub_data.language)}">\n'
            "<head>\n"
            f"  <title>{html.escape(ch.title)}</title>\n"
            '  <link rel="stylesheet" type="text/css" href="style.css"/>\n'
            "</head>\n"
            "<body>\n"
            f"{chr(10).join(body_elements)}\n"
            "</body>\n"
            "</html>\n"
        )
        chapter_files[ch_filename] = xhtml_content

    # 2. Prepare Navigation Document (nav.xhtml)
    nav_links = "\n".join(
        f'        <li><a href="{fname}">{html.escape(title)}</a></li>'
        for fname, _, title in chapter_entries
    )
    nav_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        f'xml:lang="{html.escape(epub_data.language)}" lang="{html.escape(epub_data.language)}">\n'
        "<head>\n"
        f"  <title>{html.escape(epub_data.title)} - Spis treści</title>\n"
        '  <link rel="stylesheet" type="text/css" href="style.css"/>\n'
        "</head>\n"
        "<body>\n"
        '  <nav epub:type="toc" id="toc">\n'
        "    <h2>Spis treści</h2>\n"
        "    <ol>\n"
        f"{nav_links}\n"
        "    </ol>\n"
        "  </nav>\n"
        "</body>\n"
        "</html>\n"
    )

    # 3. Prepare OPF package
    identifier = epub_data.identifier or f"urn:uuid:praelector-{int(time.time())}"
    authors_xml = "\n".join(
        f"    <dc:creator>{html.escape(a)}</dc:creator>" for a in epub_data.authors
    )
    if not authors_xml:
        authors_xml = "    <dc:creator>Unknown</dc:creator>"

    manifest_lines = [
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '    <item id="css" href="style.css" media-type="text/css"/>',
    ]

    has_cover = bool(epub_data.cover_image_bytes and epub_data.cover_image_mime)
    if has_cover:
        ext = "jpg" if "jpeg" in (epub_data.cover_image_mime or "") else "png"
        manifest_lines.append(
            f'    <item id="cover-image" href="cover.{ext}" '
            f'media-type="{epub_data.cover_image_mime}" properties="cover-image"/>'
        )

    for fname, item_id, _ in chapter_entries:
        manifest_lines.append(
            f'    <item id="{item_id}" href="{fname}" media-type="application/xhtml+xml"/>'
        )

    spine_lines = [f'    <itemref idref="{item_id}"/>' for _, item_id, _ in chapter_entries]

    opf_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'    <dc:identifier id="pub-id">{html.escape(identifier)}</dc:identifier>\n'
        f"    <dc:title>{html.escape(epub_data.title)}</dc:title>\n"
        f"    <dc:language>{html.escape(epub_data.language)}</dc:language>\n"
        f"{authors_xml}\n"
        '    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>\n'
        "  </metadata>\n"
        "  <manifest>\n"
        f"{chr(10).join(manifest_lines)}\n"
        "  </manifest>\n"
        "  <spine>\n"
        f"{chr(10).join(spine_lines)}\n"
        "  </spine>\n"
        "</package>\n"
    )

    # 4. Standard CSS
    style_content = (
        "body { font-family: sans-serif; line-height: 1.5; margin: 5%; }\n"
        "h1, h2, h3 { color: #333; margin-top: 1.5em; }\n"
        "p { text-indent: 1.2em; margin-top: 0; margin-bottom: 0.5em; }\n"
    )

    # 5. Write ZIP Archive deterministically
    with zipfile.ZipFile(out, "w") as zf:
        # File 1: mimetype uncompressed
        mimetype_info = _create_zip_info("mimetype", compress=False)
        zf.writestr(mimetype_info, b"application/epub+zip")

        # File 2: META-INF/container.xml
        container_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            "  <rootfiles>\n"
            '    <rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/>\n'
            "  </rootfiles>\n"
            "</container>\n"
        )
        container_info = _create_zip_info("META-INF/container.xml")
        zf.writestr(container_info, container_xml.encode("utf-8"))

        # File 3: OEBPS/content.opf
        opf_info = _create_zip_info("OEBPS/content.opf")
        zf.writestr(opf_info, opf_content.encode("utf-8"))

        # File 4: OEBPS/nav.xhtml
        nav_info = _create_zip_info("OEBPS/nav.xhtml")
        zf.writestr(nav_info, nav_content.encode("utf-8"))

        # File 5: OEBPS/style.css
        css_info = _create_zip_info("OEBPS/style.css")
        zf.writestr(css_info, style_content.encode("utf-8"))

        # File 6: Cover image (if present)
        if (
            has_cover
            and epub_data.cover_image_bytes
            and isinstance(epub_data.cover_image_bytes, bytes)
        ):
            ext = "jpg" if "jpeg" in (epub_data.cover_image_mime or "") else "png"
            cover_info = _create_zip_info(f"OEBPS/cover.{ext}")
            zf.writestr(cover_info, epub_data.cover_image_bytes)

        # Files 7+: Chapters
        for fname, _, _ in chapter_entries:
            ch_info = _create_zip_info(f"OEBPS/{fname}")
            zf.writestr(ch_info, chapter_files[fname].encode("utf-8"))

    return out
