# SPDX-License-Identifier: Apache-2.0
"""Front-matter and back-matter skip heuristics (EB-08)."""

from __future__ import annotations

import re

from praelector.ebook.blocks import ExtractedBlock

# Keywords strongly signaling copyright or publisher colophon
COPYRIGHT_KEYWORDS = [
    r"copyright\s*(?:©|\(c\)|by)?",
    r"wszelkie\s+prawa\s+zastrzeżone",
    r"all\s+rights\s+reserved",
    r"isbn[\s:-]*[0-9x-]+",
    r"wydanie\s+[ivx0-9]+",
    r"druk\s+i\s+oprawa",
    r"skład\s+i\s+łamanie",
    r"projekt\s+okładki",
    r"redakcja\s+językowa",
    r"korekta:",
    r"tytuł\s+oryginału",
    r"przekład\s+z\s+języka",
    r"tłumaczenie:",
    r"wydawnictwo\s+[\w\s]+",
]

COPYRIGHT_REGEX = re.compile("|".join(COPYRIGHT_KEYWORDS), re.IGNORECASE)

TOC_KEYWORDS = [
    r"^spis\s+treści",
    r"^table\s+of\s+contents",
    r"spis\s+rozdziałów",
]
TOC_REGEX = re.compile("|".join(TOC_KEYWORDS), re.IGNORECASE)

PROMO_KEYWORDS = [
    r"polecamy\s+(?:także|inne|również)",
    r"w\s+serii\s+ukazały\s+się",
    r"książki\s+tego\s+samego\s+autora",
    r"zapraszamy\s+na\s+stronę\s+wydawnictwa",
]
PROMO_REGEX = re.compile("|".join(PROMO_KEYWORDS), re.IGNORECASE)


class SkipCandidate:
    """A detected text range proposed for skipping by default."""

    def __init__(self, block_id: str, start: int, end: int, rationale: str) -> None:
        self.block_id = block_id
        self.start = start
        self.end = end
        self.rationale = rationale


def detect_skip_candidates(
    blocks: list[ExtractedBlock],
    chapter_title: str = "",
    is_first_chapter: bool = False,
    is_last_chapter: bool = False,
) -> list[SkipCandidate]:
    """Inspect blocks in a chapter to propose skip candidates for front-matter or adverts.

    Args:
        blocks: List of blocks in the chapter.
        chapter_title: Title of the current chapter.
        is_first_chapter: Whether this is the first chapter in the book spine.
        is_last_chapter: Whether this is the last chapter in the book spine.

    Returns:
        List of SkipCandidate items.
    """
    candidates: list[SkipCandidate] = []
    title_lower = chapter_title.lower()

    is_toc_chapter = bool(TOC_REGEX.search(title_lower))
    is_copyright_chapter = "redakcyjn" in title_lower or "copyright" in title_lower

    for blk in blocks:
        text = blk.text
        if not text:
            continue

        # 1. Whole chapter is TOC or copyright
        if is_toc_chapter:
            candidates.append(
                SkipCandidate(
                    block_id=blk.id,
                    start=0,
                    end=len(text),
                    rationale="Spis treści (strona nawigacyjna / spis rozdziałów)",
                )
            )
            continue

        if is_copyright_chapter:
            candidates.append(
                SkipCandidate(
                    block_id=blk.id,
                    start=0,
                    end=len(text),
                    rationale="Metadane wydawnicze i nota copyrightowa",
                )
            )
            continue

        # 2. Block-level copyright detection (especially in first 3 chapters)
        if (is_first_chapter or len(blocks) <= 10) and COPYRIGHT_REGEX.search(text):
            candidates.append(
                SkipCandidate(
                    block_id=blk.id,
                    start=0,
                    end=len(text),
                    rationale="Stopka redakcyjna / nota copyrightowa / ISBN",
                )
            )
            continue

        # 3. Block-level promotional catalog detection (especially in last chapter)
        if (is_last_chapter or len(blocks) <= 15) and PROMO_REGEX.search(text):
            candidates.append(
                SkipCandidate(
                    block_id=blk.id,
                    start=0,
                    end=len(text),
                    rationale="Materiały promocyjne wydawnictwa",
                )
            )
            continue

    return candidates
