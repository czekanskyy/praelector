# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the deterministic heuristic pre-pass pipeline (AI-02, AI-08, Table 10.1)."""

from __future__ import annotations

from praelector.domain.enums import SuggestionCategory
from praelector.text.pipeline import DeterministicPrepassPipeline


def test_golden_chapter_blocks_deterministic_prepass() -> None:
    pipeline = DeterministicPrepassPipeline()
    pid = "prj_test"
    cid = "chp_01"

    # Block 1: Rozdział 8
    b1 = pipeline.process_block("Rozdział 8", pid, cid, "blk_01")
    assert any(
        s.category == SuggestionCategory.ORDINAL_HEADING and s.proposed == "Rozdział ósmy"
        for s in b1
    )

    # Block 2: Anna odłożyła raport i spojrzała na zegar.  Było wpół do trzeciej.
    b2 = pipeline.process_block(
        "Anna odłożyła raport i spojrzała na zegar.  Było wpół do trzeciej.", pid, cid, "blk_02"
    )
    assert any(
        s.category == SuggestionCategory.CONVERSION_ARTIFACT and s.original == "  " for s in b2
    )

    # Block 3: — Nie zdążymy — powiedziała cicho. — Deadline mamy o 18:00.
    b3 = pipeline.process_block(
        "— Nie zdążymy — powiedziała cicho. — Deadline mamy o 18:00.", pid, cid, "blk_03"
    )
    assert any(
        s.category == SuggestionCategory.FOREIGN_WORD
        and s.original == "Deadline"
        and s.proposed == "Dedlajn"
        for s in b3
    )
    assert any(
        s.category == SuggestionCategory.NUMERAL
        and s.original == "18:00"
        and s.proposed == "osiemnastej"
        for s in b3
    )

    # Block 4: Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz.
    b4 = pipeline.process_block(
        "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz.",
        pid,
        cid,
        "blk_04",
    )
    assert any(
        s.category == SuggestionCategory.FOREIGN_WORD
        and s.original == "Walker"
        and s.proposed == "Łoker"
        for s in b4
    )

    # Block 5: Barnaba zapytał: — Ile mamy egzem\u00adplarzy?
    b5 = pipeline.process_block(
        "Barnaba zapytał: — Ile mamy egzem\u00adplarzy?", pid, cid, "blk_05"
    )
    assert any(
        s.category == SuggestionCategory.CONVERSION_ARTIFACT and s.proposed == "egzemplarzy"
        for s in b5
    )

    # Block 6: — 238 — odpowiedziała Anna. — Reszta poszła do Washington DC.
    b6 = pipeline.process_block(
        "— 238 — odpowiedziała Anna. — Reszta poszła do Washington DC.", pid, cid, "blk_06"
    )
    assert any(
        s.category == SuggestionCategory.NUMERAL
        and s.original == "238"
        and s.proposed == "dwieście trzydzieści osiem"
        for s in b6
    )
    assert any(
        s.category == SuggestionCategory.TOPONYM
        and s.original == "Washington DC"
        and s.proposed == "Łoszynkton di si"
        for s in b6
    )

    # Block 7: W IT nikt nie odbierał telefonu. Na biurku leżała notatka: „Briefing prze-\nsunięty na XIV piętro”.
    b7 = pipeline.process_block(
        "W IT nikt nie odbierał telefonu. Na biurku leżała notatka: „Briefing prze-\nsunięty na XIV piętro”.",
        pid,
        cid,
        "blk_07",
    )
    assert any(
        s.category == SuggestionCategory.ACRONYM and s.original == "IT" and s.proposed == "aj ti"
        for s in b7
    )
    assert any(
        s.category == SuggestionCategory.CONVERSION_ARTIFACT
        and s.original == "prze-\nsunięty"
        and s.proposed == "przesunięty"
        for s in b7
    )
    assert any(
        s.category == SuggestionCategory.NUMERAL
        and s.original == "XIV"
        and s.proposed == "czternaste"
        for s in b7
    )

    # Block 8: ISBN 978-83-000000-0-0
    b8 = pipeline.process_block("ISBN 978-83-000000-0-0", pid, cid, "blk_08")
    assert any(s.category == SuggestionCategory.CONVERSION_ARTIFACT for s in b8)

    # Block 9: 12 (bare page number)
    b9 = pipeline.process_block("12", pid, cid, "blk_09")
    assert any(s.category == SuggestionCategory.CONVERSION_ARTIFACT for s in b9)
