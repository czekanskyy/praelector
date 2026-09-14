# SPDX-License-Identifier: Apache-2.0
"""Unit tests for sentence segmentation with Polish abbreviation guards (D-18)."""

from __future__ import annotations

from praelector.text.segmentation import PysbdSentenceSegmenter, RegexSentenceSegmenter


def test_pysbd_segmentation_offsets_match() -> None:
    text = "To jest pierwsze zdanie. To jest drugie zdanie! A to trzecie?"
    segmenter = PysbdSentenceSegmenter()
    segments = segmenter.segment(text)

    assert len(segments) == 3
    for seg in segments:
        assert text[seg.start : seg.end] == seg.text


def test_pysbd_abbreviation_protection() -> None:
    text = (
        "Spotkanie odbędzie się o godz. 18:00 w sali nr 5. Będą omawiane m.in. plany na rok 2025."
    )
    segmenter = PysbdSentenceSegmenter()
    segments = segmenter.segment(text)

    # Should not split on "godz." or "m.in."
    assert len(segments) == 2
    assert "godz. 18:00" in segments[0].text
    assert "m.in." in segments[1].text


def test_regex_fallback_segmenter() -> None:
    text = "Pierwsze zdanie. Drugie zdanie. Trzecie zdanie."
    segmenter = RegexSentenceSegmenter()
    segments = segmenter.segment(text)

    assert len(segments) == 3
    assert "Pierwsze zdanie." in segments[0].text
    assert "Drugie zdanie." in segments[1].text
    assert "Trzecie zdanie." in segments[2].text
