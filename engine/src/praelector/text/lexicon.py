# SPDX-License-Identifier: Apache-2.0
"""User lexicon applied as ``dict_hit`` suggestions (AI-09).

Project rules replace global ones that share ``(pattern, is_regex)``. A lower
``priority`` wins when two rules want the same span. ``auto`` marks the
suggestion pre-accepted. The block text is not rewritten.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from praelector.domain.enums import Detector, SuggestionCategory
from praelector.text.suggestion import Suggestion, make_suggestion


@dataclass(frozen=True, slots=True)
class LexiconRule:
    """One pronunciation rule. ``scope`` is ``global`` or ``project``."""

    pattern: str
    spoken: str
    is_regex: bool = False
    auto: bool = False
    case_sensitive: bool = False
    priority: int = 100
    scope: str = "global"


def effective_rules(rules: Sequence[LexiconRule]) -> list[LexiconRule]:
    """Project entries hide the global rule with the same pattern and regex flag."""
    chosen: dict[tuple[str, bool], LexiconRule] = {}
    for rule in rules:
        key = (rule.pattern, rule.is_regex)
        current = chosen.get(key)
        if current is None or (current.scope != "project" and rule.scope == "project"):
            chosen[key] = rule
    return sorted(chosen.values(), key=lambda rule: (rule.priority, -len(rule.pattern)))


def lexicon_suggestions(text: str, rules: Sequence[LexiconRule]) -> list[Suggestion]:
    """Non-overlapping ``dict_hit`` suggestions. ``text`` is unchanged."""
    occupied = bytearray(len(text))
    found: list[Suggestion] = []
    for rule in effective_rules(rules):
        pattern = _compile(rule)
        if pattern is None:
            continue
        for match in pattern.finditer(text):
            start, end = match.span()
            if end <= start or any(occupied[start:end]):
                continue
            occupied[start:end] = b"\x01" * (end - start)
            found.append(
                make_suggestion(
                    text=text,
                    start=start,
                    end=end,
                    replacement=rule.spoken,
                    kind=SuggestionCategory.DICT_HIT,
                    reason="lexicon",
                    confidence=0.99,
                    detector=Detector.DICT,
                    auto=rule.auto,
                )
            )
    found.sort(key=lambda item: (item.start, item.end))
    return found


def _compile(rule: LexiconRule) -> re.Pattern[str] | None:
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    try:
        if rule.is_regex:
            return re.compile(rule.pattern, flags)
        return re.compile(rf"(?<!\w){re.escape(rule.pattern)}(?!\w)", flags)
    except re.error:
        return None
