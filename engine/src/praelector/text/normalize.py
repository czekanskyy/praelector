# SPDX-License-Identifier: Apache-2.0
"""Conversion-artifact suggestions (AI-02, PLAN.md §5.1 item 1).

NFC, horizontal whitespace runs, soft hyphens, a hyphenated line break, and
non-canonical dashes become ``conversion_artifact`` suggestions. The block
text is not rewritten; ``original`` keeps the glyphs that were seen.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from praelector.domain.enums import SuggestionCategory
from praelector.text.suggestion import Suggestion, make_suggestion

# U+00AD. A raw regex cannot spell this escape: ``\u`` is left intact there.
_SOFT = "\u00ad"
_KIND = SuggestionCategory.CONVERSION_ARTIFACT

# Joins ``word-\\nword`` and a soft hyphen used as the same line-break hyphen.
_HYPHEN_BREAK = re.compile(rf"([^\W\d_]+)(?:{_SOFT})?(?:-|{_SOFT})\r?\n([^\W\d_]+)")
_SOFT_WORD = re.compile(rf"[^\W\d_]*(?:{_SOFT}[^\W\d_]*)+")

# Horizontal spaces only. A line break is not collapsed: the hyphenation join
# is the one artifact that consumes a newline, and a blank line is structure.
_HSPACE = " \t\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000"
_HSPACE_RUN = re.compile(f"[{_HSPACE}]{{2,}}")

# Canonical dash is U+2014. Hyphen-like characters fold to ASCII "-".
_DASH = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "\u2014",
    "\u2013": "\u2014",
    "\u2015": "\u2014",
    "\u2212": "-",
    "\u2e3a": "\u2014",
    "\u2e3b": "\u2014",
    "\ufe58": "\u2014",
    "\ufe63": "-",
    "\uff0d": "-",
}

_HYPHENATION = 0.95
_DASH_CONFIDENCE = 0.9
_CERTAIN = 0.99


def normalization_suggestions(text: str) -> list[Suggestion]:
    """Artifact suggestions for ``text``, in offset order. ``text`` is unchanged."""
    occupied = bytearray(len(text))
    found: list[Suggestion] = []
    found.extend(_hyphenation(text, occupied))
    found.extend(_soft_hyphens(text, occupied))
    found.extend(_whitespace(text, occupied))
    found.extend(_dashes(text, occupied))
    found.extend(_nfc(text, occupied))
    found.sort(key=lambda item: (item.start, item.end, item.reason))
    return found


def _claim(
    text: str,
    occupied: bytearray,
    start: int,
    end: int,
    replacement: str,
    reason: str,
    confidence: float,
) -> Suggestion | None:
    if end <= start or any(occupied[start:end]):
        return None
    if text[start:end] == replacement:
        return None
    occupied[start:end] = b"\x01" * (end - start)
    return make_suggestion(
        text=text,
        start=start,
        end=end,
        replacement=replacement,
        kind=_KIND,
        reason=reason,
        confidence=confidence,
    )


def _hyphenation(text: str, occupied: bytearray) -> list[Suggestion]:
    found: list[Suggestion] = []
    for match in _HYPHEN_BREAK.finditer(text):
        replacement = (match.group(1) + match.group(2)).replace(_SOFT, "")
        item = _claim(
            text, occupied, match.start(), match.end(), replacement, "hyphenation", _HYPHENATION
        )
        if item is not None:
            found.append(item)
    return found


def _soft_hyphens(text: str, occupied: bytearray) -> list[Suggestion]:
    found: list[Suggestion] = []
    for match in _SOFT_WORD.finditer(text):
        item = _claim(
            text,
            occupied,
            match.start(),
            match.end(),
            match.group(0).replace(_SOFT, ""),
            "soft_hyphen",
            _CERTAIN,
        )
        if item is not None:
            found.append(item)
    return found


def _whitespace(text: str, occupied: bytearray) -> list[Suggestion]:
    found: list[Suggestion] = []
    for match in _HSPACE_RUN.finditer(text):
        item = _claim(text, occupied, match.start(), match.end(), " ", "whitespace", _CERTAIN)
        if item is not None:
            found.append(item)
    return found


def _dashes(text: str, occupied: bytearray) -> list[Suggestion]:
    found: list[Suggestion] = []
    for index, char in enumerate(text):
        canonical = _DASH.get(char)
        if canonical is None:
            continue
        item = _claim(text, occupied, index, index + 1, canonical, "dash", _DASH_CONFIDENCE)
        if item is not None:
            found.append(item)
    return found


def _nfc(text: str, occupied: bytearray) -> list[Suggestion]:
    normalised = unicodedata.normalize("NFC", text)
    if normalised == text:
        return []
    found: list[Suggestion] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=text, b=normalised, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        # A pure insertion has no original span. Anchor it to the previous
        # code point so the suggestion still quotes something the block holds.
        if i1 == i2:
            if i1 == 0:
                continue
            i1 -= 1
            j1 -= 1
        item = _claim(text, occupied, i1, i2, normalised[j1:j2], "nfc", _CERTAIN)
        if item is not None:
            found.append(item)
    return found
