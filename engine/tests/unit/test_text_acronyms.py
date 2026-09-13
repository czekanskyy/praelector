# SPDX-License-Identifier: Apache-2.0
"""Unit tests for acronym detection and pronunciation (AI-02, AI-08)."""

from __future__ import annotations

from praelector.text.acronyms import detect_acronyms, spell_acronym_pl


def test_spell_acronym_known() -> None:
    assert spell_acronym_pl("IT") == "aj ti"
    assert spell_acronym_pl("USA") == "u es a"
    assert spell_acronym_pl("SMS") == "es em es"
    assert spell_acronym_pl("VIP") == "wi aj pi"
    assert spell_acronym_pl("TV") == "ti wi"
    assert spell_acronym_pl("ZUS") == "zus"
    assert spell_acronym_pl("NBP") == "en be pe"


def test_spell_acronym_fallback() -> None:
    # Unknown acronym is spelled letter-by-letter
    assert spell_acronym_pl("XYZ") == "iks igrek zet"


def test_detect_acronyms_excludes_roman_and_common_words() -> None:
    text = "W IT nikt nie odbierał telefonu. Rozdział XIV nie był dla nas problemem, TAK czy NIE."
    matches = detect_acronyms(text)

    originals = [m.original for m in matches]
    assert "IT" in originals
    # XIV is a Roman numeral, should not be an acronym
    assert "XIV" not in originals
    # TAK, NIE are common words, should not be acronyms
    assert "TAK" not in originals
    assert "NIE" not in originals

    it_match = [m for m in matches if m.original == "IT"][0]
    assert it_match.proposed == "aj ti"
    assert it_match.category == "acronym"
