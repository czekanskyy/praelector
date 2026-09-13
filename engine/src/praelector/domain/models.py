# SPDX-License-Identifier: Apache-2.0
"""Pydantic entities and API contract models for Praelector."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from praelector.domain.enums import (
    SourceFormat,
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
