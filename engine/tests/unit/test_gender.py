# SPDX-License-Identifier: Apache-2.0
"""Speaker gender from the speech tag, the name list, and the chapter map."""

from __future__ import annotations

from praelector.domain.enums import Gender, SuggestionCategory
from praelector.text.gender import gender_suggestions, given_names


def _one(text: str):
    found = gender_suggestions([text])
    assert found
    assert all(item.kind == SuggestionCategory.SPEAKER_GENDER for item in found)
    assert text == text
    return found


def test_the_male_names_that_end_in_a_are_listed() -> None:
    names = given_names()
    for name in ("Barnaba", "Kuba", "Bonawentura", "Kosma", "Jarema"):
        assert names[name.casefold()] == Gender.MALE


def test_a_feminine_verb_suffix_is_female() -> None:
    text = "— Nie zdążymy — powiedziała cicho."
    item = _one(text)[0]
    assert item.replacement == Gender.FEMALE
    assert item.confidence >= 0.95
    assert item.reason == "verb_suffix"
    assert item.original == "Nie zdążymy"


def test_a_masculine_verb_keeps_the_speaker_label() -> None:
    text = "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz."
    item = _one(text)[0]
    assert item.replacement == Gender.MALE
    assert item.confidence >= 0.95
    assert item.speaker_id == "Walker"
    assert item.original == "A jednak spróbujemy"


def test_an_a_ending_name_does_not_flip_a_masculine_verb() -> None:
    text = "Barnaba zapytał: — Ile mamy egzemplarzy?"
    item = _one(text)[0]
    assert item.replacement == Gender.MALE
    assert item.speaker_id == "Barnaba"
    assert item.confidence >= 0.95
    assert item.reason == "verb_suffix"


def test_the_name_after_the_verb_is_the_speaker() -> None:
    text = "— 238 — odpowiedziała Anna."
    item = _one(text)[0]
    assert item.replacement == Gender.FEMALE
    assert item.speaker_id == "Anna"


def test_a_listed_name_without_a_verb_is_enough() -> None:
    text = "— Cześć — Kuba."
    item = _one(text)[0]
    assert item.replacement == Gender.MALE
    assert item.reason == "given_name"
    assert item.confidence == 0.85
    assert item.speaker_id == "Kuba"


def test_a_pronoun_in_the_previous_block_fills_a_gap() -> None:
    found = gender_suggestions(["Ona milczała przy oknie.", "— Nie wiem."])
    assert len(found) == 1
    assert found[0].block_index == 1
    assert found[0].replacement == Gender.FEMALE
    assert found[0].reason == "pronoun"
    assert found[0].confidence == 0.65


def test_a_resolved_speaker_is_reused_later_in_the_chapter() -> None:
    blocks = [
        "— Tu jestem — mruknął Walker.",
        "Minęła chwila.",
        "— Już idę — Walker.",
    ]
    found = gender_suggestions(blocks)
    assert found[0].speaker_id == "Walker"
    assert found[0].replacement == Gender.MALE
    later = found[-1]
    assert later.block_index == 2
    assert later.speaker_id == "Walker"
    assert later.replacement == Gender.MALE
    assert later.reason == "speaker_map"
    assert later.confidence == 0.60


def test_an_unmarked_line_stays_unknown() -> None:
    item = _one("— Może jutro.")[0]
    assert item.replacement == Gender.UNKNOWN
    assert item.reason == "unresolved"
    assert item.speaker_id == ""


def test_a_disagreeing_name_does_not_outrank_the_verb() -> None:
    item = _one("— Cześć — powiedziała Marek.")[0]
    assert item.replacement == Gender.FEMALE
    assert item.speaker_id == "Marek"
    assert item.reason == "contested"
    assert item.confidence < 0.70


def test_plain_narration_emits_nothing() -> None:
    assert gender_suggestions(["Anna odłożyła raport."]) == []
