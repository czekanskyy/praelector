# SPDX-License-Identifier: Apache-2.0
"""The Polish golden chapter from PLAN.md §10.1, as far as the pre-pass goes."""

from __future__ import annotations

from praelector.domain.enums import Gender, SuggestionCategory
from praelector.text.prepass import SKIP_KIND, prepass

# Same paragraphs as scripts/make_fixtures.py GOLDEN_PARAGRAPHS (PLAN.md §10.1).
_PARAGRAPHS = (
    "Rozdział 8",
    "Anna odłożyła raport i spojrzała na zegar.  Było wpół do trzeciej.",
    "— Nie zdążymy — powiedziała cicho. — Deadline mamy o 18:00.",
    "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz.",
    "Barnaba zapytał: — Ile mamy egzem\u00adplarzy?",
    "— 238 — odpowiedziała Anna. — Reszta poszła do Washington DC.",
    "W IT nikt nie odbierał telefonu. Na biurku leżała notatka: „Briefing prze-\nsunięty na XIV piętro”.",
    "ISBN 978-83-000000-0-0",
    "12",
)


def _of(found: list, block: int, kind: str):
    return [item for item in found if item.block_index == block and item.kind == kind]


def test_the_golden_chapter_matches_the_plan_table() -> None:
    blocks = list(_PARAGRAPHS)
    snapshot = list(blocks)
    found = prepass(blocks)
    assert blocks == snapshot

    heading = _of(found, 0, SuggestionCategory.ORDINAL_HEADING)[0]
    assert heading.replacement == "Rozdział ósmy"

    assert any(item.reason == "whitespace" and item.block_index == 1 for item in found)

    opening = _of(found, 2, SuggestionCategory.DIALOGUE_SPLIT)[0]
    assert [(mark.kind, blocks[2][mark.start : mark.end]) for mark in opening.segments] == [
        ("dialogue", "Nie zdążymy"),
        ("narration", "powiedziała cicho."),
        ("dialogue", "Deadline mamy o 18:00."),
    ]
    genders = _of(found, 2, SuggestionCategory.SPEAKER_GENDER)
    assert genders[0].original == "Nie zdążymy"
    assert genders[0].replacement == Gender.FEMALE
    assert genders[0].confidence >= 0.95
    assert any(item.original == "Deadline" and item.replacement == "dedlajn" for item in found)
    assert any(item.reason == "clock" and item.replacement == "osiemnastej" for item in found)

    walker = _of(found, 3, SuggestionCategory.DIALOGUE_SPLIT)[0]
    assert [(mark.kind, blocks[3][mark.start : mark.end]) for mark in walker.segments] == [
        ("narration", "Walker wzruszył ramionami."),
        ("dialogue", "A jednak spróbujemy"),
        ("narration", "mruknął i wyszedł na korytarz."),
    ]
    walker_gender = _of(found, 3, SuggestionCategory.SPEAKER_GENDER)[0]
    assert walker_gender.replacement == Gender.MALE
    assert walker_gender.speaker_id == "Walker"
    assert any(item.original == "Walker" and item.replacement == "Łoker" for item in found)

    barnaba = _of(found, 4, SuggestionCategory.DIALOGUE_SPLIT)[0]
    assert [(mark.kind, blocks[4][mark.start : mark.end]) for mark in barnaba.segments][:2] == [
        ("narration", "Barnaba zapytał:"),
        ("dialogue", "Ile mamy egzem\u00adplarzy?"),
    ]
    barnaba_gender = _of(found, 4, SuggestionCategory.SPEAKER_GENDER)[0]
    assert barnaba_gender.replacement == Gender.MALE
    assert barnaba_gender.speaker_id == "Barnaba"
    assert barnaba_gender.confidence >= 0.95

    assert any(
        item.original == "238" and item.replacement == "dwieście trzydzieści osiem"
        for item in found
    )
    anna = next(
        item for item in _of(found, 5, SuggestionCategory.SPEAKER_GENDER) if item.original == "238"
    )
    assert anna.replacement == Gender.FEMALE
    assert anna.speaker_id == "Anna"
    assert any(
        item.kind == SuggestionCategory.TOPONYM and item.replacement == "Łoszynkton di si"
        for item in found
    )
    assert any(
        item.kind == SuggestionCategory.ACRONYM and item.replacement == "aj ti" for item in found
    )
    assert any(item.reason == "hyphenation" and item.replacement == "przesunięty" for item in found)
    assert any(item.reason == "soft_hyphen" and item.replacement == "egzemplarzy" for item in found)
    assert any(item.reason == "roman" and item.replacement == "czternaste" for item in found)

    quote = _of(found, 6, SuggestionCategory.DIALOGUE_SPLIT)[0]
    assert quote.reason == "quote_without_verb"
    assert quote.confidence <= 0.40
    assert quote.auto is False

    assert _of(found, 7, SKIP_KIND)[0].reason == "isbn"
    assert _of(found, 8, SKIP_KIND)[0].reason == "page_number"
