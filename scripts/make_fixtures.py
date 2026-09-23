#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate the cross-language test fixtures deterministically (PLAN.md §10)."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import struct
import sys
import wave
import zipfile
import zlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path("fixtures")

# Byte-reproducible archives need a pinned timestamp; this is the earliest one a ZIP
# header can express.
FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_MODIFIED = "2026-01-01T00:00:00Z"
MIMETYPE = b"application/epub+zip"

SAMPLE_RATE = 24_000
SAMPLE_SECONDS = 3.0
SWEEP_FROM_HZ = 110.0
SWEEP_TO_HZ = 1_760.0
AMPLITUDE = 16_384
PADDING_SECONDS = 0.5

# Real algorithm URIs: the fixture has to look like the DRM the engine must refuse
# (EB-01, EB-02), not like a placeholder a test would happily ignore.
XML_ENC_AES128_CBC = "http://www.w3.org/2001/04/xmlenc#aes128-cbc"
XML_ENC_RSA_1_5 = "http://www.w3.org/2001/04/xmlenc#rsa-1_5"
IDPF_FONT_OBFUSCATION = "http://www.idpf.org/2008/embedding"

# PDF fixtures are NOT generated here; see the note printed by main().
PDF_FIXTURES = ("books/no_text_layer.pdf", "books/text_layer.pdf")


@dataclass(frozen=True)
class Item:
    item_id: str
    href: str
    media_type: str
    properties: str = ""


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# The golden chapter, verbatim from PLAN.md §10.1. It carries a soft hyphen inside
# `egzemplarzy` (&#173; below), a double space after `zegar.`, and a hyphenated line
# break, because those are exactly the conversion artifacts AI-02 has to catch.
GOLDEN_PARAGRAPHS: tuple[str, ...] = (
    "Rozdział 8",
    "Anna odłożyła raport i spojrzała na zegar.  Było wpół do trzeciej.",
    "— Nie zdążymy — powiedziała cicho. — Deadline mamy o 18:00.",
    "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz.",
    "Barnaba zapytał: — Ile mamy egzem\u00adplarzy?",
    "— 238 — odpowiedziała Anna. — Reszta poszła do Washington DC.",
    (
        "W IT nikt nie odbierał telefonu. Na biurku leżała notatka: „Briefing prze-\n"
        "sunięty na XIV piętro”."
    ),
    "ISBN 978-83-000000-0-0",
    "12",
)

NOVEL_CHAPTER_2: tuple[str, ...] = (
    "Rozdział 9",
    (
        "Deszcz padał od rana i ulice zrobiły się puste. Anna wracała pieszo, bo "
        "ostatni tramwaj odjechał bez niej."
    ),
    "— Miałaś odpocząć — powiedział Marek, kiedy otworzyła drzwi.",
    "— Odpocznę w poniedziałek — odpowiedziała i postawiła teczkę na podłodze.",
    (
        "W kuchni pachniało kawą. Na stole leżała kartka z jednym zdaniem: „Nie "
        "odbieraj telefonu od Barnaby”."
    ),
    "Anna długo patrzyła na te słowa, a potem schowała kartkę do kieszeni.",
)

NOVEL_CHAPTER_3: tuple[str, ...] = (
    "Rozdział 10",
    (
        "Rano przyszła paczka. Dwanaście egzemplarzy, wszystkie z tym samym błędem na "
        "stronie czterdziestej."
    ),
    "— Kto to zatwierdził? — zapytał Marek.",
    "Nikt nie odpowiedział. Za oknem przejechał samochód i znowu zrobiło się cicho.",
    (
        "Anna policzyła książki jeszcze raz, a potem napisała wiadomość do drukarni: "
        "proszę o wstrzymanie wysyłki do odwołania."
    ),
    (
        "Wieczorem Barnaba przyszedł bez zapowiedzi. Stał w progu, mokry, i trzymał w "
        "ręku jedną książkę."
    ),
    "— To nie jest błąd — powiedział. — To jest poprawka.",
)

TITLE_PAGE: tuple[str, ...] = ("Cisza w archiwum", "Marta Zaremba")

IMPRINT_PARAGRAPHS: tuple[str, ...] = (
    "Cisza w archiwum",
    "Copyright © 2026 Marta Zaremba",
    "Wydanie pierwsze, Warszawa 2026",
    "Wydawnictwo Praelector, ul. Przykładowa 12, 00-001 Warszawa",
    "ISBN 978-83-000000-1-7",
    (
        "Wszelkie prawa zastrzeżone. Przedruk całości lub fragmentów wyłącznie za "
        "pisemną zgodą wydawcy."
    ),
    "Skład i łamanie: pracownia własna wydawnictwa",
)


def xhtml(
    title: str, body: str, *, lang: str = "pl", epub2: bool = False, style: bool = False
) -> bytes:
    doctype = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
        '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
        if epub2
        else ""
    )
    link = '<link rel="stylesheet" type="text/css" href="style.css"/>\n' if style else ""
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"{doctype}"
        f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}">\n'
        "<head>\n"
        f"<title>{escape(title)}</title>\n"
        f"{link}"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )
    return document.encode("utf-8")


def paragraphs_to_body(paragraphs: Iterable[str], *, heading: bool = True) -> str:
    lines: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        # escape() keeps newlines: a hyphenated line break is a conversion artifact the
        # text pipeline has to remove, so it must survive into the fixture as-is.
        text = escape(paragraph)
        if heading and index == 0:
            lines.append(f"<h2>{text}</h2>\n")
        else:
            lines.append(f"<p>{text}</p>\n")
    return "".join(lines)


def container_xml(opf_path: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        "  <rootfiles>\n"
        f'    <rootfile full-path="{opf_path}" media-type="application/oebps-package+xml"/>\n'
        "  </rootfiles>\n"
        "</container>\n"
    ).encode()


def build_opf(
    *,
    version: str,
    identifier: str,
    title: str,
    language: str,
    items: Sequence[Item],
    spine: Sequence[str],
    ncx_id: str | None = None,
    creator: str | None = None,
    description: str | None = None,
) -> bytes:
    epub3 = version.startswith("3")
    manifest_lines = []
    for item in items:
        properties = f' properties="{item.properties}"' if item.properties else ""
        manifest_lines.append(
            f'    <item id="{item.item_id}" href="{item.href}" '
            f'media-type="{item.media_type}"{properties}/>'
        )
    spine_lines = [f'    <itemref idref="{idref}"/>' for idref in spine]

    metadata = [
        f'    <dc:identifier id="pub-id">{identifier}</dc:identifier>',
        f"    <dc:title>{escape(title)}</dc:title>",
        f"    <dc:language>{language}</dc:language>",
    ]
    if creator:
        metadata.append(f"    <dc:creator>{escape(creator)}</dc:creator>")
    if description:
        metadata.append(f"    <dc:description>{escape(description)}</dc:description>")
    if epub3:
        metadata.append(f'    <meta property="dcterms:modified">{FIXED_MODIFIED}</meta>')

    # EPUB 2 points at its NCX from the spine; EPUB 3 uses a nav document instead.
    toc_attribute = f' toc="{ncx_id}"' if ncx_id else ""
    unique = ' unique-identifier="pub-id"' if epub3 else ""
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" '
        f'xmlns:dc="http://purl.org/dc/elements/1.1/" version="{version}"{unique}>\n'
        "  <metadata>\n" + "\n".join(metadata) + "\n  </metadata>\n"
        "  <manifest>\n" + "\n".join(manifest_lines) + "\n  </manifest>\n"
        f"  <spine{toc_attribute}>\n" + "\n".join(spine_lines) + "\n  </spine>\n"
        "</package>\n"
    )
    return document.encode("utf-8")


def build_ncx(identifier: str, title: str, entries: Sequence[tuple[str, str, str]]) -> bytes:
    nav_points = [
        f'    <navPoint id="{play_order}" playOrder="{order}">\n'
        f"      <navLabel><text>{escape(label)}</text></navLabel>\n"
        f'      <content src="{src}"/>\n'
        f"    </navPoint>"
        for order, (label, src, play_order) in enumerate(entries, start=1)
    ]
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        "  <head>\n"
        f'    <meta name="dtb:uid" content="{identifier}"/>\n'
        '    <meta name="dtb:depth" content="1"/>\n'
        '    <meta name="dtb:totalPageCount" content="0"/>\n'
        '    <meta name="dtb:maxPageNumber" content="0"/>\n'
        "  </head>\n"
        f"  <docTitle><text>{escape(title)}</text></docTitle>\n"
        "  <navMap>\n" + "\n".join(nav_points) + "\n  </navMap>\n"
        "</ncx>\n"
    )
    return document.encode("utf-8")


def build_nav(title: str, entries: Sequence[tuple[str, str]], *, lang: str = "pl") -> bytes:
    items = "".join(
        f'        <li><a href="{src}">{escape(label)}</a></li>\n' for label, src in entries
    )
    body = (
        f'<nav xmlns:epub="http://www.idpf.org/2007/ops" epub:type="toc" id="toc">\n'
        f"      <h1>{escape(title)}</h1>\n"
        f"      <ol>\n{items}      </ol>\n"
        f"    </nav>\n"
    )
    return xhtml(title, body, lang=lang)


def build_stylesheet() -> bytes:
    return (
        b"body { margin: 1.5em; font-family: serif; line-height: 1.5; }\n"
        b"h1, h2 { font-weight: 600; }\n"
        b"p { text-indent: 1.5em; margin: 0; }\n"
        b"img.cover { max-width: 100%; }\n"
    )


def png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A solid-colour PNG; small enough to commit, deterministic enough to diff."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def pseudo_ciphertext(seed: str, size: int) -> bytes:
    """Deterministic filler standing in for AES-encrypted resource bytes."""
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(f"{seed}:{counter}".encode()).digest()
        counter += 1
    return bytes(out[:size])


def idpf_obfuscation_key(identifier: str) -> bytes:
    # IDPF font obfuscation derives the key from the publication identifier with the
    # `urn:uuid:` prefix and all whitespace removed, then SHA-1s the result. SHA-1 is
    # what the specification mandates; nothing here is a security decision.
    cleaned = identifier.replace("urn:uuid:", "").replace(" ", "")
    return hashlib.sha1(cleaned.encode("utf-8"), usedforsecurity=False).digest()


def idpf_obfuscate(payload: bytes, identifier: str) -> bytes:
    key = idpf_obfuscation_key(identifier)
    head = bytearray(payload[:1040])
    for index in range(len(head)):
        head[index] ^= key[index % len(key)]
    return bytes(head) + payload[1040:]


def fake_otf(size: int = 4096) -> bytes:
    # Only the header has to look like a font; the fixture exercises obfuscation and
    # detection, never rasterisation.
    return b"OTTO" + struct.pack(">IHHHH", 0x00010000, 0, 0, 0, 0) + b"\x00" * (size - 16)


def write_epub(entries: Sequence[tuple[str, bytes]]) -> bytes:
    if not entries or entries[0][0] != "mimetype" or entries[0][1] != MIMETYPE:
        raise ValueError("the first EPUB entry must be an uncompressed 'mimetype'")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for index, (name, payload) in enumerate(entries):
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE_TIME)
            # Pinned create_system and mode: without them the same builder produces
            # different bytes on Windows and on ubuntu-latest.
            info.create_system = 3
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED if index == 0 else zipfile.ZIP_DEFLATED
            bundle.writestr(info, payload)
    return buffer.getvalue()


def build_epub2_minimal() -> bytes:
    identifier = "urn:uuid:11111111-2222-3333-4444-000000000002"
    chapter = xhtml(
        "Chapter One",
        "<h1>Chapter One</h1>\n<p>It was a bright cold day in April.</p>\n",
        lang="en",
        epub2=True,
        style=True,
    )
    items = [
        Item("ncx", "toc.ncx", "application/x-dtbncx+xml"),
        Item("css", "style.css", "text/css"),
        Item("ch01", "ch01.xhtml", "application/xhtml+xml"),
    ]
    opf = build_opf(
        version="2.0",
        identifier=identifier,
        title="Minimal EPUB 2",
        language="en",
        items=items,
        spine=["ch01"],
        ncx_id="ncx",
        creator="Praelector Fixtures",
    )
    ncx = build_ncx(identifier, "Minimal EPUB 2", [("Chapter One", "ch01.xhtml", "ch01")])
    return write_epub(
        [
            ("mimetype", MIMETYPE),
            ("META-INF/container.xml", container_xml("OEBPS/content.opf")),
            ("OEBPS/content.opf", opf),
            ("OEBPS/toc.ncx", ncx),
            ("OEBPS/style.css", build_stylesheet()),
            ("OEBPS/ch01.xhtml", chapter),
        ]
    )


def build_epub3_minimal() -> bytes:
    identifier = "urn:uuid:11111111-2222-3333-4444-000000000003"
    chapter = xhtml(
        "Chapter One",
        "<h1>Chapter One</h1>\n<p>It was a bright cold day in April.</p>\n",
        lang="en",
        style=True,
    )
    items = [
        Item("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        Item("css", "style.css", "text/css"),
        Item("ch01", "ch01.xhtml", "application/xhtml+xml"),
    ]
    opf = build_opf(
        version="3.0",
        identifier=identifier,
        title="Minimal EPUB 3",
        language="en",
        items=items,
        spine=["nav", "ch01"],
        creator="Praelector Fixtures",
    )
    nav = build_nav("Contents", [("Chapter One", "ch01.xhtml")], lang="en")
    return write_epub(
        [
            ("mimetype", MIMETYPE),
            ("META-INF/container.xml", container_xml("OEBPS/content.opf")),
            ("OEBPS/content.opf", opf),
            ("OEBPS/nav.xhtml", nav),
            ("OEBPS/style.css", build_stylesheet()),
            ("OEBPS/ch01.xhtml", chapter),
        ]
    )


def build_epub3_polish_novel() -> bytes:
    identifier = "urn:uuid:11111111-2222-3333-4444-000000000004"
    title, author = TITLE_PAGE
    cover_png = png(400, 600, (46, 74, 108))

    cover_page = xhtml(
        "Okładka",
        '<div class="cover"><img class="cover" src="images/cover.png" alt="Okładka"/></div>\n',
    )
    title_page = xhtml(
        title,
        f"<h1>{escape(title)}</h1>\n<p>{escape(author)}</p>\n",
    )
    imprint = xhtml(
        "Stopka redakcyjna",
        paragraphs_to_body(IMPRINT_PARAGRAPHS, heading=False),
    )
    chapters = [
        ("ch01.xhtml", "Rozdział 8", GOLDEN_PARAGRAPHS),
        ("ch02.xhtml", "Rozdział 9", NOVEL_CHAPTER_2),
        ("ch03.xhtml", "Rozdział 10", NOVEL_CHAPTER_3),
    ]
    chapter_docs = [
        (href, xhtml(heading, paragraphs_to_body(body))) for href, heading, body in chapters
    ]

    items = [
        Item("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        Item("css", "style.css", "text/css"),
        Item("cover-image", "images/cover.png", "image/png", "cover-image"),
        Item("cover", "cover.xhtml", "application/xhtml+xml"),
        Item("titlepage", "titlepage.xhtml", "application/xhtml+xml"),
        Item("imprint", "imprint.xhtml", "application/xhtml+xml"),
        *(
            Item(f"ch{index:02d}", href, "application/xhtml+xml")
            for index, (href, _, _) in enumerate(chapters, start=1)
        ),
    ]
    opf = build_opf(
        version="3.0",
        identifier=identifier,
        title=title,
        language="pl",
        items=items,
        spine=["cover", "titlepage", "imprint", "ch01", "ch02", "ch03"],
        creator=author,
        description="Trzyrozdziałowa powieść testowa wygenerowana przez make_fixtures.py.",
    )
    nav_entries = [
        ("Okładka", "cover.xhtml"),
        ("Karta tytułowa", "titlepage.xhtml"),
        ("Stopka redakcyjna", "imprint.xhtml"),
        *((heading, href) for href, heading, _ in chapters),
    ]
    nav = build_nav("Spis treści", nav_entries)

    entries: list[tuple[str, bytes]] = [
        ("mimetype", MIMETYPE),
        ("META-INF/container.xml", container_xml("OEBPS/content.opf")),
        ("OEBPS/content.opf", opf),
        ("OEBPS/nav.xhtml", nav),
        ("OEBPS/style.css", build_stylesheet()),
        ("OEBPS/images/cover.png", cover_png),
        ("OEBPS/cover.xhtml", cover_page),
        ("OEBPS/titlepage.xhtml", title_page),
        ("OEBPS/imprint.xhtml", imprint),
    ]
    entries += [(f"OEBPS/{href}", doc) for href, doc in chapter_docs]
    return write_epub(entries)


def encryption_xml(
    *, algorithm: str, resource: str, key_name: str = "PraelectorFixtureKey"
) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"\n'
        '            xmlns:enc="http://www.w3.org/2001/04/xmlenc#"\n'
        '            xmlns:ds="http://www.w3.org/2000/09/xmldsig#">\n'
        '  <enc:EncryptedData Id="ED1" Type="http://www.w3.org/2001/04/xmlenc#Element">\n'
        f'    <enc:EncryptionMethod Algorithm="{algorithm}"/>\n'
        "    <ds:KeyInfo>\n"
        '      <ds:RetrievalMethod URI="#EK1"\n'
        '        Type="http://www.w3.org/2001/04/xmlenc#EncryptedKey"/>\n'
        "    </ds:KeyInfo>\n"
        "    <enc:CipherData>\n"
        f'      <enc:CipherReference URI="{resource}"/>\n'
        "    </enc:CipherData>\n"
        "  </enc:EncryptedData>\n"
        '  <enc:EncryptedData Id="EK1" Type="http://www.w3.org/2001/04/xmlenc#EncryptedKey">\n'
        f'    <enc:EncryptionMethod Algorithm="{XML_ENC_RSA_1_5}"/>\n'
        "    <ds:KeyInfo>\n"
        f"      <ds:KeyName>{escape(key_name)}</ds:KeyName>\n"
        "    </ds:KeyInfo>\n"
        "    <enc:CipherData>\n"
        "      <enc:CipherValue>AQAB-fixture-key-material-not-real</enc:CipherValue>\n"
        "    </enc:CipherData>\n"
        "  </enc:EncryptedData>\n"
        "</encryption>\n"
    ).encode()


def rights_xml() -> bytes:
    # ADEPT keeps an encrypted licence blob here. The fixture only needs the file to
    # exist so drm.py has a second signal beyond encryption.xml; the bytes are inert.
    blob = base64.b64encode(pseudo_ciphertext("drm_encrypted:rights", 192)).decode("ascii")
    wrapped = "\n".join(blob[index : index + 64] for index in range(0, len(blob), 64))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rights xmlns="http://ns.adobe.com/adept">\n'
        f"  <blob>\n{wrapped}\n  </blob>\n"
        "</rights>\n"
    ).encode()


def build_drm_encrypted() -> bytes:
    identifier = "urn:uuid:11111111-2222-3333-4444-000000000005"
    # The declared-encrypted resource holds ciphertext, not markup: an implementation
    # that ignores encryption.xml would otherwise parse this fixture happily and the
    # fail-closed test would prove nothing.
    encrypted_chapter = pseudo_ciphertext("drm_encrypted:ch01", 4096)
    plain_chapter = xhtml(
        "Rozdział 2",
        "<h1>Rozdział 2</h1>\n<p>Ten rozdział nie jest zaszyfrowany.</p>\n",
    )
    items = [
        Item("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        Item("ch01", "ch01.xhtml", "application/xhtml+xml"),
        Item("ch02", "ch02.xhtml", "application/xhtml+xml"),
    ]
    opf = build_opf(
        version="3.0",
        identifier=identifier,
        title="DRM Encrypted Fixture",
        language="pl",
        items=items,
        spine=["ch01", "ch02"],
        creator="Praelector Fixtures",
    )
    nav = build_nav("Spis treści", [("Rozdział 1", "ch01.xhtml"), ("Rozdział 2", "ch02.xhtml")])
    return write_epub(
        [
            ("mimetype", MIMETYPE),
            ("META-INF/container.xml", container_xml("OEBPS/content.opf")),
            (
                "META-INF/encryption.xml",
                encryption_xml(
                    algorithm=XML_ENC_AES128_CBC,
                    resource="OEBPS/ch01.xhtml",
                    key_name="ADEPT",
                ),
            ),
            ("META-INF/rights.xml", rights_xml()),
            ("OEBPS/content.opf", opf),
            ("OEBPS/nav.xhtml", nav),
            ("OEBPS/ch01.xhtml", encrypted_chapter),
            ("OEBPS/ch02.xhtml", plain_chapter),
        ]
    )


def build_font_obfuscated() -> bytes:
    identifier = "urn:uuid:11111111-2222-3333-4444-000000000006"
    font = idpf_obfuscate(fake_otf(), identifier)
    chapter = xhtml(
        "Rozdział 1",
        "<h1>Rozdział 1</h1>\n<p>Tekst jest czytelny, zaszyfrowany jest tylko font.</p>\n",
        style=True,
    )
    items = [
        Item("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        Item("css", "style.css", "text/css"),
        Item("font01", "fonts/CharisSIL-Regular.otf", "application/vnd.ms-opentype"),
        Item("ch01", "ch01.xhtml", "application/xhtml+xml"),
    ]
    opf = build_opf(
        version="3.0",
        identifier=identifier,
        title="Font Obfuscation Fixture",
        language="pl",
        items=items,
        spine=["ch01"],
        creator="Praelector Fixtures",
    )
    nav = build_nav("Spis treści", [("Rozdział 1", "ch01.xhtml")])
    return write_epub(
        [
            ("mimetype", MIMETYPE),
            ("META-INF/container.xml", container_xml("OEBPS/content.opf")),
            (
                "META-INF/encryption.xml",
                encryption_xml(
                    algorithm=IDPF_FONT_OBFUSCATION,
                    resource="OEBPS/fonts/CharisSIL-Regular.otf",
                    key_name="IDPF font obfuscation",
                ),
            ),
            ("OEBPS/content.opf", opf),
            ("OEBPS/nav.xhtml", nav),
            ("OEBPS/style.css", build_stylesheet()),
            ("OEBPS/fonts/CharisSIL-Regular.otf", font),
            ("OEBPS/ch01.xhtml", chapter),
        ]
    )


def build_empty_text() -> bytes:
    identifier = "urn:uuid:11111111-2222-3333-4444-000000000007"
    # Five spine items, none of them carrying a single character of running text:
    # exactly the shape EB-02 must refuse instead of producing an empty audiobook.
    pages = [
        ("page01.xhtml", '<div class="cover"><img src="images/page01.png" alt=""/></div>\n'),
        ("page02.xhtml", "<p> </p>\n"),
        ("page03.xhtml", "<div>\u00a0</div>\n"),
        ("page04.xhtml", '<div class="cover"><img src="images/page01.png" alt=""/></div>\n'),
        ("page05.xhtml", ""),
    ]
    items = [
        Item("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        Item("img01", "images/page01.png", "image/png"),
        *(
            Item(f"page{index:02d}", href, "application/xhtml+xml")
            for index, (href, _) in enumerate(pages, start=1)
        ),
    ]
    opf = build_opf(
        version="3.0",
        identifier=identifier,
        title="Empty Text Fixture",
        language="pl",
        items=items,
        spine=[f"page{index:02d}" for index in range(1, 6)],
        creator="Praelector Fixtures",
    )
    nav = build_nav(
        "Spis treści",
        [(f"Strona {index}", f"page{index:02d}.xhtml") for index in range(1, 6)],
    )
    entries: list[tuple[str, bytes]] = [
        ("mimetype", MIMETYPE),
        ("META-INF/container.xml", container_xml("OEBPS/content.opf")),
        ("OEBPS/content.opf", opf),
        ("OEBPS/nav.xhtml", nav),
        ("OEBPS/images/page01.png", png(64, 64, (200, 200, 200))),
    ]
    entries += [
        (f"OEBPS/{href}", xhtml(f"Strona {index}", body))
        for index, (href, body) in enumerate(pages, start=1)
    ]
    return write_epub(entries)


def build_golden_text() -> bytes:
    return ("\n\n".join(GOLDEN_PARAGRAPHS) + "\n").encode("utf-8")


def golden_expectation_rows() -> tuple[dict[str, Any], ...]:
    """The 20 assertions from PLAN.md §10.1, as structured data.

    Span offsets stay null: only the M2 golden test knows the block boundaries the
    segmenter produces, and guessing them here would bake a wrong expectation into
    the fixture.
    """

    def row(
        index: int,
        feature: str,
        requirements: Sequence[str],
        surface: str | None,
        expected: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": index,
            "feature": feature,
            "requirements": list(requirements),
            "surface": surface,
            "expected": expected,
            "spans": None,
        }

    return (
        row(
            1,
            "ordinal_heading",
            ["AI-02"],
            "Rozdział 8",
            {"category": "numeral", "spoken": "Rozdział ósmy", "auto_apply": True},
        ),
        row(
            2,
            "double_space",
            ["AI-02"],
            "na zegar.  Było",
            {"category": "conversion_artifact", "action": "collapse", "auto_apply": True},
        ),
        row(
            3,
            "paragraph_initial_em_dash",
            ["DG-01"],
            "— Nie zdążymy — powiedziała cicho. — Deadline mamy o 18:00.",
            {
                "segments": [
                    {"kind": "dialogue", "text": "Nie zdążymy"},
                    {"kind": "narration", "text": "powiedziała cicho."},
                    {"kind": "dialogue", "text": "Deadline mamy o 18:00."},
                ]
            },
        ),
        row(
            4,
            "gender_from_verb_suffix",
            ["DG-03", "DG-04"],
            "powiedziała",
            {"gender": "female", "min_confidence": 0.95},
        ),
        row(
            5,
            "english_token",
            ["AI-08", "D-12"],
            "Deadline",
            {"categories": ["foreign_word", "dict_hit"], "spoken": None},
        ),
        row(
            6,
            "time_numeral",
            ["AI-02", "D-11"],
            "18:00",
            {"category": "numeral", "spoken": "osiemnastej", "auto_apply": True},
        ),
        row(
            7,
            "mid_paragraph_dash_after_narration",
            ["DG-02"],
            "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz.",
            {
                "segments": [
                    {"kind": "narration", "text": "Walker wzruszył ramionami."},
                    {"kind": "dialogue", "text": "A jednak spróbujemy"},
                    {"kind": "narration", "text": "mruknął i wyszedł na korytarz."},
                ]
            },
        ),
        row(
            8,
            "gender_male_and_speaker_label",
            ["DG-03", "DG-06"],
            "mruknął",
            {"gender": "male", "speaker_id": "Walker"},
        ),
        row(
            9,
            "foreign_surname",
            ["AI-02"],
            "Walker",
            {"category": "foreign_word", "spoken": "Łoker"},
        ),
        row(
            10,
            "colon_plus_dash_mid_paragraph",
            ["DG-02"],
            "Barnaba zapytał: — Ile mamy egzemplarzy?",
            {
                "segments": [
                    {"kind": "narration", "text": "Barnaba zapytał:"},
                    {"kind": "dialogue", "text": "Ile mamy egzemplarzy?"},
                ]
            },
        ),
        row(
            11,
            "male_name_ending_in_a",
            ["DG-04"],
            "Barnaba",
            {"gender": "male", "reason": "verb `zapytał` agrees; lexicon must not flip it"},
        ),
        row(
            12,
            "digits_inside_dialogue",
            ["AI-02"],
            "238",
            {"category": "numeral", "spoken": "dwieście trzydzieści osiem", "auto_apply": True},
        ),
        row(
            13,
            "toponym",
            ["AI-02"],
            "Washington DC",
            {"category": "toponym", "spoken": "Łoszynkton di si"},
        ),
        row(
            14,
            "acronym",
            ["AI-02"],
            "IT",
            {"category": "acronym", "spoken": "aj ti"},
        ),
        row(
            15,
            "hyphenation_across_line_break",
            ["AI-02"],
            "prze-\nsunięty",
            {"category": "conversion_artifact", "spoken": "przesunięty", "auto_apply": True},
        ),
        row(
            16,
            "soft_hyphen",
            ["AI-02"],
            "egzem\u00adplarzy",
            {
                "category": "conversion_artifact",
                "spoken": "egzemplarzy",
                "silent": True,
                "auto_apply": True,
            },
        ),
        row(
            17,
            "roman_numeral",
            ["AI-02"],
            "XIV",
            {"category": "numeral", "spoken": "czternaste", "auto_apply": True},
        ),
        row(
            18,
            "quote_without_speech_verb",
            ["DG-02"],
            "„Briefing prze-\nsunięty na XIV piętro”.",
            {
                "stays": "narration",
                "max_suggestion_confidence": 0.40,
                "suggestion_category": "dialogue_split",
                "auto_apply": False,
            },
        ),
        row(
            19,
            "isbn_line",
            ["EB-08"],
            "ISBN 978-83-000000-0-0",
            {"kind": "skip", "spoken": None},
        ),
        row(
            20,
            "bare_page_number",
            ["EB-08"],
            "12",
            {"kind": "skip", "spoken": None},
        ),
    )


def build_golden_expectations() -> bytes:
    payload = {
        "_note": (
            "Skeleton expectations for fixtures/text/pl_chapter_01.txt, mirroring the "
            "20-row table in docs/plan/PLAN.md §10.1. Every `spans` field is null on "
            "purpose: the precise (block_id, start, end) offsets are filled in by the "
            "M2 golden test once the segmenter and the dialogue state machine exist. "
            "A JSON file cannot carry comments, so this key is the comment."
        ),
        "fixture": "pl_chapter_01.txt",
        "language": "pl",
        "schema_version": 1,
        "assertions": [dict(row) for row in golden_expectation_rows()],
    }
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def synth_sweep(seconds: float, rate: int) -> bytes:
    """Logarithmic sine sweep, integer PCM16: the reference voice sample for TTS-04."""
    frames = bytearray()
    phase = 0.0
    ratio = SWEEP_TO_HZ / SWEEP_FROM_HZ
    total = round(seconds * rate)
    for index in range(total):
        progress = index / total
        frequency = SWEEP_FROM_HZ * (ratio**progress)
        phase += 2.0 * math.pi * frequency / rate
        sample = round(AMPLITUDE * math.sin(phase))
        frames += struct.pack("<h", max(-32768, min(32767, sample)))
    return bytes(frames)


def wav_payload(frames: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(frames)
    return buffer.getvalue()


def build_voice_sample() -> bytes:
    return wav_payload(synth_sweep(SAMPLE_SECONDS, SAMPLE_RATE), SAMPLE_RATE)


def build_voice_sample_padded() -> bytes:
    # The silence trim and LUFS passes need leading and trailing silence to bite on.
    silence = b"\x00\x00" * round(PADDING_SECONDS * SAMPLE_RATE)
    return wav_payload(silence + synth_sweep(SAMPLE_SECONDS, SAMPLE_RATE) + silence, SAMPLE_RATE)


BUILDERS: dict[str, Callable[[], bytes]] = {
    "books/epub2_minimal.epub": build_epub2_minimal,
    "books/epub3_minimal.epub": build_epub3_minimal,
    "books/epub3_polish_novel.epub": build_epub3_polish_novel,
    "books/drm_encrypted.epub": build_drm_encrypted,
    "books/font_obfuscated.epub": build_font_obfuscated,
    "books/empty_text.epub": build_empty_text,
    "text/pl_chapter_01.txt": build_golden_text,
    "text/pl_chapter_01.expected.json": build_golden_expectations,
    "audio/voice_sample.wav": build_voice_sample,
    "audio/voice_sample_silence_padded.wav": build_voice_sample_padded,
}


def selected(names: Sequence[str]) -> list[str]:
    if not names:
        return list(BUILDERS)

    def matches(key: str, name: str) -> bool:
        return key == name or Path(key).name == name or Path(key).stem == name

    wanted = {name.strip().replace("\\", "/").removeprefix("fixtures/") for name in names}
    unknown = sorted(name for name in wanted if not any(matches(key, name) for key in BUILDERS))
    if unknown:
        raise ValueError(
            f"unknown fixture(s): {', '.join(unknown)}\n"
            f"       known fixtures: {', '.join(sorted(BUILDERS))}"
        )
    return [key for key in BUILDERS if any(matches(key, name) for name in wanted)]


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="make_fixtures.py",
        description=(
            "Generate the deterministic fixtures under fixtures/ (EPUB, WAV and the "
            "Polish golden chapter). Only the generator is reviewed, so output must "
            "be byte-reproducible: fixed ZIP timestamps, modes and no randomness."
        ),
        epilog="exit codes: 0 written or already present, 2 usage error",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate fixtures that already exist",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=[],
        metavar="NAME",
        help="limit the run to these fixtures (path, file name or stem)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the fixtures this script owns and exit",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (default: the parent of scripts/)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root: Path = args.root.resolve()
    base = root / FIXTURES_DIR

    if args.list:
        for key in sorted(BUILDERS):
            print(key)
        for key in PDF_FIXTURES:
            print(f"{key}  (not generated here)")
        return 0

    try:
        keys = selected(args.only)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    written = 0
    skipped = 0
    for key in keys:
        target = base / Path(*key.split("/"))
        if target.exists() and not args.force:
            print(f"skip    {key} (exists; pass --force to regenerate)")
            skipped += 1
            continue
        payload = BUILDERS[key]()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        print(f"wrote   {key} ({len(payload):,} bytes)")
        written += 1

    print(
        "note    "
        + ", ".join(Path(key).name for key in PDF_FIXTURES)
        + " are not generated by this script: they are committed binaries produced "
        "by an external tool (a print-to-PDF export for no_text_layer.pdf, a "
        "LaTeX/Word export for text_layer.pdf) and live under fixtures/books/."
    )
    print(f"ok: {written} written, {skipped} already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
