# SPDX-License-Identifier: Apache-2.0
"""Unit tests for toponym gazetteer detection (AI-02)."""

from __future__ import annotations

from praelector.text.toponyms import detect_toponyms


def test_detect_toponyms_multi_word() -> None:
    text = "Reszta poszła do Washington DC. Potem polecieli do Los Angeles i New York."
    matches = detect_toponyms(text)

    by_orig = {m.original: m for m in matches}
    assert "Washington DC" in by_orig
    assert by_orig["Washington DC"].proposed == "Łoszynkton di si"
    assert by_orig["Washington DC"].category == "toponym"

    assert "Los Angeles" in by_orig
    assert by_orig["Los Angeles"].proposed == "Los Andżeles"

    assert "New York" in by_orig
    assert by_orig["New York"].proposed == "Niu Jork"
