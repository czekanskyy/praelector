# SPDX-License-Identifier: Apache-2.0
"""Domain enumerations for Praelector entities and workflows."""

from __future__ import annotations

from enum import StrEnum


class VoiceMode(StrEnum):
    """Voice assignment mode for narration and characters."""

    SINGLE = "single"
    NARRATOR_DIALOGUE = "narrator_dialogue"
    NARRATOR_MALE_FEMALE = "narrator_male_female"


class VoiceSlot(StrEnum):
    """Voice slot assignment in a project."""

    NARRATOR = "narrator"
    DIALOGUE = "dialogue"
    MALE = "male"
    FEMALE = "female"


class SourceFormat(StrEnum):
    """Supported source book formats."""

    EPUB = "epub"
    PDF = "pdf"
    MOBI = "mobi"
    AZW3 = "azw3"


class BlockKind(StrEnum):
    """Structural kind of text block."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    BLOCKQUOTE = "blockquote"
    LIST_ITEM = "list_item"
    CAPTION = "caption"


class SpanKind(StrEnum):
    """Semantic classification of a character span."""

    NARRATION = "narration"
    DIALOGUE = "dialogue"
    PRONUNCIATION = "pronunciation"
    PAUSE = "pause"
    SKIP = "skip"


class Gender(StrEnum):
    """Grammatical and speaker gender tag for dialogue."""

    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class GenderDetector(StrEnum):
    """Provenance method of a gender assignment."""

    HEURISTIC = "heuristic"
    LLM = "llm"
    MANUAL = "manual"


class SpanOrigin(StrEnum):
    """Source that created a span."""

    INGEST = "ingest"
    HEURISTIC = "heuristic"
    LLM = "llm"
    MANUAL = "manual"


class SuggestionCategory(StrEnum):
    """Categories of suggestions surfaced by the text pipeline."""

    FOREIGN_WORD = "foreign_word"
    ACRONYM = "acronym"
    TOPONYM = "toponym"
    NUMERAL = "numeral"
    ORDINAL_HEADING = "ordinal_heading"
    DIALOGUE_SPLIT = "dialogue_split"
    SPEAKER_GENDER = "speaker_gender"
    CONVERSION_ARTIFACT = "conversion_artifact"
    DICT_HIT = "dict_hit"


class SuggestionStatus(StrEnum):
    """Lifecycle status of a suggestion in the review queue."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"
    FAILED = "failed"


class DetectorKind(StrEnum):
    """Engine component that produced a suggestion."""

    HEURISTIC = "heuristic"
    LLM = "llm"
    DICT = "dict"


class JobKind(StrEnum):
    """Kind of background execution job."""

    PREP = "prep"
    RECORD = "record"


class JobState(StrEnum):
    """High-level state of a background job."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    MUXING = "muxing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(StrEnum):
    """Sub-stage within an active job."""

    PLAN = "plan"
    SYNTH = "synth"
    MUX = "mux"


class PlanItemKind(StrEnum):
    """Type of action in an audio synthesis plan."""

    TTS = "tts"
    SILENCE = "silence"
