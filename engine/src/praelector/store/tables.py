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

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from praelector.domain.enums import VoiceMode

_VOICE_MODES = ", ".join(f"'{mode}'" for mode in VoiceMode)


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
