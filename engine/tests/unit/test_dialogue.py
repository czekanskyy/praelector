# SPDX-License-Identifier: Apache-2.0
"""Dialogue state machine (DG-01, DG-02, PLAN.md §5.2 and §10.2)."""

from __future__ import annotations

import pytest

from praelector.domain.enums import SuggestionCategory
from praelector.text.dialogue import dialogue_suggestions, segment_block, speech_verbs

_PLAN_VERBS = (
    "powiedział",
    "powiedziała",
    "rzekł",
    "rzekła",
    "mówił",
    "mówiła",
    "odparł",
    "odparła",
    "odrzekł",
    "odrzekła",
    "odpowiedział",
    "odpowiedziała",
    "zapytał",
    "zapytała",
    "spytał",
    "spytała",
    "krzyknął",
    "krzyknęła",
    "szepnął",
    "szepnęła",
    "mruknął",
    "mruknęła",
    "warknął",
    "warknęła",
    "dodał",
    "dodała",
    "wtrącił",
    "wtrąciła",
    "ciągnął",
    "ciągnęła",
    "zauważył",
    "zauważyła",
    "stwierdził",
    "stwierdziła",
    "westchnął",
    "westchnęła",
    "syknął",
    "syknęła",
    "jęknął",
    "jęknęła",
    "zaczął",
    "zaczęła",
    "skończył",
    "skończyła",
    "przerwał",
    "przerwała",
)


def _pieces(text: str) -> list[tuple[str, str]]:
    return [(segment.kind, segment.slice(text)) for segment in segment_block(text)]


def _suggestion(text: str):
    found = dialogue_suggestions(text)
    assert len(found) == 1
    item = found[0]
    assert item.kind == SuggestionCategory.DIALOGUE_SPLIT
    assert item.auto is False
    assert item.original == text
    for mark in item.segments:
        assert text[mark.start : mark.end] == text[mark.start : mark.end]
        assert mark.end > mark.start
    return item


def test_the_verb_list_is_the_plan_list() -> None:
    assert speech_verbs() == frozenset(_PLAN_VERBS)


@pytest.mark.parametrize(
    ("opener", "text"),
    [
        ("em", "— Nie zdążymy — powiedziała cicho."),
        ("en", "\u2013 Nie zdążymy \u2013 powiedziała cicho."),
        ("hyphen", "- Nie zdążymy - powiedziała cicho."),
    ],
)
def test_paragraph_openers(opener: str, text: str) -> None:
    assert _pieces(text) == [
        ("dialogue", "Nie zdążymy"),
        ("narration", "powiedziała cicho."),
    ]
    assert _suggestion(text).confidence == 0.90
    assert opener


def test_golden_paragraph_initial_em_dash() -> None:
    text = "— Nie zdążymy — powiedziała cicho. — Deadline mamy o 18:00."
    assert _pieces(text) == [
        ("dialogue", "Nie zdążymy"),
        ("narration", "powiedziała cicho."),
        ("dialogue", "Deadline mamy o 18:00."),
    ]


def test_flanked_dash_with_a_speech_verb_after_narration() -> None:
    text = "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz."
    assert _pieces(text) == [
        ("narration", "Walker wzruszył ramionami."),
        ("dialogue", "A jednak spróbujemy"),
        ("narration", "mruknął i wyszedł na korytarz."),
    ]
    assert _suggestion(text).confidence >= 0.75


@pytest.mark.parametrize(
    "dash",
    ["\u2014", "\u2013", "-"],
)
def test_colon_plus_dash(dash: str) -> None:
    text = f"Barnaba zapytał: {dash} Ile mamy egzemplarzy?"
    assert _pieces(text) == [
        ("narration", "Barnaba zapytał:"),
        ("dialogue", "Ile mamy egzemplarzy?"),
    ]


def test_an_aside_is_not_a_split() -> None:
    text = "Wszyscy — nawet Anna — milczeli."
    assert _pieces(text) == [("narration", text)]
    item = _suggestion(text)
    assert item.confidence == 0.45
    assert item.reason == "unconfirmed_dash"


def test_a_flanked_dash_without_a_speech_verb_stays_narration() -> None:
    text = "Poszedł — i wrócił."
    assert _pieces(text) == [("narration", text)]
    assert _suggestion(text).confidence == 0.35
    assert _suggestion(text).reason == "odd_dash"


def test_nested_quotes_stay_inside_dash_dialogue() -> None:
    text = "— Widziała „list” na stole — powiedziała."
    assert _pieces(text) == [
        ("dialogue", "Widziała „list” na stole"),
        ("narration", "powiedziała."),
    ]
    assert _suggestion(text).confidence == 0.90


def test_an_unbalanced_quote_is_review_only() -> None:
    text = "Powiedziała „Chodź tu"
    assert _pieces(text) == [("narration", text)]
    item = _suggestion(text)
    assert item.confidence == 0.35
    assert item.reason == "unbalanced_quote"


def test_dialogue_may_end_mid_sentence() -> None:
    text = "— Nie zdążymy, naprawdę — powiedziała i wyszła."
    assert _pieces(text) == [
        ("dialogue", "Nie zdążymy, naprawdę"),
        ("narration", "powiedziała i wyszła."),
    ]


def test_two_narration_insertions() -> None:
    text = "— Pierwsze — powiedziała. — Drugie — dodała cicho. — Trzecie."
    assert _pieces(text) == [
        ("dialogue", "Pierwsze"),
        ("narration", "powiedziała."),
        ("dialogue", "Drugie"),
        ("narration", "dodała cicho."),
        ("dialogue", "Trzecie."),
    ]


def test_a_dash_at_the_end_of_a_paragraph_closes_dialogue() -> None:
    text = "— To wszystko —"
    assert _pieces(text) == [("dialogue", "To wszystko")]
    assert _suggestion(text).confidence == 0.90


def test_question_and_exclamation_inside_dialogue() -> None:
    text = "— Naprawdę? Tak! — krzyknęła."
    assert _pieces(text) == [
        ("dialogue", "Naprawdę? Tak!"),
        ("narration", "krzyknęła."),
    ]


def test_a_following_paragraph_is_its_own_dialogue() -> None:
    first = "— Pierwsze zdanie."
    second = "— Drugie zdanie."
    assert _pieces(first) == [("dialogue", "Pierwsze zdanie.")]
    assert _pieces(second) == [("dialogue", "Drugie zdanie.")]


def test_a_quote_without_a_speech_verb_stays_narration() -> None:
    text = "Na biurku leżała notatka: „Briefing prze-\nsunięty na XIV piętro”."
    assert _pieces(text) == [("narration", text)]
    item = _suggestion(text)
    assert item.confidence == 0.40
    assert item.reason == "quote_without_verb"
    assert item.auto is False
    assert any(
        mark.kind == "dialogue" and "Briefing" in text[mark.start : mark.end]
        for mark in item.segments
    )


def test_a_quote_with_a_speech_verb_in_the_same_sentence_is_dialogue() -> None:
    text = "Anna powiedziała: „Chodź”."
    assert _pieces(text) == [
        ("narration", "Anna powiedziała:"),
        ("dialogue", "Chodź"),
    ]


def test_a_quote_with_a_speech_verb_in_the_adjacent_sentence_is_dialogue() -> None:
    text = "Anna westchnęła. „Chodź”."
    assert _pieces(text) == [
        ("narration", "Anna westchnęła."),
        ("dialogue", "Chodź"),
    ]


def test_a_name_may_precede_the_speech_verb() -> None:
    text = "— Cześć — Anna powiedziała."
    assert _pieces(text) == [
        ("dialogue", "Cześć"),
        ("narration", "Anna powiedziała."),
    ]


def test_a_pronoun_may_precede_the_speech_verb() -> None:
    text = "— Cześć — ona szepnęła."
    assert _pieces(text) == [
        ("dialogue", "Cześć"),
        ("narration", "ona szepnęła."),
    ]


def test_digits_inside_dialogue_stay_in_the_dialogue_span() -> None:
    text = "— 238 — odpowiedziała Anna. — Reszta poszła do Washington DC."
    assert _pieces(text) == [
        ("dialogue", "238"),
        ("narration", "odpowiedziała Anna."),
        ("dialogue", "Reszta poszła do Washington DC."),
    ]


def test_guillemets_with_a_speech_verb() -> None:
    text = "Zapytał: «Idziemy?»"
    assert _pieces(text) == [
        ("narration", "Zapytał:"),
        ("dialogue", "Idziemy?"),
    ]


def test_an_ascii_quote_without_a_verb_is_review_only() -> None:
    text = 'Notatka: "ok".'
    assert _pieces(text) == [("narration", text)]
    assert _suggestion(text).confidence == 0.40


def test_segment_offsets_slice_the_original_text() -> None:
    text = "— Nie zdążymy — powiedziała."
    for segment in segment_block(text):
        assert text[segment.start : segment.end] == segment.slice(text)
        assert 0.0 < segment.confidence <= 1.0


def test_plain_narration_has_no_suggestion() -> None:
    text = "Anna odłożyła raport."
    assert _pieces(text) == [("narration", text)]
    assert dialogue_suggestions(text) == []


def test_the_block_text_is_not_rewritten() -> None:
    text = "Wszyscy — nawet Anna — milczeli."
    snapshot = text
    dialogue_suggestions(text)
    segment_block(text)
    assert text == snapshot
