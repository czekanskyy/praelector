# SPDX-License-Identifier: Apache-2.0
"""Unit tests for foreign word detection and phonetic rewrite (AI-08, D-12)."""

from __future__ import annotations

from praelector.text.foreign import approximate_polish_phonetics, detect_foreign_words


def test_approximate_polish_phonetics() -> None:
    assert approximate_polish_phonetics("Walker") == "Łoker"
    assert approximate_polish_phonetics("Deadline") == "Dedlajn"
    assert approximate_polish_phonetics("briefing") == "brifing"
    assert approximate_polish_phonetics("weekend") == "łikend"


def test_detect_foreign_words_in_context() -> None:
    text = "Walker wzruszył ramionami. — Deadline mamy o 18:00 — powiedziała Anna."
    matches = detect_foreign_words(text)

    by_orig = {m.original: m for m in matches}
    assert "Walker" in by_orig
    assert by_orig["Walker"].proposed == "Łoker"

    assert "Deadline" in by_orig
    assert by_orig["Deadline"].proposed == "Dedlajn"

    # Polish words with diacritics must never be detected
    assert "wzruszył" not in by_orig
    assert "powiedziała" not in by_orig


def test_user_lexicon_suppresses_detection() -> None:
    text = "Nasz nowy manager ma deadline jutro."
    matches_before = detect_foreign_words(text)
    assert any(m.original.lower() == "manager" for m in matches_before)

    # With user lexicon containing "manager"
    matches_after = detect_foreign_words(text, user_lexicon_words={"manager"})
    assert not any(m.original.lower() == "manager" for m in matches_after)
