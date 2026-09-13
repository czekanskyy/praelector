# SPDX-License-Identifier: Apache-2.0
"""Unit tests for text normalization and artifact detection (AI-02)."""

from __future__ import annotations

from praelector.text.normalise import normalise_text


def test_nfc_normalization() -> None:
    # Combining character e + acute accent vs precomposed é
    combining = "e\u0301"
    res = normalise_text(combining)
    assert res.text == "é"


def test_soft_hyphen_stripping() -> None:
    # "egzem\u00ADplarzy" -> "egzemplarzy"
    text = "Mamy 238 egzem\u00adplarzy książki."
    res = normalise_text(text)
    assert len(res.artifacts) == 1
    art = res.artifacts[0]
    assert art.category == "conversion_artifact"
    assert "U+00AD" in art.rationale
    assert art.original == "egzem\u00adplarzy"
    assert art.proposed == "egzemplarzy"


def test_line_break_hyphenation_stitching() -> None:
    text = "Na biurku leżała notatka: „Briefing prze-\nsunięty na XIV piętro”."
    res = normalise_text(text)
    matching = [a for a in res.artifacts if "prze-" in a.original]
    assert len(matching) == 1
    art = matching[0]
    assert art.original == "prze-\nsunięty"
    assert art.proposed == "przesunięty"


def test_multiple_whitespace_collapsing() -> None:
    text = "Anna spojrzała na zegar.  Było wpół do trzeciej."
    res = normalise_text(text)
    matching = [a for a in res.artifacts if a.original == "  "]
    assert len(matching) == 1
    art = matching[0]
    assert art.proposed == " "
    assert "whitespace" in art.rationale.lower()
