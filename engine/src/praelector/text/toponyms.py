# SPDX-License-Identifier: Apache-2.0
"""Curated toponym gazetteer detection and phonetic substitution (AI-02).

Detects geographic entities (cities, states, regions, landmarks) and provides
natural Polish pronunciations (e.g. Washington DC -> Łoszynkton di si).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToponymMatch:
    """A detected toponym match in text."""

    start: int
    end: int
    original: str
    proposed: str
    category: str = "toponym"
    rationale: str = ""
    confidence: float = 0.90


_TOPONYMS_CACHE: dict[str, str] | None = None
_TOPONYMS_PATTERN: re.Pattern[str] | None = None


def _load_toponyms() -> dict[str, str]:
    global _TOPONYMS_CACHE
    if _TOPONYMS_CACHE is None:
        data_path = Path(__file__).parent / "data" / "toponyms_pl.json"
        if data_path.exists():
            with open(data_path, encoding="utf-8") as f:
                _TOPONYMS_CACHE = json.load(f)
        else:
            _TOPONYMS_CACHE = {}
    return _TOPONYMS_CACHE


def _get_toponyms_pattern() -> re.Pattern[str]:
    global _TOPONYMS_PATTERN
    if _TOPONYMS_PATTERN is None:
        toponyms = _load_toponyms()
        # Sort by length descending so longer multi-word phrases match first
        keys = sorted(toponyms.keys(), key=len, reverse=True)
        escaped = [re.escape(k) for k in keys]
        if escaped:
            # Word boundary matching
            _TOPONYMS_PATTERN = re.compile(
                r"\b(" + "|".join(escaped) + r")\b",
                re.IGNORECASE,
            )
        else:
            _TOPONYMS_PATTERN = re.compile(r"(?!)")  # Never matches
    return _TOPONYMS_PATTERN


def detect_toponyms(text: str) -> list[ToponymMatch]:
    """Detect curated toponyms in text and return Polish spoken suggestions."""
    matches: list[ToponymMatch] = []
    toponyms = _load_toponyms()
    pattern = _get_toponyms_pattern()

    # Map normalized lowercase keys to their spoken values
    lookup = {k.lower(): v for k, v in toponyms.items()}

    for m in pattern.finditer(text):
        token = m.group(1)
        lower_token = token.lower()
        if lower_token in lookup:
            spoken = lookup[lower_token]
            # If the spoken readout is identical to original, we still emit or match
            matches.append(
                ToponymMatch(
                    start=m.start(),
                    end=m.end(),
                    original=token,
                    proposed=spoken,
                    category="toponym",
                    rationale=f"Toponym pronunciation: {token} -> {spoken}",
                    confidence=0.90,
                )
            )

    return matches
