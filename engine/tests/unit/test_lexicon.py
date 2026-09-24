# SPDX-License-Identifier: Apache-2.0
"""Global and project lexicon rules become dict_hit suggestions (AI-09)."""

from __future__ import annotations

from praelector.domain.enums import Detector, SuggestionCategory
from praelector.text.lexicon import LexiconRule, lexicon_suggestions
from praelector.text.prepass import prepass


def test_an_exact_rule_is_a_whole_token_and_can_be_pre_accepted() -> None:
    text = "W IT nikt nie widział itemu."
    found = lexicon_suggestions(
        text,
        [LexiconRule("IT", "aj ti", auto=True)],
    )
    assert len(found) == 1
    item = found[0]
    assert item.kind == SuggestionCategory.DICT_HIT
    assert item.original == "IT"
    assert item.replacement == "aj ti"
    assert item.auto is True
    assert item.detector == Detector.DICT
    assert item.confidence == 0.99
    assert text == "W IT nikt nie widział itemu."


def test_a_project_rule_hides_the_global_one() -> None:
    rules = [
        LexiconRule("Walker", "łoker", scope="global"),
        LexiconRule("Walker", "łolker", scope="project", priority=50),
    ]
    found = lexicon_suggestions("Walker wszedł.", rules)
    assert [item.replacement for item in found] == ["łolker"]


def test_lower_priority_wins_when_spans_overlap() -> None:
    rules = [
        LexiconRule(r"Washington(?: DC)?", "łaszyngton", is_regex=True, priority=20),
        LexiconRule("DC", "di si", priority=80),
    ]
    found = lexicon_suggestions("Washington DC", rules)
    assert [(item.original, item.replacement) for item in found] == [
        ("Washington DC", "łaszyngton")
    ]


def test_a_broken_regex_is_skipped() -> None:
    assert lexicon_suggestions("Anna", [LexiconRule("(", "x", is_regex=True)]) == []


def test_prepass_lets_the_lexicon_replace_a_foreign_word() -> None:
    text = "Walker wzruszył ramionami."
    found = prepass([text], lexicon=[LexiconRule("Walker", "łolker", auto=True)])
    walkers = [item for item in found if item.original == "Walker"]
    assert len(walkers) == 1
    assert walkers[0].kind == SuggestionCategory.DICT_HIT
    assert walkers[0].replacement == "łolker"
    assert walkers[0].auto is True
