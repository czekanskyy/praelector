# SPDX-License-Identifier: Apache-2.0
"""Conversion artifacts stay suggestions; the block text is not rewritten."""

from __future__ import annotations

from praelector.domain.enums import Detector, SuggestionCategory
from praelector.text.normalize import normalization_suggestions
from praelector.text.suggestion import Suggestion


def _only(text: str, reason: str) -> Suggestion:
    found = [item for item in normalization_suggestions(text) if item.reason == reason]
    assert len(found) == 1
    item = found[0]
    assert item.original == text[item.start : item.end]
    assert item.kind == SuggestionCategory.CONVERSION_ARTIFACT
    assert item.detector == Detector.HEURISTIC
    return item


def test_horizontal_whitespace_collapses_and_newlines_do_not() -> None:
    text = "na zegar.  Było"
    item = _only(text, "whitespace")
    assert item.original == "  "
    assert item.replacement == " "
    assert normalization_suggestions("a\nb") == []
    assert normalization_suggestions("a\n\nb") == []
    spaces = _only("a\u00a0\u00a0b", "whitespace")
    assert spaces.original == "\u00a0\u00a0"
    assert spaces.replacement == " "


def test_soft_hyphen_is_recorded_and_not_applied_to_the_source() -> None:
    text = "egzem\u00adplarzy"
    item = _only(text, "soft_hyphen")
    assert item.original == text
    assert item.replacement == "egzemplarzy"
    assert text == "egzem\u00adplarzy"
    lone = _only("a\u00adb", "soft_hyphen")
    assert lone.replacement == "ab"


def test_hyphenated_line_break_joins_the_word() -> None:
    text = "prze-\nsunięty"
    item = _only(text, "hyphenation")
    assert item.original == text
    assert item.replacement == "przesunięty"
    crlf = _only("prze-\r\nsunięty", "hyphenation")
    assert crlf.replacement == "przesunięty"
    soft_break = _only("sło\u00ad\nwo", "hyphenation")
    assert soft_break.replacement == "słowo"
    both = _only("za\u00ad-\nczyna", "hyphenation")
    assert both.replacement == "zaczyna"
    assert normalization_suggestions("prze—\nsłowo") == []


def test_dashes_map_to_the_canonical_form_and_remember_the_original() -> None:
    en = _only("lata 1989\u20132000", "dash")
    assert en.original == "\u2013"
    assert en.replacement == "\u2014"
    minus = _only("5\u22123", "dash")
    assert minus.original == "\u2212"
    assert minus.replacement == "-"
    assert normalization_suggestions("pauza — tutaj") == []


def test_nfc_is_a_suggestion_over_the_decomposed_span() -> None:
    text = "cafe\u0301"
    item = _only(text, "nfc")
    assert item.original == "e\u0301"
    assert item.replacement == "é"
    assert normalization_suggestions("café") == []


def test_clean_text_has_no_artifact() -> None:
    assert normalization_suggestions("Anna odłożyła raport.") == []
