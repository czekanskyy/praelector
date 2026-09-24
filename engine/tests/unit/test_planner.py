# SPDX-License-Identifier: Apache-2.0
"""The planner drops skips, expands readings, and keeps voice slots apart."""

from __future__ import annotations

import pytest

from praelector.domain.enums import VoiceMode, VoiceSlot
from praelector.errors import AppError, ErrorCode
from praelector.jobs.planner import SourceBlock, spoken_runs
from praelector.text.apply import AppliedSpan

_PROFILES = {
    VoiceSlot.NARRATOR: ("vpr_n", "hash_n"),
    VoiceSlot.DIALOGUE: ("vpr_d", "hash_d"),
    VoiceSlot.FEMALE: ("vpr_f", "hash_f"),
}


def test_a_reading_replaces_the_print_and_a_skip_drops_out() -> None:
    block = SourceBlock(
        "chp_1",
        "Rok 1984. [przypis]",
        (
            AppliedSpan("pronunciation", 4, 8, spoken="tysiąc dziewięćset osiemdziesiąty czwarty"),
            AppliedSpan("skip", 10, 19),
        ),
    )
    runs, warnings = spoken_runs(
        [block],
        mode=VoiceMode.SINGLE,
        filled={VoiceSlot.NARRATOR},
        profiles=_PROFILES,
    )
    assert warnings == []
    assert len(runs) == 1
    assert runs[0].text == "Rok tysiąc dziewięćset osiemdziesiąty czwarty."
    assert runs[0].voice_slot == VoiceSlot.NARRATOR
    assert runs[0].voice_profile_id == "vpr_n"


def test_dialogue_uses_its_slot_and_paragraphs_join() -> None:
    blocks = [
        SourceBlock("chp_1", "Szła drogą."),
        SourceBlock(
            "chp_1",
            "— Cześć.",
            (AppliedSpan("dialogue", 0, 8, gender="female"),),
        ),
        SourceBlock("chp_1", "Kiwnął głową."),
    ]
    runs, warnings = spoken_runs(
        blocks,
        mode=VoiceMode.NARRATOR_DIALOGUE,
        filled={VoiceSlot.NARRATOR, VoiceSlot.DIALOGUE},
        profiles=_PROFILES,
    )
    assert warnings == []
    assert [run.text for run in runs] == ["Szła drogą.", "— Cześć.", "Kiwnął głową."]
    assert [run.voice_slot for run in runs] == [
        VoiceSlot.NARRATOR,
        VoiceSlot.DIALOGUE,
        VoiceSlot.NARRATOR,
    ]


def test_same_slot_paragraphs_in_one_chapter_join() -> None:
    blocks = [
        SourceBlock("chp_1", "Pierwsze."),
        SourceBlock("chp_1", "Drugie."),
        SourceBlock("chp_2", "Trzecie."),
    ]
    runs, _warnings = spoken_runs(
        blocks,
        mode=VoiceMode.SINGLE,
        filled={VoiceSlot.NARRATOR},
        profiles=_PROFILES,
    )
    assert [run.text for run in runs] == ["Pierwsze. Drugie.", "Trzecie."]
    assert [run.chapter_id for run in runs] == ["chp_1", "chp_2"]


def test_a_pause_is_silence_between_the_words() -> None:
    block = SourceBlock(
        "chp_1",
        "Cisza potem.",
        (AppliedSpan("pause", 5, 6),),
    )
    runs, _warnings = spoken_runs(
        [block],
        mode=VoiceMode.SINGLE,
        filled={VoiceSlot.NARRATOR},
        profiles=_PROFILES,
    )
    assert [(run.kind, run.text) for run in runs] == [
        ("tts", "Cisza"),
        ("silence", ""),
        ("tts", "potem."),
    ]


def test_a_missing_dialogue_slot_falls_back_and_warns_once() -> None:
    blocks = [
        SourceBlock("chp_1", "A", (AppliedSpan("dialogue", 0, 1),)),
        SourceBlock("chp_1", "B", (AppliedSpan("dialogue", 0, 1),)),
    ]
    runs, warnings = spoken_runs(
        blocks,
        mode=VoiceMode.NARRATOR_DIALOGUE,
        filled={VoiceSlot.NARRATOR},
        profiles=_PROFILES,
    )
    assert warnings == ["slot_missing_dialogue"]
    assert len(runs) == 1
    assert runs[0].voice_slot == VoiceSlot.NARRATOR
    assert runs[0].text == "A B"


def test_a_missing_narrator_is_rejected() -> None:
    with pytest.raises(AppError) as caught:
        spoken_runs(
            [SourceBlock("chp_1", "A")],
            mode=VoiceMode.SINGLE,
            filled=set(),
            profiles={},
        )
    assert caught.value.code is ErrorCode.TTS_VOICE_SLOT_MISSING
