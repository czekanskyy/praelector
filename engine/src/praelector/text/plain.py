# SPDX-License-Identifier: Apache-2.0
"""Chapter plain text: blank-line blocks and identity re-association (D-08, ED-02).

The editor's document is the current blocks joined with a blank line. A commit
splits on blank lines and keeps a block id when the normalised texts are still
similar, so a typo does not mint a new id.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

#: DATA_MODEL.md §4. Below this ratio the candidate is a new block.
SIMILARITY_THRESHOLD = 0.6

_BLANK_LINE = re.compile(r"\n[ \t]*\n")
_SOFT_HYPHEN = "\u00ad"


def join_plain_text(parts: Sequence[str]) -> str:
    """Blocks joined the way ``GET /chapters/{id}/text`` returns them."""
    return "\n\n".join(parts)


def split_plain_text(text: str) -> list[str]:
    """Split editor text into blocks. Blank lines are the only separators.

    CR LF is normalised first. Empty pieces, including a trailing blank line,
    are dropped. A single newline inside a block is kept.
    """
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in _BLANK_LINE.split(normalised) if part.strip()]


def normalise_match_text(text: str) -> str:
    """NFC, no soft hyphens, collapsed whitespace. Case is preserved."""
    folded = unicodedata.normalize("NFC", text).replace(_SOFT_HYPHEN, "")
    return " ".join(folded.split())


def associate_block_ids(
    existing: Sequence[tuple[str, str]],
    candidates: Sequence[str],
) -> list[str | None]:
    """Pair each candidate with an existing id, or None when none is close enough.

    ``existing`` is ``(id, text)`` in chapter order. A pair is eligible at
    :data:`SIMILARITY_THRESHOLD` or above. Each id is used at most once. Equal
    ratios prefer the closer ordinal, then the earlier block.
    """
    if not candidates:
        return []
    scored: list[tuple[float, int, int, int, int]] = []
    for new_index, candidate in enumerate(candidates):
        wanted = normalise_match_text(candidate)
        for old_index, (_block_id, old_text) in enumerate(existing):
            ratio = SequenceMatcher(
                a=normalise_match_text(old_text),
                b=wanted,
                autojunk=False,
            ).ratio()
            if ratio < SIMILARITY_THRESHOLD:
                continue
            scored.append((ratio, -abs(new_index - old_index), -old_index, new_index, old_index))
    scored.sort(reverse=True)
    assigned: list[str | None] = [None] * len(candidates)
    used_new: set[int] = set()
    used_old: set[int] = set()
    for _ratio, _distance, _old_bias, new_index, old_index in scored:
        if new_index in used_new or old_index in used_old:
            continue
        assigned[new_index] = existing[old_index][0]
        used_new.add(new_index)
        used_old.add(old_index)
    return assigned


def replacement_count(text: str, query: str) -> int:
    """Non-overlapping, case-sensitive matches. An empty query matches nothing."""
    if not query:
        return 0
    return text.count(query)
