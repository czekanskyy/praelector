# SPDX-License-Identifier: Apache-2.0
"""SQLAlchemy tables. ``docs/plan/DATA_MODEL.md`` is normative for every shape.

Timestamps are RFC 3339 UTC **strings**, not a SQL datetime type: the same values
are written into ``project.json``, ``job.json`` and chunk sidecars, and keeping
one representation avoids a rounding/format mismatch between the database and the
files that must survive a crash (D-02).

Only the tables this milestone uses are declared here. Each later PR adds its own
Alembic migration together with the code that reads and writes it, so the schema
never runs ahead of the features.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from praelector.domain.enums import SuggestionCategory, VoiceMode

_VOICE_MODES = ", ".join(f"'{mode}'" for mode in VoiceMode)
_SUGGESTION_CATEGORIES = ", ".join(f"'{item.value}'" for item in SuggestionCategory)


class Base(DeclarativeBase):
    """Metadata for every project database."""


def to_db_time(value: datetime) -> str:
    """RFC 3339 UTC with second precision and a ``Z`` suffix."""
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def from_db_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ProjectRow(Base):
    """One row per project (DATA_MODEL.md §2)."""

    __tablename__ = "project"
    __table_args__ = (
        CheckConstraint(f"voice_mode IN ({_VOICE_MODES})", name="ck_project_voice_mode"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Source (EB-05, EB-06). Populated by ingest; null until a book is imported.
    source_format: Mapped[str | None] = mapped_column(String)
    source_original_rel: Mapped[str | None] = mapped_column(String)
    working_epub_rel: Mapped[str | None] = mapped_column(String)
    converter: Mapped[str | None] = mapped_column(String)
    book_language: Mapped[str | None] = mapped_column(String)

    # Lector settings.
    spoken_language: Mapped[str] = mapped_column(String, nullable=False, default="pl")
    voice_mode: Mapped[str] = mapped_column(String, nullable=False)
    backend_id: Mapped[str | None] = mapped_column(String)
    backend_params_json: Mapped[str | None] = mapped_column(String)
    precision: Mapped[str | None] = mapped_column(String, default="fp16")

    #: Cloud LLM calls need an explicit per-project toggle (LM-05, NF-02).
    cloud_llm_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RevisionRow(Base):
    """A book revision (AI-07). ``n = 0`` is the as-ingested state."""

    __tablename__ = "revision"

    n: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String)
    reverted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ChapterRow(Base):
    """One chapter in narration order (DATA_MODEL.md §3).

    ``ordinal < 0`` is a chapter that merge removed from the tree. The row stays
    so block versions can keep their foreign key (0002_chapters).
    """

    __tablename__ = "chapter"
    __table_args__ = (
        UniqueConstraint("project_id", "ordinal", name="uq_chapter_ordinal"),
        Index("ix_chapter_project", "project_id", "ordinal"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_href: Mapped[str | None] = mapped_column(String)
    spine_index: Mapped[int | None] = mapped_column(Integer)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class BlockRow(Base):
    """One version of a block (DATA_MODEL.md §4, D-08).

    ``id`` is stable across edits. ``version_id`` is the row. A current row has
    ``valid_to_revision`` NULL; closing it sets that column to the revision that
    replaced it.
    """

    __tablename__ = "block"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('paragraph','heading','blockquote','list_item','caption')",
            name="ck_block_kind",
        ),
        CheckConstraint(
            "heading_level IS NULL OR (heading_level >= 1 AND heading_level <= 6)",
            name="ck_block_heading_level",
        ),
        Index("ix_block_current", "chapter_id", "valid_to_revision", "ordinal"),
        Index("ix_block_id", "id", "valid_from_revision"),
    )

    id: Mapped[str] = mapped_column(String, nullable=False)
    version_id: Mapped[str] = mapped_column(String, primary_key=True)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapter.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    heading_level: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String, nullable=False)
    source_ref_json: Mapped[str | None] = mapped_column(String)
    valid_from_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_to_revision: Mapped[int | None] = mapped_column(Integer)


class SpanRow(Base):
    """One version of a span (DATA_MODEL.md §5). Current rows have a null ``valid_to``."""

    __tablename__ = "span"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('narration','dialogue','pronunciation','pause','skip')",
            name="ck_span_kind",
        ),
        CheckConstraint(
            "gender IS NULL OR gender IN ('male','female','unknown')",
            name="ck_span_gender",
        ),
        CheckConstraint("start >= 0 AND end >= start", name="ck_span_range"),
        Index("ix_span_current", "block_id", "valid_to_revision", "start"),
    )

    id: Mapped[str] = mapped_column(String, nullable=False)
    version_id: Mapped[str] = mapped_column(String, primary_key=True)
    block_id: Mapped[str] = mapped_column(String, nullable=False)
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    gender: Mapped[str | None] = mapped_column(String)
    gender_confidence: Mapped[float | None] = mapped_column(Float)
    speaker_id: Mapped[str | None] = mapped_column(String)
    spoken: Mapped[str | None] = mapped_column(String)
    pause_ms: Mapped[int | None] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    orphaned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_to_revision: Mapped[int | None] = mapped_column(Integer)


class VoiceProfileRow(Base):
    """One reference sample (DATA_MODEL.md §7). A null slot is unassigned."""

    __tablename__ = "voice_profile"
    __table_args__ = (
        CheckConstraint(
            "slot IS NULL OR slot IN ('narrator','dialogue','male','female')",
            name="ck_voice_profile_slot",
        ),
        Index(
            "ux_voice_slot",
            "project_id",
            "slot",
            unique=True,
            sqlite_where=text("slot IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slot: Mapped[str | None] = mapped_column(String)
    source_filename: Mapped[str] = mapped_column(String, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String, nullable=False)
    ref_text: Mapped[str] = mapped_column(String, nullable=False)
    processed_rel: Mapped[str] = mapped_column(String, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    measured_lufs: Mapped[float | None] = mapped_column(Float)
    target_lufs: Mapped[float] = mapped_column(Float, nullable=False, default=-23.0)
    trim_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    chain_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class LexiconEntryRow(Base):
    """One project pronunciation rule (DATA_MODEL.md §12).

    Global rules live in a separate database. This table is project-scoped,
    so ``project_id`` is required.
    """

    __tablename__ = "lexicon_entry"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "pattern",
            "is_regex",
            name="uq_lexicon_pattern",
        ),
        CheckConstraint(
            f"category IN ({_SUGGESTION_CATEGORIES})",
            name="ck_lexicon_category",
        ),
        Index("ix_lexicon_project", "project_id", "priority"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id"), nullable=False)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    is_regex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spoken: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="pl")
    category: Mapped[str] = mapped_column(String, nullable=False, default="dict_hit")
    auto_apply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class ChunkRow(Base):
    """One reusable chunk (DATA_MODEL.md §9). Rebuilt from sidecars on open."""

    __tablename__ = "chunk"

    render_key: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("project.id"), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    rel_path: Mapped[str] = mapped_column(String, nullable=False)
