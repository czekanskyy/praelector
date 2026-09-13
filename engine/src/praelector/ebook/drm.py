# SPDX-License-Identifier: Apache-2.0
"""DRM refusal inspection for EPUB, PDF, and MOBI (EB-01, EB-02)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from praelector.domain.enums import SourceFormat
from praelector.ebook.detect import detect_format
from praelector.errors import AppError

# Standard Font Obfuscation Algorithm URIs that are NOT DRM
ALLOWED_FONT_OBFUSCATION_URIS = frozenset(
    {
        "http://www.idpf.org/2008/embedding",
        "http://ns.adobe.com/pdf/enc/2008/type1",
        "http://ns.adobe.com/adobe-font-obfuscation",
        "urn:oasis:names:tc:opendocument:xmlns:container",
    }
)

FONT_EXTENSIONS = frozenset({".otf", ".ttf", ".woff", ".woff2", ".eot"})

# Explicit DRM metadata files inside EPUB containers
DRM_SPECIFIC_CONTAINER_FILES = frozenset(
    {
        "meta-inf/sinf.xml",
        "meta-inf/rights.xml",
        "meta-inf/license.xml",
        "meta-inf/adobereader.xml",
        "meta-inf/signatures.xml",
    }
)


def _xpath_elements(
    node: etree._Element, query: str, namespaces: dict[str, str] | None = None
) -> list[etree._Element]:
    """Execute an XPath query returning only Element nodes."""
    result = node.xpath(query, namespaces=namespaces)
    if isinstance(result, list):
        return [item for item in result if isinstance(item, etree._Element)]
    return []


def inspect_epub_drm(zf: zipfile.ZipFile) -> None:
    """Inspect an open EPUB zip archive for DRM encryption.

    Raises:
        AppError: with code 'ebook.drm_detected' if DRM protection is detected.
    """
    namelist_lower = {name.lower(): name for name in zf.namelist()}

    # 1. Check for DRM specific marker files
    for drm_file in DRM_SPECIFIC_CONTAINER_FILES:
        if drm_file in namelist_lower:
            actual_name = namelist_lower[drm_file]
            raise AppError(
                "ebook.drm_detected",
                status_code=422,
                detail={
                    "reason": "drm_metadata_present",
                    "file": actual_name,
                    "message": f"DRM metadata file '{actual_name}' detected in EPUB archive.",
                },
            )

    # 2. Check META-INF/encryption.xml
    encryption_key = "meta-inf/encryption.xml"
    if encryption_key not in namelist_lower:
        return  # No encryption metadata, clear

    actual_enc_name = namelist_lower[encryption_key]
    try:
        enc_xml_data = zf.read(actual_enc_name)
        root = etree.fromstring(enc_xml_data)
    except Exception as exc:
        raise AppError(
            "ebook.corrupt",
            status_code=422,
            detail={
                "message": f"Failed to parse encryption metadata XML: {exc}",
                "file": actual_enc_name,
            },
        ) from exc

    # Namespaces for XML-Enc
    ns = {"enc": "http://www.w3.org/2001/04/xmlenc#"}

    # Find all EncryptedData elements (with or without namespace)
    encrypted_data_elements = _xpath_elements(
        root, "//enc:EncryptedData | //*[local-name()='EncryptedData']", namespaces=ns
    )
    if not encrypted_data_elements:
        return

    for elem in encrypted_data_elements:
        # Check EncryptionMethod Algorithm
        method_elems = _xpath_elements(
            elem, ".//enc:EncryptionMethod | .//*[local-name()='EncryptionMethod']", namespaces=ns
        )
        algorithm = ""
        if method_elems:
            algorithm = method_elems[0].get("Algorithm", "") or ""

        # Check CipherData -> CipherReference URI (the encrypted file in the EPUB)
        cipher_refs = _xpath_elements(
            elem, ".//enc:CipherReference | .//*[local-name()='CipherReference']", namespaces=ns
        )
        target_uri = ""
        if cipher_refs:
            target_uri = cipher_refs[0].get("URI", "") or ""

        target_ext = Path(target_uri).suffix.lower()

        # If the target is NOT a font, or the algorithm is NOT one of the font obfuscation algorithms,
        # it is content DRM.
        is_font = target_ext in FONT_EXTENSIONS
        is_allowed_font_algo = algorithm in ALLOWED_FONT_OBFUSCATION_URIS

        if not (is_font and is_allowed_font_algo):
            reason = "content_encrypted" if not is_font else "unsupported_encryption_algorithm"
            raise AppError(
                "ebook.drm_detected",
                status_code=422,
                detail={
                    "reason": reason,
                    "target": target_uri,
                    "algorithm": algorithm,
                    "message": (
                        f"DRM encryption detected for resource '{target_uri}' "
                        f"(algorithm: {algorithm or 'unknown'})."
                    ),
                },
            )


def inspect_pdf_drm(path: Path) -> None:
    """Inspect a PDF file for password protection and DRM encryption.

    Raises:
        AppError: with code 'ebook.drm_detected' if the PDF is encrypted.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise AppError(
                "ebook.drm_detected",
                status_code=422,
                detail={
                    "reason": "pdf_encrypted",
                    "message": "PDF file is encrypted or password-protected.",
                },
            )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "ebook.corrupt",
            status_code=422,
            detail={"message": f"Could not read PDF file: {exc}"},
        ) from exc


def inspect_mobi_drm(path: Path) -> None:
    """Inspect a MOBI or AZW3 file for Mobipocket / Kindle DRM."""
    with open(path, "rb") as f:
        data = f.read(4096)

    # In Mobipocket, record 0 contains the MOBI header
    # Check for 'MOBI' or 'BOOKMOBI'
    mobi_idx = data.find(b"MOBI")
    if mobi_idx != -1 and mobi_idx + 16 <= len(data):
        # The 2-byte encryption_type is at offset 0x0C (12) from MOBI magic
        encryption_type = int.from_bytes(data[mobi_idx + 12 : mobi_idx + 14], "big")
        if encryption_type != 0:
            raise AppError(
                "ebook.drm_detected",
                status_code=422,
                detail={
                    "reason": "mobi_drm_detected",
                    "encryption_type": encryption_type,
                    "message": f"MOBI/AZW DRM encryption detected (type: {encryption_type}).",
                },
            )


def inspect_drm(file_path: Path | str, format_hint: SourceFormat | None = None) -> None:
    """Inspect an ebook file for DRM.

    Args:
        file_path: Path to the book file.
        format_hint: Optional pre-detected SourceFormat.

    Raises:
        AppError: If DRM is detected ('ebook.drm_detected') or format unsupported.
    """
    path = Path(file_path)
    fmt = format_hint or detect_format(path)

    if fmt == SourceFormat.EPUB:
        if not zipfile.is_zipfile(path):
            raise AppError(
                "ebook.corrupt",
                status_code=422,
                detail={"message": "Invalid EPUB zip file"},
            )
        with zipfile.ZipFile(path, "r") as zf:
            inspect_epub_drm(zf)

    elif fmt == SourceFormat.PDF:
        inspect_pdf_drm(path)

    elif fmt in (SourceFormat.MOBI, SourceFormat.AZW3):
        inspect_mobi_drm(path)
