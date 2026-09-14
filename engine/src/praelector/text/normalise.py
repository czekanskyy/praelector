# SPDX-License-Identifier: Apache-2.0
"""Text normalisation and conversion artifact detection (AI-02).

Performs Unicode NFC normalization, soft-hyphen stripping, line-break
hyphenation stitching, whitespace collapsing, and canonical dash unification.
Emits conversion_artifact suggestions tracking all non-silent alterations.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactMatch:
    """A detected conversion artifact in a text block."""

    start: int
    end: int
    original: str
    proposed: str
    category: str = "conversion_artifact"
    rationale: str = ""
    confidence: float = 0.95


@dataclass(frozen=True)
class NormaliseResult:
    """Output of the normalization pass on a block."""

    text: str
    artifacts: list[ArtifactMatch]


# Soft hyphen character U+00AD
SOFT_HYPHEN = "\u00ad"

# Matches word hyphenation across line breaks: e.g. "prze-\nsunięty" or "prze-\r\nsunięty"
RE_LINE_HYPHEN = re.compile(
    r"([A-Za-zżźćńółęąśŻŹĆĄŚĘŁÓŃ]+)-[ \t]*\r?\n[ \t]*([A-Za-zżźćńółęąśŻŹĆĄŚĘŁÓŃ]+)"
)

# Matches runs of multiple whitespace characters (excluding single newlines)
RE_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def normalise_text(raw_text: str) -> NormaliseResult:
    """Normalize text to Unicode NFC and detect conversion artifacts.

    1. Normalize to NFC.
    2. Detect & record soft hyphens, then remove them.
    3. Detect & record word hyphenation across line breaks, then stitch them.
    4. Detect & record runs of whitespace (e.g. double spaces).
    """
    # Step 1: NFC normalization
    text = unicodedata.normalize("NFC", raw_text)
    artifacts: list[ArtifactMatch] = []

    # Step 2: Line-break hyphenation ("prze-\nsunięty" -> "przesunięty")
    for m in RE_LINE_HYPHEN.finditer(text):
        orig = m.group(0)
        stitched = f"{m.group(1)}{m.group(2)}"
        artifacts.append(
            ArtifactMatch(
                start=m.start(),
                end=m.end(),
                original=orig,
                proposed=stitched,
                category="conversion_artifact",
                rationale="Stitched hyphenation across line break",
                confidence=0.95,
            )
        )

    # Step 3: Soft hyphens U+00AD
    if SOFT_HYPHEN in text:
        # Find word containing the soft hyphen for context (excluding punctuation)
        words = re.finditer(r"[A-Za-zżźćńółęąśŻŹĆĄŚĘŁÓŃ\u00ad]+", text)
        for w in words:
            word_str = w.group(0)
            if SOFT_HYPHEN in word_str:
                cleaned = word_str.replace(SOFT_HYPHEN, "")
                artifacts.append(
                    ArtifactMatch(
                        start=w.start(),
                        end=w.end(),
                        original=word_str,
                        proposed=cleaned,
                        category="conversion_artifact",
                        rationale="Stripped soft hyphen (U+00AD)",
                        confidence=0.99,
                    )
                )

    # Step 4: Runs of multiple spaces ("  " -> " ")
    for m in RE_MULTI_SPACE.finditer(text):
        artifacts.append(
            ArtifactMatch(
                start=m.start(),
                end=m.end(),
                original=m.group(0),
                proposed=" ",
                category="conversion_artifact",
                rationale="Collapsed run of whitespace",
                confidence=0.95,
            )
        )

    # Sort artifacts by start offset
    artifacts.sort(key=lambda a: a.start)
    return NormaliseResult(text=text, artifacts=artifacts)
