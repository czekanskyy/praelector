# SPDX-License-Identifier: Apache-2.0
"""Lexicon repository for global and project-level pronunciation rules (AI-09)."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Engine, create_engine, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from praelector.domain.ids import LEXICON_PREFIX, generate_id
from praelector.domain.models import (
    LexiconEntryCreate,
    LexiconEntryResponse,
    LexiconEntryUpdate,
)
from praelector.store.schema import lexicon_entry_table


class LexiconRepository:
    """Manages global and project-level pronunciation lexicon entries."""

    def __init__(
        self,
        config_dir: str | Path,
        project_engine: Engine | None = None,
    ) -> None:
        self.config_dir = Path(config_dir)
        self.project_engine = project_engine
        self._global_engine: Engine | None = None

    @property
    def global_engine(self) -> Engine:
        """Lazily initialize global lexicon SQLite database at <configDir>/lexicon.db."""
        if self._global_engine is None:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            db_path = self.config_dir / "lexicon.db"
            eng = create_engine(f"sqlite:///{db_path}")
            # Ensure table exists in global db
            lexicon_entry_table.create(bind=eng, checkfirst=True)
            self._global_engine = eng
        return self._global_engine

    def _row_to_response(self, row: Any) -> LexiconEntryResponse:
        mapping = row._mapping
        return LexiconEntryResponse(
            id=mapping["id"],
            project_id=mapping["project_id"],
            pattern=mapping["pattern"],
            is_regex=bool(mapping["is_regex"]),
            spoken=mapping["spoken"],
            language=mapping["language"],
            category=mapping["category"],
            auto_apply=bool(mapping["auto_apply"]),
            case_sensitive=bool(mapping["case_sensitive"]),
            priority=int(mapping["priority"]),
            created_at=mapping["created_at"],
        )

    def list_entries(self, project_id: str | None = None) -> list[LexiconEntryResponse]:
        """List lexicon entries for global scope or specific project scope."""
        if project_id is None:
            stmt = (
                select(lexicon_entry_table)
                .where(lexicon_entry_table.c.project_id.is_(None))
                .order_by(lexicon_entry_table.c.priority, lexicon_entry_table.c.pattern)
            )
            with Session(self.global_engine) as s:
                rows = s.execute(stmt).all()
                return [self._row_to_response(r) for r in rows]
        else:
            if self.project_engine is None:
                return []
            stmt = (
                select(lexicon_entry_table)
                .where(lexicon_entry_table.c.project_id == project_id)
                .order_by(lexicon_entry_table.c.priority, lexicon_entry_table.c.pattern)
            )
            with Session(self.project_engine) as s:
                rows = s.execute(stmt).all()
                return [self._row_to_response(r) for r in rows]

    def get_effective_lexicon(self, project_id: str | None = None) -> list[LexiconEntryResponse]:
        """Compute effective lexicon: global entries overlaid by project entries."""
        global_entries = self.list_entries(project_id=None)
        if project_id is None:
            return global_entries

        project_entries = self.list_entries(project_id=project_id)
        effective: dict[tuple[str, bool], LexiconEntryResponse] = {}

        for g in global_entries:
            effective[(g.pattern, g.is_regex)] = g
        for p in project_entries:
            effective[(p.pattern, p.is_regex)] = p

        return sorted(effective.values(), key=lambda e: (e.priority, e.pattern))

    def create_entry(
        self,
        create_data: LexiconEntryCreate,
        project_id: str | None = None,
    ) -> LexiconEntryResponse:
        """Create a new lexicon entry in global or project scope."""
        now_str = datetime.datetime.now(datetime.UTC).isoformat()
        lex_id = generate_id(LEXICON_PREFIX)

        values: dict[str, Any] = {
            "id": lex_id,
            "project_id": project_id,
            "pattern": create_data.pattern,
            "is_regex": 1 if create_data.is_regex else 0,
            "spoken": create_data.spoken,
            "language": create_data.language,
            "category": create_data.category,
            "auto_apply": 1 if create_data.auto_apply else 0,
            "case_sensitive": 1 if create_data.case_sensitive else 0,
            "priority": create_data.priority,
            "created_at": now_str,
        }

        eng = self.project_engine if (project_id and self.project_engine) else self.global_engine
        with Session(eng) as s:
            s.execute(lexicon_entry_table.insert().values(**values))
            s.commit()

        return LexiconEntryResponse(
            id=lex_id,
            project_id=project_id,
            pattern=create_data.pattern,
            is_regex=create_data.is_regex,
            spoken=create_data.spoken,
            language=create_data.language,
            category=create_data.category,
            auto_apply=create_data.auto_apply,
            case_sensitive=create_data.case_sensitive,
            priority=create_data.priority,
            created_at=now_str,
        )

    def update_entry(
        self,
        entry_id: str,
        upd: LexiconEntryUpdate,
        project_id: str | None = None,
    ) -> LexiconEntryResponse | None:
        """Update an existing lexicon entry."""
        values: dict[str, Any] = {}
        if upd.pattern is not None:
            values["pattern"] = upd.pattern
        if upd.is_regex is not None:
            values["is_regex"] = 1 if upd.is_regex else 0
        if upd.spoken is not None:
            values["spoken"] = upd.spoken
        if upd.language is not None:
            values["language"] = upd.language
        if upd.category is not None:
            values["category"] = upd.category
        if upd.auto_apply is not None:
            values["auto_apply"] = 1 if upd.auto_apply else 0
        if upd.case_sensitive is not None:
            values["case_sensitive"] = 1 if upd.case_sensitive else 0
        if upd.priority is not None:
            values["priority"] = upd.priority

        if not values:
            return self.get_by_id(entry_id, project_id=project_id)

        eng = self.project_engine if (project_id and self.project_engine) else self.global_engine
        with Session(eng) as s:
            stmt = (
                update(lexicon_entry_table)
                .where(lexicon_entry_table.c.id == entry_id)
                .values(**values)
            )
            res = s.execute(stmt)
            if cast(CursorResult[Any], res).rowcount == 0:
                return None
            s.commit()

        return self.get_by_id(entry_id, project_id=project_id)

    def delete_entry(self, entry_id: str, project_id: str | None = None) -> bool:
        """Delete an entry by ID."""
        eng = self.project_engine if (project_id and self.project_engine) else self.global_engine
        with Session(eng) as s:
            stmt = delete(lexicon_entry_table).where(lexicon_entry_table.c.id == entry_id)
            res = s.execute(stmt)
            s.commit()
            return bool(cast(CursorResult[Any], res).rowcount > 0)

    def get_by_id(
        self,
        entry_id: str,
        project_id: str | None = None,
    ) -> LexiconEntryResponse | None:
        """Retrieve a single lexicon entry by ID."""
        eng = self.project_engine if (project_id and self.project_engine) else self.global_engine
        with Session(eng) as s:
            stmt = select(lexicon_entry_table).where(lexicon_entry_table.c.id == entry_id)
            row = s.execute(stmt).first()
            return self._row_to_response(row) if row else None
