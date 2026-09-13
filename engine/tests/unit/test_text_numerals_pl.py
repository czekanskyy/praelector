# SPDX-License-Identifier: Apache-2.0
"""Unit tests for Polish numeral pronunciation and detection (D-11, AI-02)."""

from __future__ import annotations

from praelector.text.numerals_pl import (
    cardinal_nominative,
    decimal_to_words,
    detect_numerals,
    ordinal_nominative,
    roman_to_int,
    roman_to_words,
    time_to_words,
    year_to_words,
)


def test_cardinal_nominative_basic() -> None:
    assert cardinal_nominative(0) == "zero"
    assert cardinal_nominative(1) == "jeden"
    assert cardinal_nominative(2) == "dwa"
    assert cardinal_nominative(5) == "pięć"
    assert cardinal_nominative(12) == "dwanaście"
    assert cardinal_nominative(20) == "dwadzieścia"
    assert cardinal_nominative(45) == "czterdzieści pięć"
    assert cardinal_nominative(100) == "sto"
    assert cardinal_nominative(238) == "dwieście trzydzieści osiem"
    assert cardinal_nominative(1000) == "tysiąc"
    assert cardinal_nominative(1001) == "tysiąc jeden"
    assert cardinal_nominative(2000) == "dwa tysiące"
    assert cardinal_nominative(5000) == "pięć tysięcy"
    assert cardinal_nominative(1_000_000) == "milion"
    assert cardinal_nominative(2_500_000) == "dwa miliony pięćset tysięcy"


def test_ordinal_nominative_genders() -> None:
    # Masculine (m)
    assert ordinal_nominative(1, "m") == "pierwszy"
    assert ordinal_nominative(8, "m") == "ósmy"
    assert ordinal_nominative(14, "m") == "czternasty"
    assert ordinal_nominative(20, "m") == "dwudziesty"
    assert ordinal_nominative(21, "m") == "dwudziesty pierwszy"

    # Feminine (f)
    assert ordinal_nominative(1, "f") == "pierwsza"
    assert ordinal_nominative(2, "f") == "druga"
    assert ordinal_nominative(8, "f") == "ósma"
    assert ordinal_nominative(14, "f") == "czternasta"

    # Neuter (n)
    assert ordinal_nominative(1, "n") == "pierwsze"
    assert ordinal_nominative(8, "n") == "ósme"
    assert ordinal_nominative(14, "n") == "czternaste"


def test_year_to_words() -> None:
    assert year_to_words(1939) == "tysiąc dziewięćset trzydziesty dziewiąty"
    assert year_to_words(1900) == "tysiąc dziewięćsetny"
    assert year_to_words(2000) == "dwutysięczny"
    assert year_to_words(2024) == "dwa tysiące dwudziesty czwarty"


def test_time_to_words() -> None:
    # With preposition "o 18:00" -> "osiemnastej"
    assert time_to_words(18, 0, has_preposition=True) == "osiemnastej"
    assert time_to_words(18, 30, has_preposition=True) == "osiemnastej trzydzieści"
    # Without preposition "18:00" -> "osiemnasta"
    assert time_to_words(18, 0, has_preposition=False) == "osiemnasta"
    assert time_to_words(18, 30, has_preposition=False) == "osiemnasta trzydzieści"


def test_decimal_to_words() -> None:
    assert decimal_to_words("3,5") == "trzy i pięć dziesiątych"
    assert decimal_to_words("3.5") == "trzy i pięć dziesiątych"
    assert decimal_to_words("2,25") == "dwa i dwadzieścia pięć setnych"
    assert decimal_to_words("1,1") == "jeden i jedna dziesiąta"


def test_roman_numerals() -> None:
    assert roman_to_int("I") == 1
    assert roman_to_int("IV") == 4
    assert roman_to_int("VIII") == 8
    assert roman_to_int("XIV") == 14
    assert roman_to_int("XXI") == 21

    # Following noun gender context
    assert roman_to_words("XIV", following_word="piętro") == "czternaste"
    assert roman_to_words("XIV", following_word="wiek") == "czternasty"
    assert roman_to_words("II", following_word="część") == "druga"


def test_detect_numerals_pipeline() -> None:
    sample = "Rozdział 8\nSpotkanie o 18:00 na XIV piętrze. Koszt to 3,5 miliona. Było 238 osób."
    matches = detect_numerals(sample)

    by_orig = {m.original: m for m in matches}

    assert "Rozdział 8" in by_orig
    assert by_orig["Rozdział 8"].category == "ordinal_heading"
    assert by_orig["Rozdział 8"].proposed == "Rozdział ósmy"

    assert "18:00" in by_orig
    assert by_orig["18:00"].category == "numeral"
    assert by_orig["18:00"].proposed == "osiemnastej"

    assert "XIV" in by_orig
    assert by_orig["XIV"].category == "numeral"
    assert by_orig["XIV"].proposed == "czternaste"

    assert "3,5" in by_orig
    assert by_orig["3,5"].proposed == "trzy i pięć dziesiątych"

    assert "238" in by_orig
    assert by_orig["238"].proposed == "dwieście trzydzieści osiem"
