# SPDX-License-Identifier: Apache-2.0
"""Map a span onto a voice slot (PLAN.md §6.3, TTS-06).

A missing narrator is an error before the job starts. Any other missing
sample falls back to the narrator and is recorded as a warning.
"""

from __future__ import annotations

from dataclasses import dataclass

from praelector.domain.enums import Gender, VoiceMode, VoiceSlot
from praelector.errors import AppError, ErrorCode


@dataclass(frozen=True, slots=True)
class SlotAssignment:
    """``slot`` is what will be spoken. ``warning`` is set on a fallback."""

    slot: str
    warning: str | None = None


def assign_slot(
    mode: VoiceMode,
    *,
    kind: str,
    gender: str | None,
    filled: set[str],
) -> SlotAssignment:
    """Choose the slot for one span. ``filled`` holds slots that have a sample."""
    if VoiceSlot.NARRATOR not in filled:
        raise AppError(
            ErrorCode.TTS_VOICE_SLOT_MISSING,
            detail={"slot": VoiceSlot.NARRATOR, "mode": mode},
        )
    wanted = _wanted(mode, kind, gender)
    if wanted in filled:
        return SlotAssignment(wanted)
    return SlotAssignment(
        VoiceSlot.NARRATOR,
        warning=f"slot_missing_{wanted}",
    )


def _wanted(mode: VoiceMode, kind: str, gender: str | None) -> str:
    if mode is VoiceMode.SINGLE or kind != "dialogue":
        return VoiceSlot.NARRATOR
    if mode is VoiceMode.NARRATOR_DIALOGUE:
        return VoiceSlot.DIALOGUE
    if gender == Gender.MALE:
        return VoiceSlot.MALE
    if gender == Gender.FEMALE:
        return VoiceSlot.FEMALE
    return VoiceSlot.NARRATOR
