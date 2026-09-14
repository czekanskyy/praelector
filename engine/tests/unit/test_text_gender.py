# SPDX-License-Identifier: Apache-2.0
"""Unit tests for speaker gender resolution signal ladder (DG-03..DG-06, §5.3)."""

from __future__ import annotations

from praelector.domain.enums import Gender, GenderDetector, SpanKind, VoiceMode
from praelector.text.dialogue import split_dialogue
from praelector.text.gender import (
    GIVEN_NAMES,
    MALE_A_EXCEPTIONS,
    ChapterSpeakerMap,
    generate_gender_suggestions,
    resolve_speaker_gender,
)


def test_male_a_exceptions_lexicon() -> None:
    """Verify that mandatory -a male exceptions are marked as male (§5.3 Rank 2)."""
    mandatory_names = ["Barnaba", "Kuba", "Bonawentura", "Kosma", "Jarema", "Zawisza"]
    for name in mandatory_names:
        assert name.lower() in MALE_A_EXCEPTIONS
        res = GIVEN_NAMES.lookup(name)
        assert res is not None, f"Expected {name} to be found in lexicon"
        gender, conf = res
        assert gender == Gender.MALE, f"Expected {name} to be male, got {gender}"
        assert conf >= 0.85


def test_female_given_names_lexicon() -> None:
    """Verify that common Polish female names are recognized as female."""
    names = ["Anna", "Maria", "Katarzyna", "Zofia", "Ewa"]
    for name in names:
        res = GIVEN_NAMES.lookup(name)
        assert res is not None
        gender, conf = res
        assert gender == Gender.FEMALE
        assert conf >= 0.85


def test_signal_1_past_tense_speech_verb() -> None:
    """Signal 1: -ł -> male (0.95), -ła -> female (0.95)."""
    # Female verb
    text_f = "— Nie zdążymy — powiedziała cicho."
    split_f = split_dialogue(text_f)
    res_f = resolve_speaker_gender(split_f.segments, text_f)
    diag_f = [s for s in res_f if s.kind == SpanKind.DIALOGUE]
    assert len(diag_f) == 1
    assert diag_f[0].gender == Gender.FEMALE
    assert diag_f[0].gender_confidence == 0.95
    assert diag_f[0].gender_detector == GenderDetector.HEURISTIC

    # Male verb
    text_m = "— Spróbujemy — mruknął Jan."
    split_m = split_dialogue(text_m)
    res_m = resolve_speaker_gender(split_m.segments, text_m)
    diag_m = [s for s in res_m if s.kind == SpanKind.DIALOGUE]
    assert len(diag_m) == 1
    assert diag_m[0].gender == Gender.MALE
    assert diag_m[0].gender_confidence == 0.95
    assert diag_m[0].speaker_id == "Jan"


def test_signal_2_given_name_and_agreement() -> None:
    """Signal 2: Name in speech tag agrees with verb suffix or resolves gender."""
    # Barnaba with -ł verb zapytał
    text = "Barnaba zapytał: — Ile mamy egzemplarzy?"
    split_res = split_dialogue(text)
    res = resolve_speaker_gender(split_res.segments, text)
    diag = [s for s in res if s.kind == SpanKind.DIALOGUE]
    assert len(diag) == 1
    assert diag[0].gender == Gender.MALE
    assert diag[0].gender_confidence == 0.95
    assert diag[0].speaker_id == "Barnaba"

    # Foreign name Walker with mruknął
    text_w = "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął i wyszedł na korytarz."
    split_w = split_dialogue(text_w)
    res_w = resolve_speaker_gender(split_w.segments, text_w)
    diag_w = [s for s in res_w if s.kind == SpanKind.DIALOGUE]
    assert len(diag_w) == 1
    assert diag_w[0].gender == Gender.MALE
    assert diag_w[0].speaker_id == "Walker"
    assert diag_w[0].gender_confidence == 0.95


def test_signal_3_adjacent_pronouns_and_participles() -> None:
    """Signal 3: Adjacent sentence pronouns/participles (0.65)."""
    # Context has 'ona' and 'zrobiła'
    text = "— Czas ucieka."
    split_res = split_dialogue(text)
    res = resolve_speaker_gender(
        split_res.segments,
        text,
        adjacent_context="Ona spojrzała na zegar i szybko wyszła.",
    )
    diag = [s for s in res if s.kind == SpanKind.DIALOGUE]
    assert len(diag) == 1
    assert diag[0].gender == Gender.FEMALE
    assert diag[0].gender_confidence == 0.65


def test_signal_4_chapter_speaker_map() -> None:
    """Signal 4: Chapter speaker map propagates gender for known speaker_id (0.60)."""
    cmap = ChapterSpeakerMap()
    cmap.record("Walker", Gender.MALE, 0.95)

    # Later paragraph with Walker but present-tense or ambiguous verb
    text = "Walker mówi: — Ruszajmy."
    split_res = split_dialogue(text)
    res = resolve_speaker_gender(split_res.segments, text, chapter_speaker_map=cmap)
    diag = [s for s in res if s.kind == SpanKind.DIALOGUE]
    assert len(diag) == 1
    assert diag[0].speaker_id == "Walker"
    # Either resolved by name (0.85) or map (0.60), both yield MALE
    assert diag[0].gender == Gender.MALE
    assert diag[0].gender_confidence is not None and diag[0].gender_confidence >= 0.60


def test_signal_5_unknown_gender_voice_mode_fallback() -> None:
    """Signal 5: Fallback when gender stays unknown (DG-05)."""
    text = "— Tajemniczy głos rozległ się w ciemności."
    split_res = split_dialogue(text)

    # Single mode -> narrator
    res_single = resolve_speaker_gender(split_res.segments, text, voice_mode=VoiceMode.SINGLE)
    diag_single = [s for s in res_single if s.kind == SpanKind.DIALOGUE]
    assert diag_single[0].gender == Gender.UNKNOWN

    # Suggestions emitted
    sugs = generate_gender_suggestions(
        res_single,
        project_id="p1",
        chapter_id="c1",
        block_id="b1",
    )
    assert len(sugs) == 1
    assert sugs[0].category.value == "speaker_gender"
    assert sugs[0].proposed == "unknown"


def test_multiple_dialogues_in_same_block_continuation() -> None:
    """Paragraph with dialogue continuation inherits speaker from earlier utterance."""
    text = "— 238 — odpowiedziała Anna. — Reszta poszła do Washington DC."
    split_res = split_dialogue(text)
    res = resolve_speaker_gender(split_res.segments, text)
    diag = [s for s in res if s.kind == SpanKind.DIALOGUE]
    assert len(diag) == 2
    assert diag[0].gender == Gender.FEMALE
    assert diag[0].speaker_id == "Anna"
    assert diag[1].gender == Gender.FEMALE
    assert diag[1].speaker_id == "Anna"
