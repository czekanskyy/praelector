# SPDX-License-Identifier: Apache-2.0
"""Test suite for the Polish golden chapter fixture (AI-02, DG-01..DG-06, §10.1)."""

from __future__ import annotations

import json
from pathlib import Path

from praelector.domain.enums import SuggestionCategory
from praelector.text.pipeline import DeterministicPrepassPipeline

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_golden_chapter_fixtures_exist() -> None:
    """Verify fixture files exist on disk."""
    txt_path = FIXTURES_DIR / "pl_chapter_01.txt"
    json_path = FIXTURES_DIR / "pl_chapter_01.expected.json"

    assert txt_path.is_file(), "pl_chapter_01.txt missing"
    assert json_path.is_file(), "pl_chapter_01.expected.json missing"


def test_golden_chapter_20_rows_table() -> None:
    """Execute the deterministic pre-pass pipeline on pl_chapter_01.txt and verify all 20 rows from Table 10.1."""
    txt_path = FIXTURES_DIR / "pl_chapter_01.txt"
    json_path = FIXTURES_DIR / "pl_chapter_01.expected.json"

    with open(txt_path, encoding="utf-8") as f:
        content = f.read()

    with open(json_path, encoding="utf-8") as f:
        expected_meta = json.load(f)
    assert len(expected_meta["cases"]) == 20

    # Split into paragraphs/blocks
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    blocks = [(f"block_{i}", p) for i, p in enumerate(paragraphs)]

    pipeline = DeterministicPrepassPipeline()
    results_by_block = pipeline.process_chapter_blocks(
        blocks=blocks,
        project_id="proj_golden",
        chapter_id="chap_01",
    )

    all_suggestions = [sug for sugs in results_by_block.values() for sug in sugs]

    # 1. Heading ordinal: ordinal_heading: Rozdział 8 -> Rozdział ósmy (AI-02)
    sug_1 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.ORDINAL_HEADING and s.original == "Rozdział 8"
        ),
        None,
    )
    assert sug_1 is not None
    assert sug_1.proposed == "Rozdział ósmy"
    assert sug_1.confidence >= 0.90

    # 2. Double space: conversion_artifact (AI-02)
    sug_2 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.CONVERSION_ARTIFACT and s.original == "  "
        ),
        None,
    )
    assert sug_2 is not None
    assert sug_2.proposed == " "

    # 3. Paragraph-initial em dash: dialogue span Nie zdążymy, narration powiedziała cicho., dialogue Deadline mamy o 18:00. (DG-01)
    sug_3 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.DIALOGUE_SPLIT and "Nie zdążymy" in s.original
        ),
        None,
    )
    assert sug_3 is not None
    assert sug_3.payload_json is not None
    payload_3 = json.loads(sug_3.payload_json)
    seg_texts_3 = [(s["kind"], s["text"]) for s in payload_3["segments"]]
    assert seg_texts_3 == [
        ("dialogue", "Nie zdążymy"),
        ("narration", "powiedziała cicho."),
        ("dialogue", "Deadline mamy o 18:00."),
    ]

    # 4. Gender from verb suffix: powiedziała -> female, conf >= 0.95 (DG-03, DG-04)
    sug_4 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.SPEAKER_GENDER and s.original == "Nie zdążymy"
        ),
        None,
    )
    assert sug_4 is not None
    assert sug_4.proposed == "female"
    assert sug_4.confidence >= 0.95

    # 5. English token: foreign_word/dict_hit: Deadline (AI-08, D-12)
    sug_5 = next(
        (
            s
            for s in all_suggestions
            if s.category in (SuggestionCategory.FOREIGN_WORD, SuggestionCategory.DICT_HIT)
            and s.original == "Deadline"
        ),
        None,
    )
    assert sug_5 is not None
    assert sug_5.proposed == "Dedlajn"

    # 6. Time numeral: numeral: 18:00 -> osiemnastej (AI-02, D-11)
    sug_6 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.NUMERAL and s.original == "18:00"
        ),
        None,
    )
    assert sug_6 is not None
    assert sug_6.proposed == "osiemnastej"

    # 7. Mid-paragraph dash after narration: narration Walker wzruszył ramionami. + dialogue A jednak spróbujemy + narration mruknął... (DG-02)
    sug_7 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.DIALOGUE_SPLIT
            and "Walker wzruszył ramionami" in s.original
        ),
        None,
    )
    assert sug_7 is not None
    assert sug_7.payload_json is not None
    payload_7 = json.loads(sug_7.payload_json)
    seg_texts_7 = [(s["kind"], s["text"]) for s in payload_7["segments"]]
    assert seg_texts_7 == [
        ("narration", "Walker wzruszył ramionami."),
        ("dialogue", "A jednak spróbujemy"),
        ("narration", "mruknął i wyszedł na korytarz."),
    ]

    # 8. Gender male + speaker label: mruknął -> male; speaker_id = "Walker" (DG-03, DG-06)
    sug_8 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.SPEAKER_GENDER
            and s.original == "A jednak spróbujemy"
        ),
        None,
    )
    assert sug_8 is not None
    assert sug_8.proposed == "male"
    assert sug_8.confidence >= 0.95
    assert sug_8.payload_json is not None
    payload_8 = json.loads(sug_8.payload_json)
    assert payload_8["speaker_id"] == "Walker"

    # 9. Foreign surname: foreign_word: Walker -> Łoker (AI-02)
    sug_9 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.FOREIGN_WORD and s.original == "Walker"
        ),
        None,
    )
    assert sug_9 is not None
    assert sug_9.proposed == "Łoker"

    # 10. Colon + dash mid-paragraph: narration Barnaba zapytał: + dialogue Ile mamy egzemplarzy? (DG-02)
    sug_10 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.DIALOGUE_SPLIT and "Barnaba zapytał:" in s.original
        ),
        None,
    )
    assert sug_10 is not None
    assert sug_10.payload_json is not None
    payload_10 = json.loads(sug_10.payload_json)
    seg_texts_10 = [(s["kind"], s["text"]) for s in payload_10["segments"]]
    assert seg_texts_10[0] == ("narration", "Barnaba zapytał:")
    assert seg_texts_10[1][0] == "dialogue"
    assert "Ile mamy egzem" in seg_texts_10[1][1]

    # 11. -a male name exception: Barnaba stays male (verb zapytał agrees; name lexicon must not flip it) (DG-04)
    sug_11 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.SPEAKER_GENDER and "Ile mamy egzem" in s.original
        ),
        None,
    )
    assert sug_11 is not None
    assert sug_11.proposed == "male"
    assert sug_11.confidence >= 0.85
    assert sug_11.payload_json is not None
    payload_11 = json.loads(sug_11.payload_json)
    assert payload_11["speaker_id"] == "Barnaba"

    # 12. Digits inside dialogue: numeral: 238 -> dwieście trzydzieści osiem (AI-02)
    sug_12 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.NUMERAL and s.original == "238"
        ),
        None,
    )
    assert sug_12 is not None
    assert sug_12.proposed == "dwieście trzydzieści osiem"

    # 13. Toponym: toponym: Washington DC -> Łoszynkton di si (AI-02)
    sug_13 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.TOPONYM and s.original == "Washington DC"
        ),
        None,
    )
    assert sug_13 is not None
    assert sug_13.proposed == "Łoszynkton di si"

    # 14. Acronym: acronym: IT -> aj ti (AI-02)
    sug_14 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.ACRONYM and s.original == "IT"
        ),
        None,
    )
    assert sug_14 is not None
    assert sug_14.proposed == "aj ti"

    # 15. Hyphenation across line break: conversion_artifact: prze-\nsunięty -> przesunięty (AI-02)
    sug_15 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.CONVERSION_ARTIFACT
            and s.original == "prze-\nsunięty"
        ),
        None,
    )
    assert sug_15 is not None
    assert sug_15.proposed == "przesunięty"

    # 16. Soft hyphen: removed silently, recorded as conversion_artifact (AI-02)
    sug_16 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.CONVERSION_ARTIFACT and "\xad" in s.original
        ),
        None,
    )
    assert sug_16 is not None
    assert sug_16.proposed == "egzemplarzy"

    # 17. Roman numeral: numeral: XIV -> czternaste (AI-02)
    sug_17 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.NUMERAL and s.original == "XIV"
        ),
        None,
    )
    assert sug_17 is not None
    assert sug_17.proposed == "czternaste"

    # 18. Quote without a speech verb: „Briefing …” stays narration; at most a 0.40 dialogue_split suggestion; must not auto-apply (DG-02)
    sug_18 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.DIALOGUE_SPLIT and "Briefing" in s.original
        ),
        None,
    )
    assert sug_18 is not None
    assert sug_18.confidence <= 0.40
    # Must NOT auto-apply: confidence < 0.75 threshold
    assert sug_18.confidence < 0.75

    # 19. ISBN line: skip span / conversion_artifact (EB-08)
    sug_19 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.CONVERSION_ARTIFACT and "ISBN" in s.original
        ),
        None,
    )
    assert sug_19 is not None

    # 20. Bare page number: skip span / conversion_artifact (EB-08)
    sug_20 = next(
        (
            s
            for s in all_suggestions
            if s.category == SuggestionCategory.CONVERSION_ARTIFACT and s.original == "12"
        ),
        None,
    )
    assert sug_20 is not None
