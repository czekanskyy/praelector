# SPDX-License-Identifier: Apache-2.0
"""XML helpers for the hand-rolled EPUB reader.

EPUB content has to be XML, so this is the stdlib parser plus the HTML named
entities real XHTML uses (``&nbsp;``) and that ElementTree does not know.
External entities are rejected rather than resolved.
"""

from __future__ import annotations

import codecs
import html.entities
import re
from pathlib import PurePosixPath
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from praelector.errors import AppError, ErrorCode

_XML_BUILTIN = frozenset({"amp", "lt", "gt", "quot", "apos"})
_NAMED_ENTITY = re.compile(r"&([A-Za-z][A-Za-z0-9]+);")
_DECL_ENCODING = re.compile(rb"""encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""", re.IGNORECASE)
_MAX_XML_BYTES = 32 * 1024 * 1024


def local_name(tag: str) -> str:
    """The tag without its ``{namespace}`` prefix."""
    if tag.startswith("{"):
        return tag.rpartition("}")[2]
    return tag


def attr(element: ET.Element, name: str) -> str | None:
    """An attribute by local name, ignoring namespaces."""
    if name in element.attrib:
        return element.attrib[name]
    want = name.casefold()
    for key, value in element.attrib.items():
        if local_name(key).casefold() == want:
            return value
    return None


def elements(element: ET.Element) -> list[ET.Element]:
    return [child for child in element if isinstance(child.tag, str)]


def direct(element: ET.Element, name: str) -> list[ET.Element]:
    want = name.casefold()
    return [child for child in elements(element) if local_name(child.tag).casefold() == want]


def first(element: ET.Element, name: str) -> ET.Element | None:
    """First element with this local name, including ``element`` itself."""
    want = name.casefold()
    for node in element.iter():
        if isinstance(node.tag, str) and local_name(node.tag).casefold() == want:
            return node
    return None


def element_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def directory_of(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return "" if parent == "." else parent


def resolve_href(base_dir: str, href: str) -> str:
    """Resolve an EPUB relative href to a zip-internal POSIX path.

    ``..`` that would leave the archive is ``ebook.parse_failed``. A path that
    normalises to another member inside the zip is kept.
    """
    raw = unquote(href.split("#", 1)[0].split("?", 1)[0]).strip()
    if not raw:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "empty_href"},
            message="epub href is empty",
        )
    if raw.startswith("/"):
        combined = raw[1:]
    elif base_dir:
        combined = f"{base_dir}/{raw}"
    else:
        combined = raw
    parts: list[str] = []
    for part in PurePosixPath(combined).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise AppError(
                    ErrorCode.EBOOK_PARSE_FAILED,
                    detail={"reason": "path_escape", "href": raw},
                    message="epub href escapes the archive",
                )
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "empty_href", "href": raw},
            message="epub href is empty",
        )
    return "/".join(parts)


def parse_xml(data: bytes, *, path: str) -> ET.Element:
    """Parse one EPUB XML member. Failures are ``ebook.parse_failed``."""
    if len(data) > _MAX_XML_BYTES:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "too_large", "path": path},
            message="epub xml member is too large",
        )
    text = _expand_entities(_decode_xml(data))
    if "<!ENTITY" in text[:8000].upper():
        # Custom entities are how a zip-of-xml becomes a billion laughs. EPUB
        # does not need them; the named HTML entities were expanded above.
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "xml_entity", "path": path},
            message="epub xml declares an entity",
        )
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise AppError(
            ErrorCode.EBOOK_PARSE_FAILED,
            detail={"reason": "xml", "path": path},
            message=f"epub xml did not parse: {path}",
        ) from exc


def _decode_xml(data: bytes) -> str:
    payload = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
    encoding = "utf-8"
    match = _DECL_ENCODING.search(payload[:240])
    if match is not None:
        declared = match.group(1).decode("ascii", "replace")
        try:
            codecs.lookup(declared)
        except LookupError:
            declared = "utf-8"
        encoding = declared
    try:
        return payload.decode(encoding)
    except UnicodeDecodeError:
        return payload.decode("utf-8", errors="replace")


def _expand_entities(text: str) -> str:
    """Replace HTML named entities ElementTree would reject.

    The five XML builtins stay as references. Expanding ``&amp;`` or ``&lt;``
    ourselves would hand the parser a bare ``&`` or a fake tag.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in _XML_BUILTIN:
            return match.group(0)
        mapped = html.entities.html5.get(f"{name};")
        if mapped is None:
            return match.group(0)
        return mapped

    return _NAMED_ENTITY.sub(replace, text)
