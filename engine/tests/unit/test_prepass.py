# SPDX-License-Identifier: Apache-2.0
"""The pre-pass runs normalise, skip, numerals, then lexical marks. Text stays put."""

from __future__ import annotations

from dataclasses import dataclass

from praelector.domain.enums import BlockKind, SuggestionCategory
from praelector.ebook.blocks import Block, SourceRef
from praelector.text.prepass import SKIP_KIND, prepass


@dataclass
class _Carrier:
    text: str
    kind: str = "paragraph"


def test_prepass_does_not_mutate_blocks_and_keeps_offsets() -> None:
    blocks = [
        "Rozdział 8",
        "Anna spojrzała na zegar.  Było późno.",
        "Deadline mamy o 18:00.",
        "W IT nikt nie odbierał.",
        "Reszta poszła do Washington DC.",
        "Walker wzruszył ramionami.",
        "ISBN 978-83-000000-0-0",
        "12",
        "Notatka: Briefing prze-\nsunięty na XIV piętro.",
        "egzem\u00adplarzy",
    ]
    snapshot = list(blocks)
    found = prepass(blocks)
    assert blocks == snapshot
    for item in found:
        source = blocks[item.block_index]
        assert item.original == source[item.start : item.end]
        assert item.detector == "heuristic"
        assert 0.0 < item.confidence <= 1.0

    heading = next(item for item in found if item.block_index == 0)
    assert heading.kind == SuggestionCategory.ORDINAL_HEADING
    assert heading.replacement == "Rozdział ósmy"

    assert any(item.reason == "whitespace" and item.block_index == 1 for item in found)
    assert any(
        item.kind == SuggestionCategory.FOREIGN_WORD and item.replacement == "dedlajn"
        for item in found
    )
    assert any(item.reason == "clock" and item.replacement == "osiemnastej" for item in found)
    assert any(
        item.kind == SuggestionCategory.ACRONYM and item.replacement == "aj ti" for item in found
    )
    assert any(
        item.kind == SuggestionCategory.TOPONYM and item.replacement == "Łoszynkton di si"
        for item in found
    )
    assert any(
        item.kind == SuggestionCategory.FOREIGN_WORD and item.replacement == "Łoker"
        for item in found
    )

    isbn = next(item for item in found if item.block_index == 6)
    assert isbn.kind == SKIP_KIND
    assert isbn.reason == "isbn"
    assert isbn.replacement == ""
    assert all(
        item.block_index != 6
        or item.kind == SKIP_KIND
        or item.kind == SuggestionCategory.CONVERSION_ARTIFACT
        for item in found
    )

    page = [item for item in found if item.block_index == 7]
    assert [item.kind for item in page] == [SKIP_KIND]
    assert page[0].reason == "page_number"

    assert any(item.reason == "hyphenation" and item.replacement == "przesunięty" for item in found)
    assert any(item.reason == "roman" and item.replacement == "czternaste" for item in found)
    assert any(item.reason == "soft_hyphen" and item.replacement == "egzemplarzy" for item in found)


def test_skip_comes_from_frontmatter_including_a_toc_run() -> None:
    titles = [f"Rozdział {number}" for number in range(1, 6)]
    blocks = ["Spis treści", *titles]
    found = prepass(blocks, chapter_titles=titles)
    assert {item.block_index for item in found if item.kind == SKIP_KIND} == {0, 1, 2, 3, 4, 5}
    assert {item.reason for item in found if item.kind == SKIP_KIND} == {"toc"}


def test_a_heading_block_marks_a_roman_and_a_page_stays_a_skip() -> None:
    heading = Block(
        kind=BlockKind.HEADING,
        text="IV",
        source_ref=SourceRef(href="ch.xhtml", path="/html/body/h1[1]"),
        ordinal=0,
    )
    page = _Carrier("12")
    district = _Carrier("Washington DC", kind="heading")
    before = (heading.text, page.text, district.text)
    found = prepass([heading, page, district])
    assert (heading.text, page.text, district.text) == before
    roman = next(item for item in found if item.block_index == 0)
    assert roman.kind == SuggestionCategory.ORDINAL_HEADING
    assert roman.replacement == "czwarty"
    assert all(item.kind != SuggestionCategory.NUMERAL for item in found if item.block_index == 1)
    toponym = next(item for item in found if item.block_index == 2)
    assert toponym.kind == SuggestionCategory.TOPONYM
    assert toponym.replacement == "Łoszynkton di si"


def test_dialogue_is_a_split_and_a_quote_without_a_verb_stays_low() -> None:
    spoken = "— Nie zdążymy — powiedziała cicho. — Deadline mamy o 18:00."
    note = "Na biurku leżała notatka: „Briefing prze-\nsunięty na XIV piętro”."
    found = prepass([spoken, note])
    split = next(
        item
        for item in found
        if item.block_index == 0 and item.kind == SuggestionCategory.DIALOGUE_SPLIT
    )
    assert [(mark.kind, spoken[mark.start : mark.end]) for mark in split.segments] == [
        ("dialogue", "Nie zdążymy"),
        ("narration", "powiedziała cicho."),
        ("dialogue", "Deadline mamy o 18:00."),
    ]
    assert split.confidence >= 0.75
    quote = next(
        item
        for item in found
        if item.block_index == 1 and item.kind == SuggestionCategory.DIALOGUE_SPLIT
    )
    assert quote.confidence <= 0.40
    assert quote.auto is False
    assert any(item.reason == "clock" and item.block_index == 0 for item in found)


def test_normalization_can_share_a_block_with_a_later_reading() -> None:
    text = "lata 1989\u20131990"
    found = prepass([text])
    assert text == "lata 1989\u20131990"
    kinds = {(item.reason, item.replacement) for item in found}
    assert ("year", "tysiąc dziewięćset osiemdziesiąty dziewiąty") in kinds
    assert ("dash", "\u2014") in kinds
    assert ("year", "tysiąc dziewięćset dziewięćdziesiąty") in kinds
