# SPDX-License-Identifier: Apache-2.0
"""Structured output schemas for LLM tasks (AI-03, LM-04).

Defines Pydantic models and JSON Schema definitions for the three LLM tasks:
1. classify_cheap: confirm / reject / correct deterministic candidates (acronyms, numerals, foreign, toponyms)
2. dialogue_hard: sub-threshold dialogue splits and contested gender determination
3. pronounce: Polish phonetic readout approximation for confirmed foreign tokens
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1. classify_cheap models (batch up to 8 items)
# ---------------------------------------------------------------------------


class ClassificationItem(BaseModel):
    """Classification decision for a single suggestion candidate."""

    id: str
    action: str = Field(description="'confirm', 'reject', or 'correct'")
    corrected: str | None = Field(
        default=None, description="Corrected spoken text if action is 'correct'"
    )
    rationale: str | None = Field(default=None, description="Brief explanation of the decision")


class ClassificationBatchResponse(BaseModel):
    """Batch response for classify_cheap task."""

    items: list[ClassificationItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. dialogue_hard models (1 block per request)
# ---------------------------------------------------------------------------


class HardDialogueSegment(BaseModel):
    """Segment parsed from an ambiguous or contested block."""

    kind: str = Field(description="'narration' or 'dialogue'")
    text: str = Field(description="Exact substring for this segment")
    gender: str | None = Field(
        default=None, description="'male', 'female', or 'unknown' for dialogue"
    )
    speaker_id: str | None = Field(
        default=None, description="Name or identifier of the speaker if known"
    )


class DialogueSplitHardResponse(BaseModel):
    """Response for dialogue_hard task."""

    has_dialogue: bool
    segments: list[HardDialogueSegment] = Field(default_factory=list)
    rationale: str | None = None


# ---------------------------------------------------------------------------
# 3. pronounce models (batch up to 8 items)
# ---------------------------------------------------------------------------


class PronounceItem(BaseModel):
    """Polish phonetic readout for a foreign token."""

    id: str
    original: str
    spoken: str = Field(description="Polish phonetic transcription suitable for Polish TTS")
    rationale: str | None = None


class PronounceBatchResponse(BaseModel):
    """Batch response for pronounce task."""

    items: list[PronounceItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Task Schema Registry
# ---------------------------------------------------------------------------


TASK_SCHEMAS: dict[str, type[BaseModel]] = {
    "classify_cheap": ClassificationBatchResponse,
    "dialogue_hard": DialogueSplitHardResponse,
    "pronounce": PronounceBatchResponse,
}


def get_task_schema(task_key: str) -> dict[str, Any] | None:
    """Retrieve JSON Schema for a registered LLM task."""
    model_cls = TASK_SCHEMAS.get(task_key)
    if model_cls is None:
        return None
    return model_cls.model_json_schema()
