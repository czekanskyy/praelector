# SPDX-License-Identifier: Apache-2.0
"""Polish readings (D-11): cardinals, ordinal genders, years, decimals, clocks, Roman."""

from __future__ import annotations

import pytest

from praelector.domain.enums import SuggestionCategory
from praelector.text.numerals_pl import (
    cardinal,
    cardinal_feminine,
    clock_phrase,
    decimal_phrase,
    numeral_suggestions,
    ordinal,
    parse_roman,
)
from praelector.text.suggestion import Suggestion


def _one(text: str, *, heading: bool = False) -> Suggestion:
    found = numeral_suggestions(text, heading=heading)
    assert len(found) == 1
    item = found[0]
    assert item.original == text[item.start : item.end]
    assert item.detector == "heuristic"
    return item


def test_cardinals_use_the_non_virile_nominative() -> None:
    assert cardinal(0) == "zero"
    assert cardinal(5) == "pięć"
    assert cardinal(12) == "dwanaście"
    assert cardinal(21) == "dwadzieścia jeden"
    assert cardinal(100) == "sto"
    assert cardinal(238) == "dwieście trzydzieści osiem"
    assert cardinal(1000) == "tysiąc"
    assert cardinal(2000) == "dwa tysiące"
    assert cardinal(5000) == "pięć tysięcy"
    assert cardinal(22000) == "dwadzieścia dwa tysiące"
    assert cardinal(1_000_000) == "milion"
    assert cardinal(2_000_000) == "dwa miliony"
    assert cardinal(5_000_000) == "pięć milionów"
    assert cardinal(1_000_000_000) == "miliard"
    with pytest.raises(ValueError, match="out of range"):
        cardinal(-1)


def test_ordinals_agree_in_masculine_feminine_and_neuter() -> None:
    assert ordinal(8, "m") == "ósmy"
    assert ordinal(8, "f") == "ósma"
    assert ordinal(8, "n") == "ósme"
    assert ordinal(2, "f") == "druga"
    assert ordinal(3, "n") == "trzecie"
    assert ordinal(14, "n") == "czternaste"
    assert ordinal(21, "m") == "dwudziesty pierwszy"
    assert ordinal(21, "f") == "dwudziesta pierwsza"
    assert ordinal(101, "f") == "sto pierwsza"
    assert ordinal(1939, "m") == "tysiąc dziewięćset trzydziesty dziewiąty"
    assert ordinal(1989, "m") == "tysiąc dziewięćset osiemdziesiąty dziewiąty"
    assert ordinal(2000, "m") == "dwutysięczny"
    assert ordinal(2010, "m") == "dwa tysiące dziesiąty"
    assert ordinal(21000, "f") == "dwudziestojednotysięczna"
    with pytest.raises(ValueError, match="out of range"):
        ordinal(1_000_000)


def test_feminine_cardinal_and_decimal_agreement() -> None:
    assert cardinal_feminine(1) == "jedna"
    assert cardinal_feminine(2) == "dwie"
    assert cardinal_feminine(5) == "pięć"
    assert cardinal_feminine(12) == "dwanaście"
    assert cardinal_feminine(21) == "dwadzieścia jedna"
    assert cardinal_feminine(22) == "dwadzieścia dwie"
    assert decimal_phrase(3, "5") == "trzy i pięć dziesiątych"
    assert decimal_phrase(1, "1") == "jeden i jedna dziesiąta"
    assert decimal_phrase(2, "2") == "dwa i dwie dziesiąte"
    assert decimal_phrase(3, "14") == "trzy i czternaście setnych"
    assert decimal_phrase(3, "22") == "trzy i dwadzieścia dwie setne"
    assert decimal_phrase(3, "05") == "trzy i pięć setnych"
    assert decimal_phrase(1, "2345") == "jeden przecinek dwa trzy cztery pięć"
    with pytest.raises(ValueError, match="decimal"):
        decimal_phrase(-1, "5")


def test_clock_hours_are_feminine_locative() -> None:
    assert clock_phrase(18, 0) == "osiemnastej"
    assert clock_phrase(14, 30) == "czternastej trzydzieści"
    assert clock_phrase(2, 0) == "drugiej"
    assert clock_phrase(3, 0) == "trzeciej"
    assert clock_phrase(22, 15) == "dwudziestej drugiej piętnaście"
    assert clock_phrase(0, 0) == "zerowej"
    with pytest.raises(ValueError, match="clock"):
        clock_phrase(24, 0)


def test_required_numeral_surfaces() -> None:
    five = _one("Zostało 5.")
    assert five.original == "5"
    assert five.replacement == "pięć"
    assert five.kind == SuggestionCategory.NUMERAL
    assert five.reason == "cardinal"

    dotted = _one("12.")
    assert dotted.original == "12."
    assert dotted.replacement == "dwunasty"
    assert dotted.reason == "ordinal"

    decimal = _one("waga 3,5 kg")
    assert decimal.original == "3,5"
    assert decimal.replacement == "trzy i pięć dziesiątych"
    assert decimal.reason == "decimal"

    clock = _one("o 14:30.")
    assert clock.original == "14:30"
    assert clock.replacement == "czternastej trzydzieści"
    assert clock.reason == "clock"

    hour = _one("o 18:00")
    assert hour.replacement == "osiemnastej"

    year = _one("w 1989 roku")
    assert year.original == "1989"
    assert year.replacement == "tysiąc dziewięćset osiemdziesiąty dziewiąty"
    assert year.reason == "year"

    roman = _one("IV", heading=True)
    assert roman.kind == SuggestionCategory.ORDINAL_HEADING
    assert roman.original == "IV"
    assert roman.replacement == "czwarty"
    assert roman.reason == "heading_ordinal"


def test_ordinal_gender_follows_the_noun_and_headings_keep_their_word() -> None:
    masculine = _one("to 12. rozdział")
    assert masculine.original == "12."
    assert masculine.replacement == "dwunasty"

    feminine = _one("to 12. część")
    assert feminine.replacement == "dwunasta"

    neuter = _one("na XIV piętro")
    assert neuter.original == "XIV"
    assert neuter.replacement == "czternaste"
    assert neuter.kind == SuggestionCategory.NUMERAL
    assert neuter.reason == "roman"

    locative = _one("na XIV piętrze")
    assert locative.replacement == "czternaste"

    heading = _one("Rozdział 8")
    assert heading.kind == SuggestionCategory.ORDINAL_HEADING
    assert heading.original == "Rozdział 8"
    assert heading.replacement == "Rozdział ósmy"

    part = _one("Część IV")
    assert part.replacement == "Część czwarta"
    assert part.kind == SuggestionCategory.ORDINAL_HEADING

    bare_heading_digit = _one("8", heading=True)
    assert bare_heading_digit.kind == SuggestionCategory.ORDINAL_HEADING
    assert bare_heading_digit.replacement == "ósmy"

    assert _one("IV").kind == SuggestionCategory.ORDINAL_HEADING
    assert _one("IV").replacement == "czwarty"


def test_years_quantities_grouping_and_rejected_shapes() -> None:
    quantity = _one("minęło 1989 lat")
    assert quantity.reason == "cardinal"
    assert quantity.replacement == "tysiąc dziewięćset osiemdziesiąt dziewięć"

    money = _one("cena 2000 zł")
    assert money.replacement == "dwa tysiące"

    grouped = _one("zebrano 1 234 szt")
    assert grouped.original == "1 234"
    assert grouped.replacement == "tysiąc dwieście trzydzieści cztery"

    narrow = _one("zebrano 1\u00a0234 szt")
    assert narrow.replacement == "tysiąc dwieście trzydzieści cztery"

    assert numeral_suggestions("24:00")[0].reason == "cardinal"
    assert parse_roman("IV") == 4
    assert parse_roman("XIV") == 14
    assert parse_roman("MCMXC") == 1990
    assert parse_roman("IIII") is None
    assert parse_roman("IT") is None
    assert numeral_suggestions("IT") == []
    assert numeral_suggestions("Washington DC") == []
    # A dot decimal is not Polish; the digits stay cardinals.
    assert [item.replacement for item in numeral_suggestions("3.5")] == ["trzy", "pięć"]


def test_a_sentence_final_period_is_not_an_ordinal_dot() -> None:
    item = _one("Było ich 5. Potem wyszli.")
    assert item.original == "5"
    assert item.replacement == "pięć"
