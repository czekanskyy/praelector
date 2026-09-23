# SPDX-License-Identifier: Apache-2.0
"""DRM refusal (EB-01, EB-02).

``META-INF/encryption.xml`` may describe IDPF or Adobe font obfuscation. Those
two algorithm URIs are not DRM and must not refuse the book. Anything else
encrypted — an OPF or XHTML member, or an algorithm that is not font
obfuscation — refuses with ``ebook.drm_detected``. ``META-INF/sinf.xml``
(Apple FairPlay) and ``META-INF/rights.xml`` (ADEPT) refuse on their own.

An ``EncryptedKey`` that carries a ``CipherValue`` and no ``CipherReference``
is key-transport material, not a publication resource. Font-obfuscation
documents sometimes wrap one next to the font entry; that wrapper is not
itself a reason to refuse. There is no key input and no decryption attempt.
"""

from __future__ import annotations

import zipfile
from typing import Final, NoReturn
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from praelector.ebook.markup import attr, local_name, parse_xml
from praelector.errors import AppError, ErrorCode

#: The only encryption algorithms EPUB allows without being DRM. Order is not
#: significant; equality is on the full URI.
FONT_OBFUSCATION_ALGORITHMS: Final = frozenset(
    {
        "http://www.idpf.org/2008/embedding",
        "http://ns.adobe.com/pdf/enc#RC",
    }
)

#: A font-obfuscation URI aimed at one of these is still DRM: the publication
#: text or package document is encrypted.
_CONTENT_SUFFIXES: Final = frozenset({".opf", ".xhtml", ".html", ".htm", ".xht", ".ncx"})


def refuse_drm(archive: zipfile.ZipFile) -> None:
    """Raise ``ebook.drm_detected`` when the package is DRM-locked.

    Font obfuscation of a font file returns normally.
    """
    exact, folded = _member_index(archive)
    sinf = _meta(exact, folded, "sinf.xml")
    if sinf is not None:
        _refuse("sinf_xml", path=sinf)
    rights = _meta(exact, folded, "rights.xml")
    if rights is not None:
        _refuse("rights_xml", path=rights)
    encryption = _meta(exact, folded, "encryption.xml")
    if encryption is None:
        return
    try:
        payload = archive.read(encryption)
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        _refuse("encryption_unreadable", path=encryption, message=str(exc))
    try:
        root = parse_xml(payload, path=encryption)
    except AppError as exc:
        _refuse("encryption_unreadable", path=encryption, message=exc.message)
    _refuse_encrypted_resources(root)


def _refuse_encrypted_resources(root: ET.Element) -> None:
    for node in root.iter():
        if not isinstance(node.tag, str) or local_name(node.tag) != "EncryptedData":
            continue
        reference = _descendant_attr(node, "CipherReference", "URI")
        if reference is None or not reference.strip():
            # Key transport (CipherValue) is not a member of the publication.
            continue
        algorithm = (_descendant_attr(node, "EncryptionMethod", "Algorithm") or "").strip()
        resource = unquote(reference.split("#", 1)[0].split("?", 1)[0]).strip()
        suffix = _suffix(resource)
        if suffix in _CONTENT_SUFFIXES:
            _refuse("encrypted_content", path=resource, algorithm=algorithm)
        if algorithm not in FONT_OBFUSCATION_ALGORITHMS:
            _refuse("encryption_algorithm", path=resource, algorithm=algorithm)


def _descendant_attr(element: ET.Element, tag: str, name: str) -> str | None:
    for node in element.iter():
        if node is element or not isinstance(node.tag, str):
            continue
        if local_name(node.tag) == tag:
            return attr(node, name)
    return None


def _suffix(resource: str) -> str:
    clean = resource.replace("\\", "/").rstrip("/")
    slash = clean.rfind("/")
    leaf = clean[slash + 1 :] if slash >= 0 else clean
    dot = leaf.rfind(".")
    if dot < 0:
        return ""
    return leaf[dot:].casefold()


def _member_index(archive: zipfile.ZipFile) -> tuple[dict[str, str], dict[str, str]]:
    exact: dict[str, str] = {}
    folded: dict[str, str] = {}
    for name in archive.namelist():
        posix = name.replace("\\", "/")
        if posix.endswith("/"):
            continue
        exact.setdefault(posix, name)
        folded.setdefault(posix.casefold(), name)
    return exact, folded


def _meta(exact: dict[str, str], folded: dict[str, str], filename: str) -> str | None:
    key = f"META-INF/{filename}"
    found = exact.get(key)
    if found is not None:
        return found
    return folded.get(key.casefold())


def _refuse(reason: str, *, path: str, algorithm: str = "", message: str = "") -> NoReturn:
    detail: dict[str, str] = {"reason": reason, "path": path}
    if algorithm:
        detail["algorithm"] = algorithm
    raise AppError(
        ErrorCode.EBOOK_DRM_DETECTED,
        detail=detail,
        message=message or f"drm detected: {reason}",
    )
