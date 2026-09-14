# SPDX-License-Identifier: Apache-2.0
"""Parameterised test suite for Polish dialogue segmentation (DG-01, DG-02, §10.2).

Covers >= 24 dialogue cases matching the master plan requirements:
- em/en/hyphen openers
- whitespace-flanked dash with and without speech verbs
- colon + dash mid-paragraph
- dash used as an aside in narration (must NOT split)
- nested quotation marks inside dash dialogue
- unbalanced quotation marks
- dialogue ending mid-sentence
- two narration insertions in one paragraph
- dash at end of paragraph
- question and exclamation marks inside dialogue
- dialogue immediately followed by a new dialogue paragraph
- mid-paragraph dash after narration
- quote with and without speech verbs
- and more.
"""

from __future__ import annotations

import pytest

from praelector.domain.enums import SpanKind
from praelector.text.dialogue import DialogueSplitResult, split_dialogue

DIALOGUE_TEST_CASES = [
    # 1. Em dash opener (DG-01)
    (
        "— Dzień dobry — powiedział Jan.",
        [
            (SpanKind.DIALOGUE, "Dzień dobry"),
            (SpanKind.NARRATION, "powiedział Jan."),
        ],
        0.90,
        True,
    ),
    # 2. En dash opener (DG-01)
    (
        "– Dzień dobry – powiedział Jan.",
        [
            (SpanKind.DIALOGUE, "Dzień dobry"),
            (SpanKind.NARRATION, "powiedział Jan."),
        ],
        0.90,
        True,
    ),
    # 3. Hyphen opener (DG-01)
    (
        "- Dzień dobry - powiedział Jan.",
        [
            (SpanKind.DIALOGUE, "Dzień dobry"),
            (SpanKind.NARRATION, "powiedział Jan."),
        ],
        0.90,
        True,
    ),
    # 4. Whitespace-flanked dash with speech verb
    (
        "— Nie zdążymy — powiedziała cicho.",
        [
            (SpanKind.DIALOGUE, "Nie zdążymy"),
            (SpanKind.NARRATION, "powiedziała cicho."),
        ],
        0.90,
        True,
    ),
    # 5. Whitespace-flanked dash without speech verb (parenthetical aside within dialogue)
    (
        "— To prawda — choć bolesna — musimy walczyć.",
        [
            (SpanKind.DIALOGUE, "To prawda — choć bolesna — musimy walczyć."),
        ],
        0.45,
        True,
    ),
    # 6. Colon + dash mid-paragraph (DG-02)
    (
        "Barnaba zapytał: — Ile mamy egzemplarzy?",
        [
            (SpanKind.NARRATION, "Barnaba zapytał:"),
            (SpanKind.DIALOGUE, "Ile mamy egzemplarzy?"),
        ],
        0.90,
        True,
    ),
    # 7. Dash used as an aside in narration (must NOT split!) (§10.2)
    (
        "Wszyscy — nawet Anna — milczeli.",
        [
            (SpanKind.NARRATION, "Wszyscy — nawet Anna — milczeli."),
        ],
        0.45,
        False,
    ),
    # 8. Nested „…” inside a dash dialogue (§10.2)
    (
        "— Przeczytałam „Lalkę” — rzekła Anna.",
        [
            (SpanKind.DIALOGUE, "Przeczytałam „Lalkę”"),
            (SpanKind.NARRATION, "rzekła Anna."),
        ],
        0.90,
        True,
    ),
    # 9. Unbalanced quote (Rule 5, confidence 0.35, never applied)
    (
        "Anna rzekła: „Nie pójdę tam.",
        [
            (SpanKind.NARRATION, "Anna rzekła: „Nie pójdę tam."),
        ],
        0.35,
        False,
    ),
    # 10. Dialogue ending mid-sentence with ellipsis
    (
        "— Ale ja... — zaczął Jan.",
        [
            (SpanKind.DIALOGUE, "Ale ja..."),
            (SpanKind.NARRATION, "zaczął Jan."),
        ],
        0.90,
        True,
    ),
    # 11. Two narration insertions in one paragraph (§10.2)
    (
        "— Poczekaj — poprosił Jan — musimy porozmawiać — dodał po chwili.",
        [
            (SpanKind.DIALOGUE, "Poczekaj"),
            (SpanKind.NARRATION, "poprosił Jan"),
            (SpanKind.DIALOGUE, "musimy porozmawiać"),
            (SpanKind.NARRATION, "dodał po chwili."),
        ],
        0.90,
        True,
    ),
    # 12. Dash at end of paragraph (interrupted speech)
    (
        "— Myślałem, że ty —",
        [
            (SpanKind.DIALOGUE, "Myślałem, że ty"),
        ],
        0.90,
        True,
    ),
    # 13. Question and exclamation marks inside dialogue
    (
        "— Naprawdę?! — zawołał Jan.",
        [
            (SpanKind.DIALOGUE, "Naprawdę?!"),
            (SpanKind.NARRATION, "zawołał Jan."),
        ],
        0.90,
        True,
    ),
    # 14. Mid-paragraph dash after narration (DG-02, golden chapter line)
    (
        "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz.",
        [
            (SpanKind.NARRATION, "Walker wzruszył ramionami."),
            (SpanKind.DIALOGUE, "A jednak spróbujemy"),
            (SpanKind.NARRATION, "mruknął i wyszedł na korytarz."),
        ],
        0.90,
        True,
    ),
    # 15. Dialogue continuation in same paragraph
    (
        "— Nie zdążymy — powiedziała cicho. — Deadline mamy o 18:00.",
        [
            (SpanKind.DIALOGUE, "Nie zdążymy"),
            (SpanKind.NARRATION, "powiedziała cicho."),
            (SpanKind.DIALOGUE, "Deadline mamy o 18:00."),
        ],
        0.90,
        True,
    ),
    # 16. Quote with confirmed speech verb
    (
        "Anna powiedziała: „Nie zdążymy”.",
        [
            (SpanKind.NARRATION, "Anna powiedziała:"),
            (SpanKind.DIALOGUE, "Nie zdążymy"),
            (SpanKind.NARRATION, "."),
        ],
        0.90,
        True,
    ),
    # 17. Quote without speech verb (Rule 4: stays narration, conf 0.40)
    (
        "Na biurku leżała notatka: „Briefing przesunięty na XIV piętro”.",
        [
            (SpanKind.NARRATION, "Na biurku leżała notatka: „Briefing przesunięty na XIV piętro”."),
        ],
        0.40,
        False,
    ),
    # 18. French guillemets quote with speech tag
    (
        "«Idziemy» — rzekł Piotr.",
        [
            (SpanKind.DIALOGUE, "Idziemy"),
            (SpanKind.NARRATION, "— rzekł Piotr."),
        ],
        0.90,
        True,
    ),
    # 19. Speech verb preceded by pronoun
    (
        "— Nic nie szkodzi — on powiedział cicho.",
        [
            (SpanKind.DIALOGUE, "Nic nie szkodzi"),
            (SpanKind.NARRATION, "on powiedział cicho."),
        ],
        0.90,
        True,
    ),
    # 20. Speech verb preceded by capitalized name
    (
        "— Nic nie szkodzi — Anna powiedziała cicho.",
        [
            (SpanKind.DIALOGUE, "Nic nie szkodzi"),
            (SpanKind.NARRATION, "Anna powiedziała cicho."),
        ],
        0.90,
        True,
    ),
    # 21. Speech verb preceded by adverb
    (
        "— Chodźmy — cicho rzekła Maria.",
        [
            (SpanKind.DIALOGUE, "Chodźmy"),
            (SpanKind.NARRATION, "cicho rzekła Maria."),
        ],
        0.90,
        True,
    ),
    # 22. Pure narration without any dashes or quotes
    (
        "Anna odłożyła raport i spojrzała na zegar. Było wpół do trzeciej.",
        [
            (
                SpanKind.NARRATION,
                "Anna odłożyła raport i spojrzała na zegar. Było wpół do trzeciej.",
            ),
        ],
        1.0,
        False,
    ),
    # 23. Multiple sentences inside dialogue span
    (
        "— Nie zdążymy. Czas ucieka. — powiedziała Anna.",
        [
            (SpanKind.DIALOGUE, "Nie zdążymy. Czas ucieka."),
            (SpanKind.NARRATION, "powiedziała Anna."),
        ],
        0.90,
        True,
    ),
    # 24. Digits inside dialogue
    (
        "— 238 — odpowiedziała Anna. — Reszta poszła do Washington DC.",
        [
            (SpanKind.DIALOGUE, "238"),
            (SpanKind.NARRATION, "odpowiedziała Anna."),
            (SpanKind.DIALOGUE, "Reszta poszła do Washington DC."),
        ],
        0.90,
        True,
    ),
    # 25. Mid-paragraph dialogue after period without following speech tag
    (
        "Jan zatrzymał się. — Czas na nas.",
        [
            (SpanKind.NARRATION, "Jan zatrzymał się."),
            (SpanKind.DIALOGUE, "Czas na nas."),
        ],
        0.90,
        True,
    ),
]


@pytest.mark.parametrize("text,expected_segments,min_conf,has_dialogue", DIALOGUE_TEST_CASES)
def test_dialogue_segmentation_case_table(
    text: str,
    expected_segments: list[tuple[SpanKind, str]],
    min_conf: float,
    has_dialogue: bool,
) -> None:
    """Verify that split_dialogue matches the >= 24 case specification from §10.2."""
    result: DialogueSplitResult = split_dialogue(text)

    assert result.has_dialogue == has_dialogue
    assert result.confidence >= min_conf - 0.05

    actual_segments = [(s.kind, s.text) for s in result.segments]
    assert actual_segments == expected_segments

    # Invariants check
    for seg in result.segments:
        assert 0 <= seg.start <= seg.end <= len(text)
        assert text[seg.start : seg.end] == seg.text
