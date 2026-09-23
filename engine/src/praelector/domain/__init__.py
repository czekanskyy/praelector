# SPDX-License-Identifier: Apache-2.0
"""Shared value types: identifiers and enumerations."""

from __future__ import annotations

from praelector.domain.enums import (
    BlockKind,
    Detector,
    EventType,
    Gender,
    GpuVendor,
    JobKind,
    JobStage,
    JobState,
    LlmPreset,
    LlmProviderKind,
    PauseMode,
    Precision,
    RuntimeFlavour,
    SourceFormat,
    SpanKind,
    SpanOrigin,
    SuggestionCategory,
    SuggestionStatus,
    TaskKey,
    VoiceMode,
    VoiceSlot,
)
from praelector.domain.ids import IdPrefix, is_valid_id, new_id

__all__ = [
    "BlockKind",
    "Detector",
    "EventType",
    "Gender",
    "GpuVendor",
    "IdPrefix",
    "JobKind",
    "JobStage",
    "JobState",
    "LlmPreset",
    "LlmProviderKind",
    "PauseMode",
    "Precision",
    "RuntimeFlavour",
    "SourceFormat",
    "SpanKind",
    "SpanOrigin",
    "SuggestionCategory",
    "SuggestionStatus",
    "TaskKey",
    "VoiceMode",
    "VoiceSlot",
    "is_valid_id",
    "new_id",
]
