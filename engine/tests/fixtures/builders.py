# SPDX-License-Identifier: Apache-2.0
"""Test fixture builders for EPUB and PDF documents (PLAN §10)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from pypdf import PdfWriter


def create_epub2_minimal(path: Path) -> Path:
    """Create a minimal valid EPUB 2.0 archive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        # mimetype uncompressed
        zinfo = zipfile.ZipInfo("mimetype")
        zinfo.compress_type = zipfile.ZIP_STORED
        zf.writestr(zinfo, b"application/epub+zip")

        # META-INF/container.xml
        zf.writestr(
            "META-INF/container.xml",
            b'<?xml version="1.0"?>'
            b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b"  <rootfiles>"
            b'    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            b"  </rootfiles>"
            b"</container>",
        )

        # OEBPS/content.opf
        zf.writestr(
            "OEBPS/content.opf",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="BookId">'
            b'  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            b"    <dc:title>Minimal EPUB 2</dc:title>"
            b"    <dc:creator>Test Author</dc:creator>"
            b"    <dc:language>en</dc:language>"
            b'    <dc:identifier id="BookId">urn:uuid:test-epub2</dc:identifier>'
            b"  </metadata>"
            b"  <manifest>"
            b'    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            b'    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            b'    <item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>'
            b"  </manifest>"
            b'  <spine toc="ncx">'
            b'    <itemref idref="ch1"/>'
            b'    <itemref idref="ch2"/>'
            b"  </spine>"
            b"</package>",
        )

        # OEBPS/toc.ncx
        zf.writestr(
            "OEBPS/toc.ncx",
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
            b"  <navMap>"
            b'    <navPoint id="np-1" playOrder="1">'
            b"      <navLabel><text>First Chapter</text></navLabel>"
            b'      <content src="ch1.xhtml"/>'
            b"    </navPoint>"
            b'    <navPoint id="np-2" playOrder="2">'
            b"      <navLabel><text>Second Chapter</text></navLabel>"
            b'      <content src="ch2.xhtml"/>'
            b"    </navPoint>"
            b"  </navMap>"
            b"</ncx>",
        )

        # OEBPS/ch1.xhtml
        zf.writestr(
            "OEBPS/ch1.xhtml",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
            b'<html xmlns="http://www.w3.org/1999/xhtml">'
            b"<head><title>First Chapter</title></head>"
            b"<body>"
            b"  <h1>First Chapter</h1>"
            b"  <p>This is the first paragraph of minimal EPUB 2 test document.</p>"
            b"</body>"
            b"</html>",
        )

        # OEBPS/ch2.xhtml
        zf.writestr(
            "OEBPS/ch2.xhtml",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
            b'<html xmlns="http://www.w3.org/1999/xhtml">'
            b"<head><title>Second Chapter</title></head>"
            b"<body>"
            b"  <h1>Second Chapter</h1>"
            b"  <p>Here is some additional text in the second chapter.</p>"
            b"</body>"
            b"</html>",
        )

    return path


def create_epub3_minimal(path: Path) -> Path:
    """Create a minimal valid EPUB 3.0 archive."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zinfo = zipfile.ZipInfo("mimetype")
        zinfo.compress_type = zipfile.ZIP_STORED
        zf.writestr(zinfo, b"application/epub+zip")

        zf.writestr(
            "META-INF/container.xml",
            b'<?xml version="1.0"?>'
            b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b"  <rootfiles>"
            b'    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>'
            b"  </rootfiles>"
            b"</container>",
        )

        zf.writestr(
            "EPUB/package.opf",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">'
            b'  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            b"    <dc:title>Minimal EPUB 3</dc:title>"
            b"    <dc:creator>Alice Author</dc:creator>"
            b"    <dc:language>en</dc:language>"
            b'    <dc:identifier id="uid">urn:uuid:test-epub3</dc:identifier>'
            b'    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>'
            b"  </metadata>"
            b"  <manifest>"
            b'    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            b'    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            b'    <item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>'
            b"  </manifest>"
            b"  <spine>"
            b'    <itemref idref="ch1"/>'
            b'    <itemref idref="ch2"/>'
            b"  </spine>"
            b"</package>",
        )

        zf.writestr(
            "EPUB/nav.xhtml",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b"<!DOCTYPE html>"
            b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
            b"<head><title>TOC</title></head>"
            b"<body>"
            b'  <nav epub:type="toc">'
            b"    <h2>Contents</h2>"
            b"    <ol>"
            b'      <li><a href="ch1.xhtml">Chapter One</a></li>'
            b'      <li><a href="ch2.xhtml">Chapter Two</a></li>'
            b"    </ol>"
            b"  </nav>"
            b"</body>"
            b"</html>",
        )

        zf.writestr(
            "EPUB/ch1.xhtml",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b"<!DOCTYPE html>"
            b'<html xmlns="http://www.w3.org/1999/xhtml">'
            b"<head><title>Chapter One</title></head>"
            b"<body>"
            b"  <h1>Chapter One</h1>"
            b"  <p>The dawn broke over the misty valley with a quiet splendour.</p>"
            b"</body>"
            b"</html>",
        )

        zf.writestr(
            "EPUB/ch2.xhtml",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b"<!DOCTYPE html>"
            b'<html xmlns="http://www.w3.org/1999/xhtml">'
            b"<head><title>Chapter Two</title></head>"
            b"<body>"
            b"  <h1>Chapter Two</h1>"
            b"  <p>They traveled along the ancient path until dusk fell upon them.</p>"
            b"</body>"
            b"</html>",
        )

    return path


def create_epub3_polish_novel(path: Path) -> Path:
    """Create a realistic Polish novel EPUB 3 fixture with chapters, dialogue dashes, and frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zinfo = zipfile.ZipInfo("mimetype")
        zinfo.compress_type = zipfile.ZIP_STORED
        zf.writestr(zinfo, b"application/epub+zip")

        zf.writestr(
            "META-INF/container.xml",
            b'<?xml version="1.0"?>'
            b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b"  <rootfiles>"
            b'    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            b"  </rootfiles>"
            b"</container>",
        )

        # 1x1 dummy JPEG for cover
        dummy_cover_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        zf.writestr("OEBPS/cover.jpg", dummy_cover_bytes)

        zf.writestr(
            "OEBPS/content.opf",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">'
            b'  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            b"    <dc:title>Kroniki Wrzosowiska</dc:title>"
            b"    <dc:creator>Jan Kowalski</dc:creator>"
            b"    <dc:language>pl</dc:language>"
            b'    <dc:identifier id="pub-id">urn:uuid:pl-novel-001</dc:identifier>'
            b'    <meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>'
            b"  </metadata>"
            b"  <manifest>"
            b'    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            b'    <item id="cover-img" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>'
            b'    <item id="front" href="front.xhtml" media-type="application/xhtml+xml"/>'
            b'    <item id="ch01" href="ch01.xhtml" media-type="application/xhtml+xml"/>'
            b'    <item id="ch02" href="ch02.xhtml" media-type="application/xhtml+xml"/>'
            b'    <item id="back" href="back.xhtml" media-type="application/xhtml+xml"/>'
            b"  </manifest>"
            b"  <spine>"
            b'    <itemref idref="front"/>'
            b'    <itemref idref="ch01"/>'
            b'    <itemref idref="ch02"/>'
            b'    <itemref idref="back"/>'
            b"  </spine>"
            b"</package>",
        )

        zf.writestr(
            "OEBPS/nav.xhtml",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b"<!DOCTYPE html>"
            b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
            b"<head><title>Spis tre\xc5\x9bci</title></head>"
            b"<body>"
            b'  <nav epub:type="toc">'
            b"    <h2>Spis tre\xc5\x9bci</h2>"
            b"    <ol>"
            b'      <li><a href="front.xhtml">Karta redakcyjna</a></li>'
            b'      <li><a href="ch01.xhtml">Rozdzia\xc5\x82 1 \xe2\x80\x94 Pocz\xc4\x85tek podr\xc3\xb3\xc5\xbcy</a></li>'
            b'      <li><a href="ch02.xhtml">Rozdzia\xc5\x82 2 \xe2\x80\x94 W cieniu puszczy</a></li>'
            b'      <li><a href="back.xhtml">Pos\xc5\x82owie</a></li>'
            b"    </ol>"
            b"  </nav>"
            b"</body>"
            b"</html>",
        )

        # Frontmatter
        zf.writestr(
            "OEBPS/front.xhtml",
            (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
                "<head><title>Karta redakcyjna</title></head><body>"
                "<h1>Karta redakcyjna</h1>"
                "<p>Copyright © 2026 Jan Kowalski. Wszelkie prawa zastrzeżone.</p>"
                "<p>Wydawnictwo Literackie, Warszawa 2026. ISBN 978-83-00-12345-6.</p>"
                "<p>Projekt okładki: Anna Nowak. Korekta: Tomasz Zieliński.</p>"
                "</body></html>"
            ).encode(),
        )

        # Chapter 1 with Polish dialogue
        zf.writestr(
            "OEBPS/ch01.xhtml",
            (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
                "<head><title>Rozdział 1</title></head><body>"
                "<h1>Rozdział 1 — Początek podróży</h1>"
                "<p>Wiosenny poranek powitał wędrowców gęstą mgłą unoszącą się nad doliną rzeki.</p>"
                "<p>— Czy daleko jeszcze do traktu? — zapytał Michał, poprawiając ciężki plecak.</p>"
                "<p>— Godzina drogi, nie więcej — odparła z uśmiechem Anna. — Musimy tylko minąć stary wiatrak.</p>"
                "<p>Ruszyli naprzód wąską ścieżką wiodącą wzdłuż kamiennego muru.</p>"
                "</body></html>"
            ).encode(),
        )

        # Chapter 2
        zf.writestr(
            "OEBPS/ch02.xhtml",
            (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
                "<head><title>Rozdział 2</title></head><body>"
                "<h1>Rozdział 2 — W cieniu puszczy</h1>"
                "<p>Drzewa stawały się coraz gęstsze, a promienie słońca ledwie przebijały się przez korony sosen.</p>"
                "<p>— Spójrz na te ślady — rzekł cicho przewodnik. — Ktoś tędy szedł zaledwie godzinę temu.</p>"
                "<p>Michał skinął głową w milczeniu i wyciągnął kompas.</p>"
                "</body></html>"
            ).encode(),
        )

        # Backmatter
        zf.writestr(
            "OEBPS/back.xhtml",
            (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
                "<head><title>Posłowie</title></head><body>"
                "<h1>Posłowie</h1>"
                "<p>Dziękujemy za przeczytanie książki Kroniki Wrzosowiska.</p>"
                "<p>Polecamy także inne powieści tego autora dostępne w księgarniach.</p>"
                "</body></html>"
            ).encode(),
        )

    return path


def create_drm_encrypted_epub(path: Path, mode: str = "content") -> Path:
    """Create an EPUB fixture with DRM protection for refusal tests."""
    create_epub3_minimal(path)

    with zipfile.ZipFile(path, "a") as zf:
        if mode == "sinf":
            zf.writestr("META-INF/sinf.xml", b"<sinf/>")
        elif mode == "rights":
            zf.writestr("META-INF/rights.xml", b"<rights/>")
        else:
            # content encryption in encryption.xml
            enc_xml = (
                b'<?xml version="1.0" encoding="UTF-8"?>'
                b'<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                b'  <EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#">'
                b'    <EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
                b"    <CipherData>"
                b'      <CipherReference URI="EPUB/ch1.xhtml"/>'
                b"    </CipherData>"
                b"  </EncryptedData>"
                b"</encryption>"
            )
            zf.writestr("META-INF/encryption.xml", enc_xml)

    return path


def create_font_obfuscated_epub(path: Path) -> Path:
    """Create an EPUB fixture with legitimate font obfuscation (MUST NOT be refused)."""
    create_epub3_minimal(path)

    with zipfile.ZipFile(path, "a") as zf:
        zf.writestr("EPUB/fonts/custom.otf", b"\x00\x01\x00\x00" + b"\x00" * 64)

        enc_xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b'  <EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#">'
            b'    <EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>'
            b"    <CipherData>"
            b'      <CipherReference URI="EPUB/fonts/custom.otf"/>'
            b"    </CipherData>"
            b"  </EncryptedData>"
            b"</encryption>"
        )
        zf.writestr("META-INF/encryption.xml", enc_xml)

    return path


def create_empty_text_epub(path: Path) -> Path:
    """Create an EPUB fixture with 4 spine items but empty text (< 200 chars)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zinfo = zipfile.ZipInfo("mimetype")
        zinfo.compress_type = zipfile.ZIP_STORED
        zf.writestr(zinfo, b"application/epub+zip")

        zf.writestr(
            "META-INF/container.xml",
            b'<?xml version="1.0"?>'
            b'<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            b"  <rootfiles>"
            b'    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>'
            b"  </rootfiles>"
            b"</container>",
        )

        zf.writestr(
            "content.opf",
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">'
            b'  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            b"    <dc:title>Empty Book</dc:title>"
            b"    <dc:language>en</dc:language>"
            b'    <dc:identifier id="uid">urn:uuid:empty</dc:identifier>'
            b"  </metadata>"
            b"  <manifest>"
            b'    <item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
            b'    <item id="c2" href="c2.xhtml" media-type="application/xhtml+xml"/>'
            b'    <item id="c3" href="c3.xhtml" media-type="application/xhtml+xml"/>'
            b'    <item id="c4" href="c4.xhtml" media-type="application/xhtml+xml"/>'
            b"  </manifest>"
            b"  <spine>"
            b'    <itemref idref="c1"/>'
            b'    <itemref idref="c2"/>'
            b'    <itemref idref="c3"/>'
            b'    <itemref idref="c4"/>'
            b"  </spine>"
            b"</package>",
        )

        for name in ("c1.xhtml", "c2.xhtml", "c3.xhtml", "c4.xhtml"):
            zf.writestr(name, b"<html><body>   </body></html>")

    return path


def create_no_text_layer_pdf(path: Path) -> Path:
    """Create a PDF without an extractable text layer (e.g. scanned blank pages)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=595, height=842)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def create_encrypted_pdf(path: Path) -> Path:
    """Create a password-encrypted PDF fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.encrypt("topsecret")
    with open(path, "wb") as f:
        writer.write(f)
    return path


def create_text_layer_pdf(path: Path) -> Path:
    """Create a PDF with a valid, readable text layer (> 200 chars)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text_content = (
        "To jest testowy dokument PDF posiadający pełną warstwę tekstową. "
        "Zawiera on znacznie więcej niż wymagane dwieście znaków tekstu, aby "
        "sonda modułu praelector.ebook.pdf mogła pomyślnie potwierdzić obecność "
        "nadającego się do odczytu tekstu. Lektor będzie mógł przygotować "
        "rozdziały do późniejszej syntezy głosu na podstawie tego pliku źródłowego."
    )
    # Generate minimal valid PDF with BT/ET stream
    stream_bytes = f"BT /F1 12 Tf 50 750 Td ({text_content}) Tj ET".encode(
        "latin-1", errors="replace"
    )
    stream_len = len(stream_bytes)

    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
        b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj\n"
        b"4 0 obj <</Length " + str(stream_len).encode("ascii") + b">>\n"
        b"stream\n" + stream_bytes + b"\nendstream\nendobj\n"
        b"5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000056 00000 n \n"
        b"0000000111 00000 n \n"
        b"0000000228 00000 n \n"
        b"0000000550 00000 n \n"
        b"trailer <</Size 6 /Root 1 0 R>>\n"
        b"startxref\n"
        b"650\n"
        b"%%EOF\n"
    )

    with open(path, "wb") as f:
        f.write(pdf_bytes)
    return path
