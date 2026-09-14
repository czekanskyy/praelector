# SPDX-License-Identifier: Apache-2.0
"""Unit tests for user pronunciation lexicon matching engine (AI-09)."""

from __future__ import annotations

from praelector.domain.models import LexiconEntryResponse
from praelector.text.lexicon import LexiconMatcher


def test_lexicon_exact_and_regex_matching() -> None:
    entries = [
        LexiconEntryResponse(
            id="lex_01",
            pattern="AI",
            is_regex=False,
            spoken="sztuczna inteligencja",
            language="pl",
            category="dict_hit",
            auto_apply=True,
            case_sensitive=True,
            priority=10,
            created_at="2026-01-01T00:00:00Z",
        ),
        LexiconEntryResponse(
            id="lex_02",
            pattern=r"v(\d+)\.(\d+)",
            is_regex=True,
            spoken=r"wersja \1 kropka \2",
            language="pl",
            category="dict_hit",
            auto_apply=False,
            case_sensitive=False,
            priority=20,
            created_at="2026-01-01T00:00:00Z",
        ),
    ]

    matcher = LexiconMatcher(global_entries=entries)
    text = "Wdrożyliśmy AI w v2.3 wczoraj."
    matches = matcher.match(text)

    assert len(matches) == 2

    m_ai = matches[0]
    assert m_ai.original == "AI"
    assert m_ai.proposed == "sztuczna inteligencja"
    assert m_ai.auto_apply is True

    m_ver = matches[1]
    assert m_ver.original == "v2.3"
    assert m_ver.proposed == "wersja 2 kropka 3"
    assert m_ver.auto_apply is False


def test_project_overrides_global() -> None:
    global_entries = [
        LexiconEntryResponse(
            id="lex_g1",
            pattern="Praelector",
            is_regex=False,
            spoken="Pralektor",
            priority=50,
            created_at="2026-01-01T00:00:00Z",
        )
    ]
    project_entries = [
        LexiconEntryResponse(
            id="lex_p1",
            pattern="Praelector",
            is_regex=False,
            spoken="Preelektor",
            priority=10,
            created_at="2026-01-01T00:00:00Z",
        )
    ]

    matcher = LexiconMatcher(global_entries=global_entries, project_entries=project_entries)
    text = "Witamy w aplikacji Praelector."
    matches = matcher.match(text)

    assert len(matches) == 1
    # Project entry must win
    assert matches[0].proposed == "Preelektor"
