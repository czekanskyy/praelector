# SPDX-License-Identifier: Apache-2.0
"""Unit tests for front-matter and skip candidate detection (EB-08)."""

from __future__ import annotations

from praelector.text.skip_detector import detect_skip_candidates


def test_bare_page_number() -> None:
    text = "12"
    matches = detect_skip_candidates(text)
    assert len(matches) == 1
    assert matches[0].rationale == "Bare page number"
    assert matches[0].start == 0
    assert matches[0].end == 2


def test_isbn_line() -> None:
    text = "ISBN 978-83-000000-0-0"
    matches = detect_skip_candidates(text)
    assert len(matches) == 1
    assert matches[0].rationale == "ISBN line"
    assert matches[0].start == 0
    assert matches[0].end == len(text)


def test_copyright_block() -> None:
    text = "Copyright © 2026 Praelector. Wszelkie prawa zastrzeżone."
    matches = detect_skip_candidates(text)
    assert len(matches) == 1
    assert "Copyright" in matches[0].rationale


def test_publishing_imprint() -> None:
    text = "Redakcja i korekta: Jan Kowalski. Projekt okładki: Anna Nowak."
    matches = detect_skip_candidates(text)
    assert len(matches) == 1
    assert "imprint" in matches[0].rationale.lower()
