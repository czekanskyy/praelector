# SPDX-License-Identifier: Apache-2.0
"""Unit tests for SQLite database, WAL pragmas, and Alembic migrations."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from praelector.domain.enums import VoiceMode
from praelector.domain.models import ProjectManifest
from praelector.store.db import create_project_engine
from praelector.store.migrations.runner import apply_migrations
from praelector.store.repositories.project import ProjectRepository


def test_migrations_and_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "project.db"

    # Run Alembic migrations
    apply_migrations(db_path)
    assert db_path.is_file()

    engine = create_project_engine(db_path)
    try:
        with engine.connect() as conn:
            # Check WAL pragma
            mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert str(mode).lower() == "wal"

            # Check foreign keys
            fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
            assert fk == 1

            # Check table existence
            tables = (
                conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                .scalars()
                .all()
            )
            assert "project" in tables
            assert "revision" in tables
            assert "chapter" in tables
            assert "block" in tables
            assert "span" in tables
            assert "suggestion" in tables
            assert "voice_profile" in tables
            assert "job" in tables
            assert "plan_item" in tables
            assert "chunk" in tables
            assert "alembic_version" in tables
    finally:
        engine.dispose()


def test_project_repository_crud(tmp_path: Path) -> None:
    db_path = tmp_path / "project.db"
    apply_migrations(db_path)

    engine = create_project_engine(db_path)
    try:
        repo = ProjectRepository(engine)
        manifest = ProjectManifest(
            schema_version=1,
            id="prj_01TEST123",
            name="Repo Test Book",
            created_at="2026-09-13T12:00:00Z",
            updated_at="2026-09-13T12:00:00Z",
            voice_mode=VoiceMode.NARRATOR_MALE_FEMALE,
            backend_id="omnivoice",
            spoken_language="pl",
            current_revision=0,
        )

        repo.create(manifest)

        row = repo.get("prj_01TEST123")
        assert row is not None
        assert row["name"] == "Repo Test Book"
        assert row["voice_mode"] == "narrator_male_female"

        repo.update("prj_01TEST123", {"name": "Updated Title"})
        updated = repo.get("prj_01TEST123")
        assert updated is not None
        assert updated["name"] == "Updated Title"

        counts = repo.get_counts("prj_01TEST123")
        assert counts.chapters == 0
        assert counts.suggestions_pending == 0

        stats = repo.get_stats("prj_01TEST123")
        assert stats.chapter_count == 0
    finally:
        engine.dispose()
