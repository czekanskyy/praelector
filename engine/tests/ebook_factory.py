# SPDX-License-Identifier: Apache-2.0
"""Tiny EPUB/PDF bytes for ingest tests. Not collected by pytest."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence

MIMETYPE = b"application/epub+zip"
IDPF_FONT_OBFUSCATION = "http://www.idpf.org/2008/embedding"
ADOBE_FONT_OBFUSCATION = "http://ns.adobe.com/pdf/enc#RC"
AES_128_CBC = "http://www.w3.org/2001/04/xmlenc#aes128-cbc"


def epub_bytes(entries: Sequence[tuple[str, bytes]]) -> bytes:
    """Zip ``entries`` with ``mimetype`` stored when it is first, like a real EPUB."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for index, (name, payload) in enumerate(entries):
            info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if index == 0 else zipfile.ZIP_DEFLATED
            bundle.writestr(info, payload)
    return buffer.getvalue()


def container_xml(opf: str = "OEBPS/content.opf") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "  <rootfiles>\n"
        f'    <rootfile full-path="{opf}" media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>\n"
    ).encode()


def xhtml(title: str, body: str, *, lang: str = "en", epub2: bool = False) -> bytes:
    doctype = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
        '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
        if epub2
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"{doctype}"
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}">\n'
        f"<head><title>{_esc(title)}</title></head>\n"
        f"<body>\n{body}</body>\n</html>\n"
    ).encode()


def package(
    *,
    title: str,
    language: str,
    items: Sequence[tuple[str, str, str, str]],
    spine: Sequence[str],
    identifier: str,
    creator: str | None = None,
    version: str = "3.0",
    ncx_id: str | None = None,
) -> bytes:
    manifest = []
    for item_id, href, media, properties in items:
        extra = f' properties="{properties}"' if properties else ""
        manifest.append(f'    <item id="{item_id}" href="{href}" media-type="{media}"{extra}/>')
    spine_lines = [f'    <itemref idref="{idref}"/>' for idref in spine]
    metadata = [
        f'    <dc:identifier id="pub-id">{_esc(identifier)}</dc:identifier>',
        f"    <dc:title>{_esc(title)}</dc:title>",
        f"    <dc:language>{language}</dc:language>",
    ]
    if creator:
        metadata.append(f"    <dc:creator>{_esc(creator)}</dc:creator>")
    if version.startswith("3"):
        metadata.append('    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>')
    toc = f' toc="{ncx_id}"' if ncx_id else ""
    unique = ' unique-identifier="pub-id"' if version.startswith("3") else ""
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" '
        f'xmlns:dc="http://purl.org/dc/elements/1.1/" version="{version}"{unique}>\n'
        "  <metadata>\n" + "\n".join(metadata) + "\n  </metadata>\n"
        "  <manifest>\n" + "\n".join(manifest) + "\n  </manifest>\n"
        f"  <spine{toc}>\n" + "\n".join(spine_lines) + "\n  </spine>\n"
        "</package>\n"
    )
    return document.encode()


def tiny_epub3(*, isbn: bool = False) -> bytes:
    paragraphs = "<h1>Chapter One</h1>\n<p>It was a bright cold day in April.</p>\n"
    if isbn:
        paragraphs += "<p>ISBN 978-83-000000-0-0</p>\n"
    chapter = xhtml("Chapter One", paragraphs)
    nav = xhtml(
        "Contents",
        '<nav xmlns:epub="http://www.idpf.org/2007/ops" epub:type="toc" id="toc">\n'
        "<h1>Contents</h1>\n"
        '<ol><li><a href="ch01.xhtml">Chapter One</a></li></ol>\n'
        "</nav>\n",
    )
    opf = package(
        title="Tiny Book",
        language="en",
        creator="Ada Lovelace",
        identifier="urn:uuid:11111111-2222-3333-4444-000000000003",
        items=(
            ("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
            ("ch01", "ch01.xhtml", "application/xhtml+xml", ""),
        ),
        spine=("ch01",),
    )
    return epub_bytes(
        (
            ("mimetype", MIMETYPE),
            ("META-INF/container.xml", container_xml()),
            ("OEBPS/content.opf", opf),
            ("OEBPS/nav.xhtml", nav),
            ("OEBPS/ch01.xhtml", chapter),
        )
    )


def tiny_epub2() -> bytes:
    chapter = xhtml(
        "Chapter One",
        "<h1>Chapter One</h1>\n<p>It was a bright cold day in April.</p>\n",
        epub2=True,
    )
    ncx = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        b'  <head><meta name="dtb:uid" content="urn:uuid:epub2"/></head>\n'
        b"  <docTitle><text>Minimal EPUB 2</text></docTitle>\n"
        b"  <navMap>\n"
        b'    <navPoint id="ch01" playOrder="1">\n'
        b"      <navLabel><text>Chapter One</text></navLabel>\n"
        b'      <content src="ch01.xhtml"/>\n'
        b"    </navPoint>\n"
        b"  </navMap>\n"
        b"</ncx>\n"
    )
    opf = package(
        title="Minimal EPUB 2",
        language="en",
        creator="Praelector Fixtures",
        identifier="urn:uuid:11111111-2222-3333-4444-000000000002",
        version="2.0",
        ncx_id="ncx",
        items=(
            ("ncx", "toc.ncx", "application/x-dtbncx+xml", ""),
            ("ch01", "ch01.xhtml", "application/xhtml+xml", ""),
        ),
        spine=("ch01",),
    )
    return epub_bytes(
        (
            ("mimetype", MIMETYPE),
            ("META-INF/container.xml", container_xml()),
            ("OEBPS/content.opf", opf),
            ("OEBPS/toc.ncx", ncx),
            ("OEBPS/ch01.xhtml", chapter),
        )
    )


def spine_epub(bodies: Sequence[str]) -> bytes:
    """One spine document per body. An empty body is a whitespace-only paragraph."""
    items: list[tuple[str, str, str, str]] = []
    files: list[tuple[str, bytes]] = []
    spine: list[str] = []
    for index, body in enumerate(bodies, start=1):
        item_id = f"p{index:02d}"
        href = f"{item_id}.xhtml"
        inner = body if body else "<p> </p>"
        if body and not body.lstrip().startswith("<"):
            inner = f"<p>{_esc(body)}</p>"
        items.append((item_id, href, "application/xhtml+xml", ""))
        files.append((f"OEBPS/{href}", xhtml(item_id, inner)))
        spine.append(item_id)
    opf = package(
        title="Spine",
        language="pl",
        identifier="urn:uuid:spine",
        items=items,
        spine=spine,
    )
    entries = [
        ("mimetype", MIMETYPE),
        ("META-INF/container.xml", container_xml()),
        ("OEBPS/content.opf", opf),
        *files,
    ]
    return epub_bytes(entries)


def encryption_xml(algorithm: str, resource: str, *, wrapped_key: bool = False) -> bytes:
    key = ""
    if wrapped_key:
        key = (
            '  <enc:EncryptedData Id="EK1" '
            'Type="http://www.w3.org/2001/04/xmlenc#EncryptedKey">\n'
            '    <enc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#rsa-1_5"/>\n'
            "    <enc:CipherData><enc:CipherValue>AQAB</enc:CipherValue></enc:CipherData>\n"
            "  </enc:EncryptedData>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"\n'
        '            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">\n'
        "  <enc:EncryptedData>\n"
        f'    <enc:EncryptionMethod Algorithm="{algorithm}"/>\n'
        "    <enc:CipherData>\n"
        f'      <enc:CipherReference URI="{resource}"/>\n'
        "    </enc:CipherData>\n"
        "  </enc:EncryptedData>\n"
        f"{key}</encryption>\n"
    ).encode()


def with_meta(extra: Sequence[tuple[str, bytes]], *, chapter: bytes | None = None) -> bytes:
    """A one-chapter EPUB plus extra zip members (encryption.xml, a font, …)."""
    body = (
        chapter
        if chapter is not None
        else xhtml(
            "Chapter One",
            "<h1>Chapter One</h1>\n<p>The text stays readable.</p>\n",
        )
    )
    opf = package(
        title="Locked or not",
        language="en",
        creator="Ada Lovelace",
        identifier="urn:uuid:locked",
        items=(
            ("ch01", "ch01.xhtml", "application/xhtml+xml", ""),
            ("font", "fonts/font.otf", "font/otf", ""),
        ),
        spine=("ch01",),
    )
    entries: list[tuple[str, bytes]] = [
        ("mimetype", MIMETYPE),
        ("META-INF/container.xml", container_xml()),
        *extra,
        ("OEBPS/content.opf", opf),
        ("OEBPS/ch01.xhtml", body),
        ("OEBPS/fonts/font.otf", b"OTTO" + b"\x00" * 32),
    ]
    return epub_bytes(entries)


def pdf_bytes(text: str) -> bytes:
    """A one-page PDF whose text layer is ``text`` (ASCII). Empty text draws nothing."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 50 750 Td ({escaped}) Tj ET".encode("ascii") if text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
