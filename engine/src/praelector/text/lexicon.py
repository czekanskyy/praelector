# SPDX-License-Identifier: Apache-2.0
"""User-editable pronunciation lexicon matching engine (AI-09).

Manages rule execution (exact match and regex) for global and project lexicons,
emitting dict_hit suggestions with auto_apply pre-acceptance support.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from praelector.domain.models import LexiconEntryResponse


@dataclass(frozen=True)
class LexiconMatch:
    """A match produced by the lexicon engine."""

    start: int
    end: int
    original: str
    proposed: str
    category: str = "dict_hit"
    rationale: str = ""
    confidence: float = 1.0
    auto_apply: bool = False


class LexiconMatcher:
    """Matches text against combined global and project lexicon entries.

    Project entries override global entries with identical (pattern, is_regex).
    Rules are evaluated in order of priority (lower numerical value wins).
    """

    def __init__(
        self,
        global_entries: list[LexiconEntryResponse] | None = None,
        project_entries: list[LexiconEntryResponse] | None = None,
    ) -> None:
        entries_dict: dict[tuple[str, bool], LexiconEntryResponse] = {}

        # 1. Load global entries
        for g in global_entries or []:
            entries_dict[(g.pattern, g.is_regex)] = g

        # 2. Project entries override global entries by (pattern, is_regex)
        for p in project_entries or []:
            entries_dict[(p.pattern, p.is_regex)] = p

        # 3. Sort effective entries by priority ascending
        self._entries = sorted(entries_dict.values(), key=lambda e: e.priority)
        self._compiled: list[tuple[re.Pattern[str], LexiconEntryResponse]] = []

        for entry in self._entries:
            flags = 0 if entry.case_sensitive else re.IGNORECASE
            try:
                if entry.is_regex:
                    pat = re.compile(entry.pattern, flags)
                else:
                    escaped = re.escape(entry.pattern)
                    # If pattern looks like a word, enforce word boundaries
                    if re.match(r"^\w+$", entry.pattern, re.UNICODE):
                        pat = re.compile(rf"\b{escaped}\b", flags)
                    else:
                        pat = re.compile(escaped, flags)
                self._compiled.append((pat, entry))
            except re.error:
                continue

    @property
    def entries(self) -> list[LexiconEntryResponse]:
        return self._entries

    def match(self, text: str) -> list[LexiconMatch]:
        """Find all non-overlapping lexicon matches in text."""
        candidates: list[tuple[int, int, int, LexiconMatch]] = []

        for pat, entry in self._compiled:
            for m in pat.finditer(text):
                orig = m.group(0)
                # Handle regex group replacement if applicable
                proposed = entry.spoken
                if entry.is_regex:
                    try:
                        proposed = m.expand(entry.spoken)
                    except re.error:
                        proposed = entry.spoken

                match_obj = LexiconMatch(
                    start=m.start(),
                    end=m.end(),
                    original=orig,
                    proposed=proposed,
                    category=entry.category or "dict_hit",
                    rationale=f"Lexicon match for pattern '{entry.pattern}'",
                    confidence=1.0,
                    auto_apply=entry.auto_apply,
                )
                candidates.append((entry.priority, m.start(), m.end(), match_obj))

        # Sort candidates: lower priority first, then earlier start, then longer match
        candidates.sort(key=lambda c: (c[0], c[1], -(c[2] - c[1])))

        # Resolve overlaps
        accepted: list[LexiconMatch] = []
        occupied: list[tuple[int, int]] = []

        for _, start, end, match_obj in candidates:
            if not any(max(start, os) < min(end, oe) for os, oe in occupied):
                accepted.append(match_obj)
                occupied.append((start, end))

        accepted.sort(key=lambda m: m.start)
        return accepted
