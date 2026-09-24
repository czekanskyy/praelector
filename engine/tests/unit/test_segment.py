# SPDX-License-Identifier: Apache-2.0
"""SentenceSegmenter: regex fallback, abbreviation guard, and pysbd (D-18)."""

from __future__ import annotations

import pytest

from praelector.text.segment import (
    ABBREVIATIONS,
    PysbdSentenceSegmenter,
    RegexSentenceSegmenter,
    SentenceSpan,
    apply_abbreviation_guard,
    sentence_segmenter,
)

_REQUIRED = (
    "np.",
    "tzn.",
    "itd.",
    "itp.",
    "m.in.",
    "ok.",
    "godz.",
    "ul.",
    "dr.",
    "prof.",
    "r.",
    "w.",
    "św.",
)


def _texts(text: str) -> list[str]:
    spans = RegexSentenceSegmenter().segment(text)
    _assert_slices(text, spans)
    return [span.text for span in spans]


def _assert_slices(text: str, spans: list[SentenceSpan]) -> None:
    cursor = 0
    for span in spans:
        assert text[cursor : span.start].strip() == ""
        assert text[span.start : span.end] == span.text
        cursor = span.end
    assert text[cursor:].strip() == ""


def test_the_guard_list_is_the_plan_list() -> None:
    assert ABBREVIATIONS == _REQUIRED


@pytest.mark.parametrize("abbreviation", _REQUIRED)
def test_abbreviations_do_not_end_a_sentence(abbreviation: str) -> None:
    text = f"Zobacz {abbreviation} Dalszy tekst. Koniec."
    assert _texts(text) == [f"Zobacz {abbreviation} Dalszy tekst.", "Koniec."]


def test_regex_segmenter_splits_on_punctuation_and_keeps_a_trailing_abbreviation() -> None:
    assert _texts("Ala ma kota. Kot ma Alę.") == ["Ala ma kota.", "Kot ma Alę."]
    assert _texts("Naprawdę? Tak!") == ["Naprawdę?", "Tak!"]
    assert _texts("Czekaj… Potem ruszaj.") == ["Czekaj…", "Potem ruszaj."]
    assert _texts("Koniec. — Nie.") == ["Koniec.", "— Nie."]
    assert _texts("Zdanie. 2 kolejne.") == ["Zdanie.", "2 kolejne."]
    assert _texts("Koniec. potem jeszcze.") == ["Koniec. potem jeszcze."]
    assert _texts("Koniec np.") == ["Koniec np."]
    assert _texts("") == []
    assert _texts("   ") == []
    assert _texts("  Ala.  Ola. ") == ["Ala.", "Ola."]


def test_abbreviation_guard_merges_a_split_on_the_dot() -> None:
    text = "Zobacz np. ten dom."
    first = text.index("ten")
    spans = [
        SentenceSpan(0, first - 1, text[: first - 1]),
        SentenceSpan(first, len(text), text[first:]),
    ]
    merged = apply_abbreviation_guard(text, spans)
    assert [span.text for span in merged] == [text]
    untouched = [SentenceSpan(0, len(text), text)]
    assert apply_abbreviation_guard("Bez kropki", untouched) == untouched
    assert apply_abbreviation_guard(text, []) == []


def test_default_segmenter_is_pysbd_and_honours_the_guard() -> None:
    segmenter = sentence_segmenter()
    assert isinstance(segmenter, PysbdSentenceSegmenter)
    text = "Sprawdź np. ten zapis. Potem idź dalej."
    spans = segmenter.segment(text)
    _assert_slices(text, spans)
    assert len(spans) == 2
    assert spans[0].text.startswith("Sprawdź")
    assert "ten zapis" in spans[0].text
    assert spans[1].text.startswith("Potem")


def test_pysbd_falls_back_to_the_regex_segmenter() -> None:
    segmenter = PysbdSentenceSegmenter()

    class _Broken:
        def segment(self, text: str) -> list[object]:
            return ["not-a-span"]

    segmenter._engine = _Broken()  # type: ignore[assignment]
    text = "Ala ma kota. Kot też."
    assert [span.text for span in segmenter.segment(text)] == ["Ala ma kota.", "Kot też."]

    class _Empty:
        def segment(self, text: str) -> list[object]:
            return []

    segmenter._engine = _Empty()  # type: ignore[assignment]
    assert [span.text for span in segmenter.segment(text)] == ["Ala ma kota.", "Kot też."]
