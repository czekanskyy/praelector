# SPDX-License-Identifier: Apache-2.0
"""Every enumeration the engine and the UI agree on.

These are the source of truth for the generated TypeScript unions in
``packages/schemas``. Adding a member is an additive change; renaming or removing
one is breaking and must be marked as such (CI_AND_RELEASE.md §6).
"""

from __future__ import annotations

from enum import StrEnum


class SourceFormat(StrEnum):
    EPUB = "epub"
    PDF = "pdf"
    MOBI = "mobi"
    AZW3 = "azw3"
    AZW = "azw"


class BlockKind(StrEnum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    BLOCKQUOTE = "blockquote"
    LIST_ITEM = "list_item"
    CAPTION = "caption"


class SpanKind(StrEnum):
    NARRATION = "narration"
    DIALOGUE = "dialogue"
    PRONUNCIATION = "pronunciation"
    PAUSE = "pause"
    SKIP = "skip"


class SpanOrigin(StrEnum):
    INGEST = "ingest"
    HEURISTIC = "heuristic"
    LLM = "llm"
    MANUAL = "manual"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class VoiceMode(StrEnum):
    SINGLE = "single"
    NARRATOR_DIALOGUE = "narrator_dialogue"
    NARRATOR_MALE_FEMALE = "narrator_male_female"


class VoiceSlot(StrEnum):
    NARRATOR = "narrator"
    DIALOGUE = "dialogue"
    MALE = "male"
    FEMALE = "female"


#: The nine categories of PRD §6.3.1 — exactly nine, no others (PLAN.md §5.4).
class SuggestionCategory(StrEnum):
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
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"
    #: The LLM returned unusable output twice; carries ``error_code`` and no
    #: proposal, excluded from apply, filterable in review (PLAN.md D-15).
    FAILED = "failed"


class Detector(StrEnum):
    HEURISTIC = "heuristic"
    LLM = "llm"
    DICT = "dict"


class JobKind(StrEnum):
    PREP = "prep"
    RECORD = "record"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    MUXING = "muxing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(StrEnum):
    PLAN = "plan"
    SYNTH = "synth"
    MUX = "mux"


class PauseMode(StrEnum):
    FINISH_CURRENT = "finish_current"
    DISCARD_CURRENT = "discard_current"


class Precision(StrEnum):
    FP16 = "fp16"
    BF16 = "bf16"
    FP32 = "fp32"


class GpuVendor(StrEnum):
    NVIDIA = "nvidia"
    AMD = "amd"
    CPU = "cpu"


class RuntimeFlavour(StrEnum):
    CPU = "cpu"
    CUDA = "cuda"
    ROCM = "rocm"


class LlmProviderKind(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class LlmPreset(StrEnum):
    OLLAMA = "ollama"
    LMSTUDIO = "lmstudio"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    XAI = "xai"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    GENERIC = "generic"


#: Per-task model routing (LM-04, PLAN.md §5.5).
class TaskKey(StrEnum):
    CLASSIFY_CHEAP = "classify_cheap"
    DIALOGUE_HARD = "dialogue_hard"
    PRONOUNCE = "pronounce"


class EpubVariant(StrEnum):
    READER = "reader"
    CLEAN = "clean"


class MuxMode(StrEnum):
    FULL = "full"
    PARTIAL = "partial"


class EventType(StrEnum):
    """WebSocket event types (OPENAPI_SKETCH.md §11)."""

    JOB_STATE = "job.state"
    JOB_PROGRESS = "job.progress"
    JOB_CHUNK = "job.chunk"
    JOB_WARNING = "job.warning"
    JOB_LOG = "job.log"
    GPU_SAMPLE = "gpu.sample"
    SUGGESTION_CREATED = "suggestion.created"
    PREP_PROGRESS = "prep.progress"
    DOWNLOAD_PROGRESS = "download.progress"
    RUNTIME_PROGRESS = "runtime.progress"
    PROJECT_REVISION = "project.revision"
    ERROR = "error"


TERMINAL_JOB_STATES: frozenset[JobState] = frozenset(
    {JobState.DONE, JobState.FAILED, JobState.CANCELLED}
)

ACTIVE_JOB_STATES: frozenset[JobState] = frozenset(
    {JobState.QUEUED, JobState.RUNNING, JobState.PAUSED, JobState.MUXING}
)
