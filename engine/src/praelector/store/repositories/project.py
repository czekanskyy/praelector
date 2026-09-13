# SPDX-License-Identifier: Apache-2.0
"""Project repository for SQLite storage operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from praelector.domain.models import ProjectCounts, ProjectManifest, ProjectStats
from praelector.store.schema import (
    block_table,
    chapter_table,
    chunk_table,
    project_table,
    revision_table,
    span_table,
    suggestion_table,
)


class ProjectRepository:
    """Data access layer for Project entities in project.db."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, manifest: ProjectManifest, session: Session | None = None) -> None:
        """Insert project and initial baseline revision 0."""
        values = {
            "id": manifest.id,
            "name": manifest.name,
            "created_at": manifest.created_at,
            "updated_at": manifest.updated_at,
            "schema_version": manifest.schema_version,
            "spoken_language": manifest.spoken_language,
            "voice_mode": manifest.voice_mode.value,
            "backend_id": manifest.backend_id,
            "current_revision": manifest.current_revision,
            "cloud_llm_enabled": 0,
            "precision": "fp16",
        }

        def _do_insert(s: Session) -> None:
            s.execute(project_table.insert().values(**values))
            s.execute(
                revision_table.insert().values(
                    n=0,
                    created_at=manifest.created_at,
                    label="Project created",
                    reverted=0,
                )
            )

        if session is not None:
            _do_insert(session)
        else:
            with Session(self.engine) as s:
                _do_insert(s)
                s.commit()

    def get(self, project_id: str, session: Session | None = None) -> dict[str, Any] | None:
        """Fetch project record by ID."""
        stmt = select(project_table).where(project_table.c.id == project_id)

        if session is not None:
            row = session.execute(stmt).mappings().first()
            return dict(row) if row else None

        with Session(self.engine) as s:
            row = s.execute(stmt).mappings().first()
            return dict(row) if row else None

    def update(
        self,
        project_id: str,
        values: dict[str, Any],
        session: Session | None = None,
    ) -> None:
        """Update fields of a project record."""
        stmt = update(project_table).where(project_table.c.id == project_id).values(**values)

        if session is not None:
            session.execute(stmt)
        else:
            with Session(self.engine) as s:
                s.execute(stmt)
                s.commit()

    def get_counts(self, project_id: str, session: Session | None = None) -> ProjectCounts:
        """Aggregate entity counts for a project."""

        def _compute(s: Session) -> ProjectCounts:
            ch_count = (
                s.scalar(
                    select(func.count())
                    .select_from(chapter_table)
                    .where(chapter_table.c.project_id == project_id)
                )
                or 0
            )

            # Block count at current revision (valid_to_revision is null)
            blk_count = (
                s.scalar(
                    select(func.count())
                    .select_from(block_table)
                    .join(chapter_table, block_table.c.chapter_id == chapter_table.c.id)
                    .where(
                        chapter_table.c.project_id == project_id,
                        block_table.c.valid_to_revision.is_(None),
                    )
                )
                or 0
            )

            # Span count at current revision
            spn_count = (
                s.scalar(
                    select(func.count())
                    .select_from(span_table)
                    .join(block_table, span_table.c.block_id == block_table.c.id)
                    .join(chapter_table, block_table.c.chapter_id == chapter_table.c.id)
                    .where(
                        chapter_table.c.project_id == project_id,
                        span_table.c.valid_to_revision.is_(None),
                    )
                )
                or 0
            )

            sug_pending = (
                s.scalar(
                    select(func.count())
                    .select_from(suggestion_table)
                    .where(
                        suggestion_table.c.project_id == project_id,
                        suggestion_table.c.status == "pending",
                    )
                )
                or 0
            )

            chunks_done = (
                s.scalar(
                    select(func.count())
                    .select_from(chunk_table)
                    .where(chunk_table.c.project_id == project_id)
                )
                or 0
            )

            return ProjectCounts(
                chapters=ch_count,
                blocks=blk_count,
                spans=spn_count,
                suggestions_pending=sug_pending,
                chunks_done=chunks_done,
                chunks_total=chunks_done,
            )

        if session is not None:
            return _compute(session)

        with Session(self.engine) as s:
            return _compute(s)

    def get_stats(self, project_id: str, session: Session | None = None) -> ProjectStats:
        """Compute detailed chapter, block, character, and suggestion statistics."""

        def _compute(s: Session) -> ProjectStats:
            counts = self.get_counts(project_id, s)

            # Total characters from included chapters
            char_sum = (
                s.scalar(
                    select(func.sum(chapter_table.c.char_count)).where(
                        chapter_table.c.project_id == project_id
                    )
                )
                or 0
            )

            # Suggestions grouped by category
            cat_rows = s.execute(
                select(suggestion_table.c.category, func.count())
                .where(suggestion_table.c.project_id == project_id)
                .group_by(suggestion_table.c.category)
            ).all()
            by_category = {str(r[0]): int(r[1]) for r in cat_rows}

            # Suggestions grouped by status
            stat_rows = s.execute(
                select(suggestion_table.c.status, func.count())
                .where(suggestion_table.c.project_id == project_id)
                .group_by(suggestion_table.c.status)
            ).all()
            by_status = {str(r[0]): int(r[1]) for r in stat_rows}

            # Approximate word count (char_count / 6)
            words = char_sum // 6

            return ProjectStats(
                project_id=project_id,
                chapter_count=counts.chapters,
                block_count=counts.blocks,
                word_count=words,
                char_count=char_sum,
                suggestions_by_category=by_category,
                suggestions_by_status=by_status,
            )

        if session is not None:
            return _compute(session)

        with Session(self.engine) as s:
            return _compute(s)
