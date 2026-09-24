# SPDX-License-Identifier: Apache-2.0
"""Acronyms, the hand-written toponym list, and English-looking tokens (D-12)."""

from __future__ import annotations

from praelector.domain.enums import SuggestionCategory
from praelector.text.acronyms import lexical_suggestions, spell_acronym
from praelector.text.suggestion import Suggestion


def _kinds(text: str) -> list[Suggestion]:
    found = lexical_suggestions(text)
    for item in found:
        assert item.original == text[item.start : item.end]
        assert item.detector == "heuristic"
    return found


def test_acronyms_are_spelled_and_known_words_are_not() -> None:
    assert spell_acronym("IT") == "aj ti"
    assert spell_acronym("PDF") == "pi di ef"
    item = _kinds("W IT nikt nie odbierał.")[0]
    assert item.kind == SuggestionCategory.ACRONYM
    assert item.original == "IT"
    assert item.replacement == "aj ti"
    assert item.reason == "acronym"
    assert _kinds("TAK") == []
    assert _kinds("OK") == []
    assert _kinds("IV") == []


def test_toponyms_are_hand_written_phrases() -> None:
    warsaw = _kinds("Warszawa")[0]
    assert warsaw.kind == SuggestionCategory.TOPONYM
    assert warsaw.replacement == "Warszawa"

    york = _kinds("w Nowy  Jork pada")[0]
    assert york.original == "Nowy  Jork"
    assert york.replacement == "Nowy Jork"

    angeles = _kinds("Los Angeles")[0]
    assert angeles.replacement == "Los Andżeles"

    capital = _kinds("Washington")[0]
    assert capital.replacement == "Łoszynkton"

    district = _kinds("do Washington DC jutro")[0]
    assert district.original == "Washington DC"
    assert district.replacement == "Łoszynkton di si"
    assert _kinds("w Nowy Jorku") == []


def test_english_tokens_are_foreign_words_and_toponyms_win() -> None:
    walker = _kinds("Walker wzruszył ramionami.")[0]
    assert walker.kind == SuggestionCategory.FOREIGN_WORD
    assert walker.original == "Walker"
    assert walker.replacement == "Łoker"
    assert walker.reason == "english_word"

    deadline = _kinds("Deadline mamy dziś.")[0]
    assert deadline.replacement == "dedlajn"

    inflected = _kinds("po meetingu")[0]
    assert inflected.original == "meetingu"
    assert inflected.replacement == "mitingu"
    assert inflected.reason == "english_orthography"

    clock = _kinds("ten clock stoi")[0]
    assert clock.replacement == "clok"
    assert clock.reason == "english_word"

    thing = _kinds("to thing jest")[0]
    assert thing.kind == SuggestionCategory.FOREIGN_WORD
    assert thing.replacement == "ting"
    assert thing.reason == "english_orthography"

    walking = _kinds("idzie walking")[0]
    assert walking.replacement == "walking"
    assert walking.confidence == 0.62

    assert _kinds("Zażółć gęślą jaźń") == []
    assert _kinds("kot") == []

    mixed = _kinds("Washington DC i IT")
    assert [(item.kind, item.original, item.replacement) for item in mixed] == [
        (SuggestionCategory.TOPONYM, "Washington DC", "Łoszynkton di si"),
        (SuggestionCategory.ACRONYM, "IT", "aj ti"),
    ]
