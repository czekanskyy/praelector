# SPDX-License-Identifier: Apache-2.0
"""Voice-slot fallback (PLAN.md §6.3, TTS-06)."""

from __future__ import annotations

import pytest

from praelector.domain.enums import Gender, VoiceMode, VoiceSlot
from praelector.errors import AppError, ErrorCode
from praelector.voices.assignment import assign_slot

_NARRATOR = {VoiceSlot.NARRATOR}


def test_single_mode_sends_everything_to_the_narrator() -> None:
    item = assign_slot(
        VoiceMode.SINGLE, kind="dialogue", gender=Gender.FEMALE, filled=set(_NARRATOR)
    )
    assert item.slot == VoiceSlot.NARRATOR
    assert item.warning is None


def test_a_missing_narrator_is_an_error_before_the_job() -> None:
    with pytest.raises(AppError) as caught:
        assign_slot(VoiceMode.SINGLE, kind="narration", gender=None, filled=set())
    assert caught.value.code == ErrorCode.TTS_VOICE_SLOT_MISSING
    assert caught.value.detail["slot"] == VoiceSlot.NARRATOR


def test_dialogue_uses_its_slot_when_the_sample_is_present() -> None:
    filled = {VoiceSlot.NARRATOR, VoiceSlot.DIALOGUE}
    item = assign_slot(VoiceMode.NARRATOR_DIALOGUE, kind="dialogue", gender=None, filled=filled)
    assert item.slot == VoiceSlot.DIALOGUE
    assert item.warning is None


def test_a_missing_dialogue_sample_falls_back_and_warns() -> None:
    item = assign_slot(
        VoiceMode.NARRATOR_DIALOGUE, kind="dialogue", gender=None, filled=set(_NARRATOR)
    )
    assert item.slot == VoiceSlot.NARRATOR
    assert item.warning == "slot_missing_dialogue"


def test_gendered_dialogue_picks_male_or_female() -> None:
    filled = {VoiceSlot.NARRATOR, VoiceSlot.MALE, VoiceSlot.FEMALE}
    male = assign_slot(
        VoiceMode.NARRATOR_MALE_FEMALE, kind="dialogue", gender=Gender.MALE, filled=filled
    )
    female = assign_slot(
        VoiceMode.NARRATOR_MALE_FEMALE, kind="dialogue", gender=Gender.FEMALE, filled=filled
    )
    assert male.slot == VoiceSlot.MALE
    assert female.slot == VoiceSlot.FEMALE
    assert male.warning is None


def test_unknown_gender_stays_on_the_narrator() -> None:
    filled = {VoiceSlot.NARRATOR, VoiceSlot.MALE, VoiceSlot.FEMALE}
    item = assign_slot(
        VoiceMode.NARRATOR_MALE_FEMALE, kind="dialogue", gender=Gender.UNKNOWN, filled=filled
    )
    assert item.slot == VoiceSlot.NARRATOR
    assert item.warning is None


def test_a_missing_gender_slot_warns_and_falls_back() -> None:
    item = assign_slot(
        VoiceMode.NARRATOR_MALE_FEMALE,
        kind="dialogue",
        gender=Gender.FEMALE,
        filled={VoiceSlot.NARRATOR, VoiceSlot.MALE},
    )
    assert item.slot == VoiceSlot.NARRATOR
    assert item.warning == "slot_missing_female"


def test_narration_never_uses_a_dialogue_slot() -> None:
    filled = {VoiceSlot.NARRATOR, VoiceSlot.MALE, VoiceSlot.FEMALE, VoiceSlot.DIALOGUE}
    item = assign_slot(
        VoiceMode.NARRATOR_MALE_FEMALE, kind="narration", gender=Gender.MALE, filled=filled
    )
    assert item.slot == VoiceSlot.NARRATOR
