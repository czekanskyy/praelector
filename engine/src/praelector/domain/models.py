# SPDX-License-Identifier: Apache-2.0
"""Pydantic entities and API contract models for Praelector."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from praelector.domain.enums import (
    BlockKind,
    DetectorKind,
    Gender,
    GenderDetector,
    SourceFormat,
    SpanKind,
    SpanOrigin,
    SuggestionCategory,
    SuggestionStatus,
    VoiceMode,
)


class ProjectManifest(BaseModel):
    """Manifest stored at <project_dir>/project.json for quick listing."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1)
    id: str
    name: str
    created_at: str
    updated_at: str
    voice_mode: VoiceMode = VoiceMode.NARRATOR_MALE_FEMALE
    backend_id: str = "omnivoice"
    spoken_language: str = "pl"
    current_revision: int = 0


class ProjectCreate(BaseModel):
    """Payload for creating a new project."""

    name: str = Field(min_length=1, max_length=255)
    dir: str | None = None
    voice_mode: VoiceMode = VoiceMode.NARRATOR_MALE_FEMALE
    spoken_language: str = "pl"
    backend_id: str = "omnivoice"


class ProjectUpdate(BaseModel):
    """Payload for updating project metadata and settings."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    voice_mode: VoiceMode | None = None
    backend_id: str | None = None
    spoken_language: str | None = None
    cloud_llm_enabled: bool | None = None


class ProjectCounts(BaseModel):
    """Aggregated entity counts for a project."""

    chapters: int = 0
    blocks: int = 0
    spans: int = 0
    suggestions_pending: int = 0
    chunks_done: int = 0
    chunks_total: int = 0


class ProjectResponse(BaseModel):
    """Detailed project representation returned by API."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    path: str
    created_at: str
    updated_at: str
    schema_version: int = 1
    source_format: SourceFormat | None = None
    source_original_rel: str | None = None
    working_epub_rel: str | None = None
    converter: str | None = None
    book_language: str | None = None
    spoken_language: str = "pl"
    voice_mode: VoiceMode = VoiceMode.NARRATOR_MALE_FEMALE
    backend_id: str = "omnivoice"
    backend_params_json: str | None = None
    precision: str = "fp16"
    cloud_llm_enabled: bool = False
    current_revision: int = 0
    active_job_id: str | None = None
    is_open: bool = False
    counts: ProjectCounts = Field(default_factory=ProjectCounts)


class ProjectSummary(BaseModel):
    """Summary item for the Library project list."""

    id: str
    name: str
    path: str
    created_at: str
    updated_at: str
    spoken_language: str
    voice_mode: VoiceMode
    backend_id: str
    current_revision: int
    is_open: bool = False


class ProjectOpenResponse(BaseModel):
    """Response returned when opening a project."""

    project: ProjectResponse
    status: str = "opened"


class ProjectStats(BaseModel):
    """Detailed statistics for the project stats endpoint."""

    project_id: str
    chapter_count: int = 0
    block_count: int = 0
    word_count: int = 0
    char_count: int = 0
    suggestions_by_category: dict[str, int] = Field(default_factory=dict)
    suggestions_by_status: dict[str, int] = Field(default_factory=dict)


class SecretField(BaseModel):
    """Masked secret field preventing credentials from being echoed in responses (LM-03)."""

    set: bool = False


class LlmProfile(BaseModel):
    """Configured LLM provider profile for text assistance."""

    id: str
    name: str | None = None
    kind: str = "openai_compatible"
    preset: str = "ollama"
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen2.5:14b-instruct"
    is_cloud: bool = False
    supports_json_schema: bool = True
    timeout_s: int = 120
    max_tokens: int = 1024
    api_key: SecretField = Field(default_factory=SecretField)


class LlmProfileWrite(BaseModel):
    """Payload for creating or updating an LLM profile with optional secret value."""

    id: str
    name: str | None = None
    kind: str = "openai_compatible"
    preset: str = "ollama"
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen2.5:14b-instruct"
    is_cloud: bool = False
    supports_json_schema: bool = True
    timeout_s: int = 120
    max_tokens: int = 1024
    api_key: str | None = None


class TaskRouting(BaseModel):
    """Task-to-profile routing mapping."""

    classify_cheap: str = "llm_local_ollama"
    dialogue_hard: str = "llm_local_ollama"
    pronounce: str = "llm_local_ollama"


class GpuPolicy(BaseModel):
    """GPU admission control and resource policy."""

    device_index: int = 0
    reserve_mib: int | None = None
    peak_worker_mib_overrides: dict[str, int] = Field(default_factory=dict)
    worker_cap: int = 4
    allow_cpu: bool = False


class AudioSettings(BaseModel):
    """Default output and audio normalization parameters."""

    output_sample_rate: int = 44100
    output_bitrate_kbps: int = 64
    target_lufs: float = -23.0
    inter_sentence_silence_ms: int = 300
    crossfade_ms: int = 0


class AppSettings(BaseModel):
    """Application-level configuration tree."""

    projects_dir: str
    data_dir: str
    config_dir: str
    log_level: str = "INFO"
    llm_profiles: list[LlmProfile] = Field(default_factory=list)
    task_routing: TaskRouting = Field(default_factory=TaskRouting)
    gpu_policy: GpuPolicy = Field(default_factory=GpuPolicy)
    audio: AudioSettings = Field(default_factory=AudioSettings)


class SettingsUpdate(BaseModel):
    """Partial update payload for settings."""

    projects_dir: str | None = None
    log_level: str | None = None
    task_routing: TaskRouting | None = None
    gpu_policy: GpuPolicy | None = None
    audio: AudioSettings | None = None


class ToolProbe(BaseModel):
    """Probe result for external CLI utilities (ffmpeg, calibre)."""

    installed: bool
    path: str | None = None
    version: str | None = None
    error: str | None = None
    filters_ok: bool | None = None


class KeyringProbe(BaseModel):
    """Keyring availability probe result."""

    backend: str
    available: bool


class RuntimeProbe(BaseModel):
    """TTS worker runtime availability probe result."""

    flavour: str
    ready: bool


class CapabilitiesResponse(BaseModel):
    """System capabilities and probe findings."""

    ffmpeg: ToolProbe
    calibre: ToolProbe
    keyring: KeyringProbe
    runtime: RuntimeProbe
    system_info: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Ingest Models (EB-01 .. EB-08)
# ---------------------------------------------------------------------------


class DrmStatus(BaseModel):
    """DRM inspection findings."""

    detected: bool = False
    reason: str | None = None
    file: str | None = None


class MetadataPreview(BaseModel):
    """Metadata extracted during ebook probe."""

    title: str
    authors: list[str] = Field(default_factory=list)
    language: str = "pl"
    chapter_count: int = 0
    total_chars: int = 0
    cover_detected: bool = False


class IngestProbeRequest(BaseModel):
    """Payload for probing a book file before import."""

    path: str


class IngestProbeResponse(BaseModel):
    """Probe result returned to the user before confirming ingest."""

    format: SourceFormat
    needs_conversion: bool
    drm: DrmStatus = Field(default_factory=DrmStatus)
    has_text_layer: bool = True
    metadata_preview: MetadataPreview | None = None


class IngestConvertOptions(BaseModel):
    """Conversion settings for formats requiring Calibre."""

    enabled: bool = False
    engine: str = "calibre"


class IngestRequest(BaseModel):
    """Payload to import an ebook file into an open project."""

    path: str
    convert: IngestConvertOptions = Field(default_factory=IngestConvertOptions)


class IngestResponse(BaseModel):
    """Result of importing an ebook into a project."""

    project_id: str
    format: SourceFormat
    chapter_count: int
    total_chars: int
    working_epub_path: str


class ProjectSourceResponse(BaseModel):
    """Information about the source and working documents in the project."""

    original_path: str | None = None
    working_epub_path: str | None = None
    imported_at: str | None = None
    converter: str | None = None


# ---------------------------------------------------------------------------
# Chapters, Blocks, Spans Models (ED-01 .. ED-09)
# ---------------------------------------------------------------------------


class ChapterResponse(BaseModel):
    """Chapter tree item returned by the API."""

    id: str
    ordinal: int
    title: str
    included: bool = True
    block_count: int = 0
    char_count: int = 0
    est_audio_s: float = 0.0


class ChapterUpdate(BaseModel):
    """Payload for renaming or including/excluding a chapter."""

    title: str | None = None
    included: bool | None = None


class ChapterReorderRequest(BaseModel):
    """Payload for updating chapter ordinal sequence."""

    order: list[str]


class ChapterSplitRequest(BaseModel):
    """Payload for splitting a chapter at a given block and offset."""

    block_id: str
    offset: int = 0


class ChapterMergeRequest(BaseModel):
    """Payload for merging multiple chapters in sequence."""

    ids: list[str]


class BlockResponse(BaseModel):
    """A semantic text block in a chapter."""

    id: str
    ordinal: int
    kind: BlockKind
    heading_level: int | None = None
    text: str
    source_ref_json: str | None = None


class ChapterTextResponse(BaseModel):
    """Chapter content for editing or reading."""

    view: str = "display"
    blocks: list[BlockResponse] = Field(default_factory=list)
    text: str


class ChapterTextUpdate(BaseModel):
    """Payload for updating a chapter's plain text."""

    text: str
    base_revision: int


class ChapterTextUpdateResponse(BaseModel):
    """Result of chapter plain text update."""

    revision: int
    orphaned_span_ids: list[str] = Field(default_factory=list)


class SpanResponse(BaseModel):
    """A span annotation within a block."""

    id: str
    block_id: str
    start: int
    end: int
    kind: SpanKind
    gender: Gender | None = None
    gender_confidence: float | None = None
    gender_detector: GenderDetector | None = None
    speaker_id: str | None = None
    spoken: str | None = None
    pause_ms: int | None = None
    origin: SpanOrigin
    orphaned: bool = False


class SpanCreate(BaseModel):
    """Payload for creating a manual span."""

    block_id: str
    start: int
    end: int
    kind: SpanKind
    gender: Gender | None = None
    speaker_id: str | None = None
    spoken: str | None = None
    pause_ms: int | None = None


class SpanUpdate(BaseModel):
    """Payload for modifying an existing span."""

    kind: SpanKind | None = None
    gender: Gender | None = None
    speaker_id: str | None = None
    spoken: str | None = None
    pause_ms: int | None = None


# ---------------------------------------------------------------------------
# Search and Replace Models (ED-05)
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Query payload for text search."""

    query: str
    regex: bool = False
    case_sensitive: bool = False
    scope: str = "book"
    chapter_id: str | None = None


class SearchHit(BaseModel):
    """A search match location and snippet."""

    chapter_id: str
    chapter_title: str
    block_id: str
    start: int
    end: int
    text_match: str
    context: str


class SearchResponse(BaseModel):
    """Results returned by search endpoint."""

    count: int
    hits: list[SearchHit] = Field(default_factory=list)


class ReplaceRequest(BaseModel):
    """Query payload for search and replace with dry-run support."""

    query: str
    replacement: str
    regex: bool = False
    case_sensitive: bool = False
    scope: str = "book"
    chapter_id: str | None = None
    dry_run: bool = True


class ReplacePreview(BaseModel):
    """Preview of a single block replacement."""

    chapter_id: str
    block_id: str
    original: str
    proposed: str


class ReplaceResponse(BaseModel):
    """Result of search and replace operation."""

    count: int
    previews: list[ReplacePreview] = Field(default_factory=list)
    revision: int | None = None


# ---------------------------------------------------------------------------
# Suggestion Models (AI-04, AI-06)
# ---------------------------------------------------------------------------


class SuggestionRange(BaseModel):
    """Character offsets for a suggestion within its parent block."""

    start: int
    end: int


class SuggestionResponse(BaseModel):
    """A suggestion item surfaced in the review queue."""

    id: str
    project_id: str
    chapter_id: str
    block_id: str
    start: int
    end: int
    range: SuggestionRange | None = None
    category: SuggestionCategory
    original: str
    proposed: str | None = None
    payload_json: str | None = None
    rationale: str | None = None
    confidence: float
    detector: DetectorKind
    status: SuggestionStatus = SuggestionStatus.PENDING
    error_code: str | None = None
    llm_profile_id: str | None = None
    prompt_version: str | None = None
    batch_id: str | None = None
    base_revision: int
    applied_in_revision: int | None = None
    created_at: str


class SuggestionCreate(BaseModel):
    """Payload for creating a suggestion."""

    project_id: str
    chapter_id: str
    block_id: str
    start: int
    end: int
    category: SuggestionCategory
    original: str
    proposed: str | None = None
    payload_json: str | None = None
    rationale: str | None = None
    confidence: float
    detector: DetectorKind = DetectorKind.HEURISTIC
    status: SuggestionStatus = SuggestionStatus.PENDING
    error_code: str | None = None
    llm_profile_id: str | None = None
    prompt_version: str | None = None
    batch_id: str | None = None
    base_revision: int = 0


class SuggestionUpdate(BaseModel):
    """Payload for patching a suggestion's status or proposed text."""

    status: SuggestionStatus
    proposed: str | None = None


class SuggestionBulkAction(BaseModel):
    """Payload for bulk operations on suggestions."""

    category: SuggestionCategory | None = None
    status: SuggestionStatus | None = None
    chapter_id: str | None = None
    detector: DetectorKind | None = None
    action: str  # "accept" | "reject"
    limit: int | None = None


class SuggestionBulkResponse(BaseModel):
    """Result of bulk suggestion action."""

    batch_id: str
    affected: int


# ---------------------------------------------------------------------------
# Lexicon Models (AI-09)
# ---------------------------------------------------------------------------


class LexiconEntryResponse(BaseModel):
    """A dictionary entry in the pronunciation lexicon."""

    id: str
    project_id: str | None = None
    pattern: str
    is_regex: bool = False
    spoken: str
    language: str = "pl"
    category: str = "dict_hit"
    auto_apply: bool = False
    case_sensitive: bool = False
    priority: int = 100
    created_at: str


class LexiconEntryCreate(BaseModel):
    """Payload to create a lexicon rule."""

    pattern: str = Field(min_length=1)
    is_regex: bool = False
    spoken: str = Field(min_length=1)
    language: str = "pl"
    category: str = "dict_hit"
    auto_apply: bool = False
    case_sensitive: bool = False
    priority: int = 100


class LexiconEntryUpdate(BaseModel):
    """Payload to update an existing lexicon rule."""

    pattern: str | None = None
    is_regex: bool | None = None
    spoken: str | None = None
    language: str | None = None
    category: str | None = None
    auto_apply: bool | None = None
    case_sensitive: bool | None = None
    priority: int | None = None


# ---------------------------------------------------------------------------
# LLM Profile Management Models (LM-01, LM-02)
# ---------------------------------------------------------------------------


class LlmTestResponse(BaseModel):
    """Result of testing an LLM provider connection."""

    ok: bool
    latency_ms: float = 0.0
    models: list[str] = Field(default_factory=list)
    error: str | None = None


class LlmProfileCreate(BaseModel):
    """Payload to create an LLM profile."""

    id: str | None = None
    name: str | None = None
    kind: str = "openai_compatible"
    preset: str = "ollama"
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = "qwen2.5:14b-instruct"
    is_cloud: bool = False
    supports_json_schema: bool = True
    timeout_s: int = 120
    max_tokens: int = 1024
    api_key: str | None = None


class LlmProfilePatch(BaseModel):
    """Payload to partially update an LLM profile."""

    name: str | None = None
    kind: str | None = None
    preset: str | None = None
    base_url: str | None = None
    model: str | None = None
    is_cloud: bool | None = None
    supports_json_schema: bool | None = None
    timeout_s: int | None = None
    max_tokens: int | None = None
    api_key: str | None = None


# ---------------------------------------------------------------------------
# Job Models (JB-01..JB-07, AI-01)
# ---------------------------------------------------------------------------


class JobCounts(BaseModel):
    """Progress counters for background jobs."""

    chapters_total: int = 0
    chapters_done: int = 0
    blocks_total: int = 0
    blocks_done: int = 0
    chunks_total: int = 0
    chunks_done: int = 0
    chunks_reused: int = 0
    chunks_failed: int = 0
    suggestions_emitted: int = 0


class JobMetrics(BaseModel):
    """Performance and timing metrics for background jobs."""

    elapsed_s: float = 0.0
    eta_s: float | None = None
    chars_per_audio_s: float | None = None
    rtf_smoothed: float | None = None


class JobCreateRequest(BaseModel):
    """Payload to launch a background job."""

    kind: str = "prep"
    options: dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    """Detailed job representation returned by API."""

    id: str
    project_id: str
    kind: str
    state: str
    stage: str | None = None
    paused_reason: str | None = None
    revision: int = 0
    options: dict[str, Any] = Field(default_factory=dict)
    counts: JobCounts = Field(default_factory=JobCounts)
    metrics: JobMetrics = Field(default_factory=JobMetrics)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
