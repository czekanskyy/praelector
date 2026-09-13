# SPDX-License-Identifier: Apache-2.0
"""SQLAlchemy schema and table definitions matching DATA_MODEL.md."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

# 1. Project table
project_table = Table(
    "project",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("schema_version", Integer, nullable=False, default=1),
    Column("source_format", String, nullable=True),
    Column("source_original_rel", String, nullable=True),
    Column("working_epub_rel", String, nullable=True),
    Column("converter", String, nullable=True),
    Column("book_language", String, nullable=True),
    Column("spoken_language", String, nullable=False, default="pl"),
    Column("voice_mode", String, nullable=False),
    Column("backend_id", String, nullable=True),
    Column("backend_params_json", Text, nullable=True),
    Column("precision", String, default="fp16"),
    Column("cloud_llm_enabled", Integer, nullable=False, default=0),
    Column("current_revision", Integer, nullable=False, default=0),
    CheckConstraint(
        "voice_mode IN ('single','narrator_dialogue','narrator_male_female')",
        name="ck_project_voice_mode",
    ),
)

# 2. Revision table
revision_table = Table(
    "revision",
    metadata,
    Column("n", Integer, primary_key=True),
    Column("created_at", String, nullable=False),
    Column("label", String, nullable=False),
    Column("batch_id", String, nullable=True),
    Column("reverted", Integer, nullable=False, default=0),
)

# 3. Chapter table
chapter_table = Table(
    "chapter",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, ForeignKey("project.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("title", String, nullable=False),
    Column("included", Integer, nullable=False, default=1),
    Column("source_href", String, nullable=True),
    Column("spine_index", Integer, nullable=True),
    Column("char_count", Integer, nullable=False, default=0),
    UniqueConstraint("project_id", "ordinal", name="uq_chapter_ordinal"),
)

# 4. Block table
block_table = Table(
    "block",
    metadata,
    Column("id", String, nullable=False),
    Column("version_id", String, primary_key=True),
    Column("chapter_id", String, ForeignKey("chapter.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("kind", String, nullable=False),
    Column("heading_level", Integer, nullable=True),
    Column("text", Text, nullable=False),
    Column("source_ref_json", Text, nullable=True),
    Column("valid_from_revision", Integer, nullable=False),
    Column("valid_to_revision", Integer, nullable=True),
    Index("ix_block_current", "chapter_id", "valid_to_revision", "ordinal"),
    Index("ix_block_id", "id", "valid_from_revision"),
)

# 5. Span table
span_table = Table(
    "span",
    metadata,
    Column("id", String, nullable=False),
    Column("version_id", String, primary_key=True),
    Column("block_id", String, nullable=False),
    Column("start", Integer, nullable=False),
    Column("end", Integer, nullable=False),
    Column("kind", String, nullable=False),
    Column("gender", String, nullable=True),
    Column("gender_confidence", Float, nullable=True),
    Column("gender_detector", String, nullable=True),
    Column("speaker_id", String, nullable=True),
    Column("spoken", Text, nullable=True),
    Column("pause_ms", Integer, nullable=True),
    Column("origin", String, nullable=False),
    Column("orphaned", Integer, nullable=False, default=0),
    Column("valid_from_revision", Integer, nullable=False),
    Column("valid_to_revision", Integer, nullable=True),
    CheckConstraint(
        "kind IN ('narration','dialogue','pronunciation','pause','skip')", name="ck_span_kind"
    ),
    CheckConstraint(
        "gender IS NULL OR gender IN ('male','female','unknown')", name="ck_span_gender"
    ),
    CheckConstraint("start >= 0 AND end >= start", name="ck_span_bounds"),
    Index("ix_span_current", "block_id", "valid_to_revision", "start"),
)

# 6. Suggestion table
suggestion_table = Table(
    "suggestion",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, ForeignKey("project.id"), nullable=False),
    Column("chapter_id", String, ForeignKey("chapter.id"), nullable=False),
    Column("block_id", String, nullable=False),
    Column("start", Integer, nullable=False),
    Column("end", Integer, nullable=False),
    Column("category", String, nullable=False),
    Column("original", Text, nullable=False),
    Column("proposed", Text, nullable=True),
    Column("payload_json", Text, nullable=True),
    Column("rationale", Text, nullable=True),
    Column("confidence", Float, nullable=False),
    Column("detector", String, nullable=False),
    Column("status", String, nullable=False, default="pending"),
    Column("error_code", String, nullable=True),
    Column("llm_profile_id", String, nullable=True),
    Column("prompt_version", String, nullable=True),
    Column("batch_id", String, nullable=True),
    Column("base_revision", Integer, nullable=False),
    Column("applied_in_revision", Integer, nullable=True),
    Column("created_at", String, nullable=False),
    CheckConstraint(
        "category IN ('foreign_word','acronym','toponym','numeral','ordinal_heading',"
        "'dialogue_split','speaker_gender','conversion_artifact','dict_hit')",
        name="ck_sug_category",
    ),
    CheckConstraint(
        "status IN ('pending','accepted','rejected','edited','failed')", name="ck_sug_status"
    ),
    CheckConstraint("detector IN ('heuristic','llm','dict')", name="ck_sug_detector"),
    Index("ix_sug_review", "project_id", "status", "category", "chapter_id"),
    Index("ix_sug_block", "block_id", "start"),
)

# 7. Voice Profile table
voice_profile_table = Table(
    "voice_profile",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, ForeignKey("project.id"), nullable=False),
    Column("name", String, nullable=False),
    Column("slot", String, nullable=True),
    Column("source_filename", String, nullable=False),
    Column("source_sha256", String, nullable=False),
    Column("ref_text", Text, nullable=False),
    Column("processed_rel", String, nullable=False),
    Column("sample_rate", Integer, nullable=False),
    Column("channels", Integer, nullable=False, default=1),
    Column("duration_s", Float, nullable=False),
    Column("measured_lufs", Float, nullable=True),
    Column("target_lufs", Float, nullable=False, default=-23.0),
    Column("trim_applied", Integer, nullable=False, default=1),
    Column("content_hash", String, nullable=False),
    Column("chain_version", String, nullable=False),
    Column("created_at", String, nullable=False),
    CheckConstraint(
        "slot IS NULL OR slot IN ('narrator','dialogue','male','female')",
        name="ck_voice_profile_slot",
    ),
)

# 8. Job table
job_table = Table(
    "job",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, ForeignKey("project.id"), nullable=False),
    Column("kind", String, nullable=False),
    Column("state", String, nullable=False),
    Column("stage", String, nullable=True),
    Column("paused_reason", String, nullable=True),
    Column("revision", Integer, nullable=False),
    Column("options_json", Text, nullable=False),
    Column("counts_json", Text, nullable=False),
    Column("metrics_json", Text, nullable=True),
    Column("warnings_json", Text, nullable=True),
    Column("error_json", Text, nullable=True),
    Column("last_seq", Integer, nullable=False, default=0),
    Column("created_at", String, nullable=False),
    Column("started_at", String, nullable=True),
    Column("finished_at", String, nullable=True),
    CheckConstraint("kind IN ('prep','record')", name="ck_job_kind"),
    CheckConstraint(
        "state IN ('queued','running','paused','muxing','done','failed','cancelled')",
        name="ck_job_state",
    ),
)

# 9. Plan Item table
plan_item_table = Table(
    "plan_item",
    metadata,
    Column("job_id", String, ForeignKey("job.id"), primary_key=True),
    Column("ordinal", Integer, primary_key=True),
    Column("chapter_id", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("voice_slot", String, nullable=True),
    Column("render_key", String, nullable=True),
    Column("chars", Integer, nullable=False, default=0),
    Column("pause_ms", Integer, nullable=True),
    Index("ix_plan_rk", "render_key"),
)

# 10. Chunk table
chunk_table = Table(
    "chunk",
    metadata,
    Column("render_key", String, primary_key=True),
    Column("project_id", String, ForeignKey("project.id"), nullable=False),
    Column("text_hash", String, nullable=False),
    Column("voice_slot", String, nullable=False),
    Column("voice_profile_id", String, nullable=True),
    Column("backend_id", String, nullable=False),
    Column("adapter_version", String, nullable=False),
    Column("model_revision", String, nullable=True),
    Column("params_hash", String, nullable=False),
    Column("sample_rate", Integer, nullable=False),
    Column("duration_s", Float, nullable=False),
    Column("bytes", Integer, nullable=False),
    Column("rel_path", String, nullable=False),
    Column("created_at", String, nullable=False),
    Index("ix_chunk_text", "text_hash", "voice_slot"),
)

# 11. GPU Budget table
gpu_budget_table = Table(
    "gpu_budget",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("job_id", String, ForeignKey("job.id"), nullable=True),
    Column("computed_at", String, nullable=False),
    Column("device_json", Text, nullable=False),
    Column("backend_id", String, nullable=False),
    Column("precision", String, nullable=False),
    Column("reserve_mib", Integer, nullable=False),
    Column("peak_worker_mib", Integer, nullable=False),
    Column("peak_source", String, nullable=False),
    Column("effective_workers", Integer, nullable=False),
    Column("admissions_paused", Integer, nullable=False, default=0),
)

# 12. VRAM table
vram_table = Table(
    "vram_table",
    metadata,
    Column("backend_id", String, primary_key=True),
    Column("precision", String, primary_key=True),
    Column("vendor", String, primary_key=True),
    Column("peak_mib", Integer, nullable=False),
    Column("measured", Integer, nullable=False, default=0),
    Column("user_override", Integer, nullable=False, default=0),
    Column("samples", Integer, nullable=False, default=0),
    Column("updated_at", String, nullable=False),
)

# 13. Metadata table
metadata_table = Table(
    "metadata",
    metadata,
    Column("project_id", String, ForeignKey("project.id"), primary_key=True),
    Column("title", String, nullable=False),
    Column("authors_json", Text, nullable=False, default="[]"),
    Column("narrator", String, nullable=True),
    Column("year", Integer, nullable=True),
    Column("description", Text, nullable=True),
    Column("language", String, nullable=True),
    Column("publisher", String, nullable=True),
    Column("isbn", String, nullable=True),
    Column("series", String, nullable=True),
    Column("series_index", Float, nullable=True),
    Column("genre", String, nullable=False, default="Audiobook"),
    Column("cover_rel", String, nullable=True),
)

# 14. Lexicon Entry table
lexicon_entry_table = Table(
    "lexicon_entry",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, ForeignKey("project.id"), nullable=True),
    Column("pattern", String, nullable=False),
    Column("is_regex", Integer, nullable=False, default=0),
    Column("spoken", String, nullable=False),
    Column("language", String, nullable=False, default="pl"),
    Column("category", String, nullable=False, default="dict_hit"),
    Column("auto_apply", Integer, nullable=False, default=0),
    Column("case_sensitive", Integer, nullable=False, default=0),
    Column("priority", Integer, nullable=False, default=100),
    Column("created_at", String, nullable=False),
    UniqueConstraint("project_id", "pattern", "is_regex", name="uq_lexicon_pattern"),
)
