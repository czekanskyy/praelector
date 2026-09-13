# SPDX-License-Identifier: Apache-2.0
"""Suggestion repository for SQLite storage operations (AI-04, AI-06)."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import Engine, and_, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from praelector.domain.enums import DetectorKind, SuggestionCategory, SuggestionStatus
from praelector.domain.ids import BATCH_PREFIX, SUGGESTION_PREFIX, generate_id
from praelector.domain.models import (
    SuggestionCreate,
    SuggestionRange,
    SuggestionResponse,
    SuggestionUpdate,
)
from praelector.store.schema import suggestion_table


class SuggestionRepository:
    """Data access layer for Suggestion entities in project.db."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _row_to_response(self, row: Any) -> SuggestionResponse:
        mapping = row._mapping
        start_val = int(mapping["start"])
        end_val = int(mapping["end"])
        return SuggestionResponse(
            id=mapping["id"],
            project_id=mapping["project_id"],
            chapter_id=mapping["chapter_id"],
            block_id=mapping["block_id"],
            start=start_val,
            end=end_val,
            range=SuggestionRange(start=start_val, end=end_val),
            category=SuggestionCategory(mapping["category"]),
            original=mapping["original"],
            proposed=mapping["proposed"],
            payload_json=mapping["payload_json"],
            rationale=mapping["rationale"],
            confidence=float(mapping["confidence"]),
            detector=DetectorKind(mapping["detector"]),
            status=SuggestionStatus(mapping["status"]),
            error_code=mapping["error_code"],
            llm_profile_id=mapping["llm_profile_id"],
            prompt_version=mapping["prompt_version"],
            batch_id=mapping["batch_id"],
            base_revision=int(mapping["base_revision"]),
            applied_in_revision=int(mapping["applied_in_revision"])
            if mapping["applied_in_revision"] is not None
            else None,
            created_at=mapping["created_at"],
        )

    def create(
        self,
        item: SuggestionCreate,
        session: Session | None = None,
    ) -> SuggestionResponse:
        """Insert a single suggestion."""
        res = self.create_many([item], session=session)
        return res[0]

    def create_many(
        self,
        items: list[SuggestionCreate],
        session: Session | None = None,
    ) -> list[SuggestionResponse]:
        """Insert multiple suggestions in a single transaction."""
        if not items:
            return []

        now_str = datetime.datetime.now(datetime.UTC).isoformat()
        rows_to_insert: list[dict[str, Any]] = []
        created_responses: list[SuggestionResponse] = []

        for item in items:
            sug_id = generate_id(SUGGESTION_PREFIX)
            row_dict = {
                "id": sug_id,
                "project_id": item.project_id,
                "chapter_id": item.chapter_id,
                "block_id": item.block_id,
                "start": item.start,
                "end": item.end,
                "category": item.category.value,
                "original": item.original,
                "proposed": item.proposed,
                "payload_json": item.payload_json,
                "rationale": item.rationale,
                "confidence": item.confidence,
                "detector": item.detector.value,
                "status": item.status.value,
                "error_code": item.error_code,
                "llm_profile_id": item.llm_profile_id,
                "prompt_version": item.prompt_version,
                "batch_id": item.batch_id,
                "base_revision": item.base_revision,
                "applied_in_revision": None,
                "created_at": now_str,
            }
            rows_to_insert.append(row_dict)
            created_responses.append(
                SuggestionResponse(
                    id=sug_id,
                    project_id=item.project_id,
                    chapter_id=item.chapter_id,
                    block_id=item.block_id,
                    start=item.start,
                    end=item.end,
                    range=SuggestionRange(start=item.start, end=item.end),
                    category=item.category,
                    original=item.original,
                    proposed=item.proposed,
                    payload_json=item.payload_json,
                    rationale=item.rationale,
                    confidence=item.confidence,
                    detector=item.detector,
                    status=item.status,
                    error_code=item.error_code,
                    llm_profile_id=item.llm_profile_id,
                    prompt_version=item.prompt_version,
                    batch_id=item.batch_id,
                    base_revision=item.base_revision,
                    applied_in_revision=None,
                    created_at=now_str,
                )
            )

        def _do_insert(s: Session) -> None:
            s.execute(suggestion_table.insert(), rows_to_insert)

        if session is not None:
            _do_insert(session)
        else:
            with Session(self.engine) as s:
                _do_insert(s)
                s.commit()

        return created_responses

    def get_by_id(
        self,
        suggestion_id: str,
        session: Session | None = None,
    ) -> SuggestionResponse | None:
        """Fetch a suggestion by its ID."""
        stmt = select(suggestion_table).where(suggestion_table.c.id == suggestion_id)

        def _do_select(s: Session) -> SuggestionResponse | None:
            row = s.execute(stmt).first()
            return self._row_to_response(row) if row else None

        if session is not None:
            return _do_select(session)
        with Session(self.engine) as s:
            return _do_select(s)

    def list(
        self,
        project_id: str,
        chapter_id: str | None = None,
        category: Sequence[SuggestionCategory] | None = None,
        status: Sequence[SuggestionStatus] | None = None,
        detector: Sequence[DetectorKind] | None = None,
        min_confidence: float | None = None,
        limit: int = 100,
        offset: int = 0,
        session: Session | None = None,
    ) -> list[SuggestionResponse]:
        """Query suggestions with multi-criteria filtering."""
        conditions = [suggestion_table.c.project_id == project_id]
        if chapter_id is not None:
            conditions.append(suggestion_table.c.chapter_id == chapter_id)
        if category:
            conditions.append(suggestion_table.c.category.in_([c.value for c in category]))
        if status:
            conditions.append(suggestion_table.c.status.in_([st.value for st in status]))
        if detector:
            conditions.append(suggestion_table.c.detector.in_([d.value for d in detector]))
        if min_confidence is not None:
            conditions.append(suggestion_table.c.confidence >= min_confidence)

        stmt = (
            select(suggestion_table)
            .where(and_(*conditions))
            .order_by(suggestion_table.c.chapter_id, suggestion_table.c.start)
            .limit(limit)
            .offset(offset)
        )

        def _do_list(s: Session) -> list[SuggestionResponse]:
            rows = s.execute(stmt).all()
            return [self._row_to_response(r) for r in rows]

        if session is not None:
            return _do_list(session)
        with Session(self.engine) as s:
            return _do_list(s)

    def count(
        self,
        project_id: str,
        chapter_id: str | None = None,
        category: Sequence[SuggestionCategory] | None = None,
        status: Sequence[SuggestionStatus] | None = None,
        session: Session | None = None,
    ) -> int:
        """Count suggestions matching filter criteria."""
        conditions = [suggestion_table.c.project_id == project_id]
        if chapter_id is not None:
            conditions.append(suggestion_table.c.chapter_id == chapter_id)
        if category:
            conditions.append(suggestion_table.c.category.in_([c.value for c in category]))
        if status:
            conditions.append(suggestion_table.c.status.in_([st.value for st in status]))

        stmt = select(func.count()).select_from(suggestion_table).where(and_(*conditions))

        def _do_count(s: Session) -> int:
            val = s.execute(stmt).scalar()
            return int(val) if val else 0

        if session is not None:
            return _do_count(session)
        with Session(self.engine) as s:
            return _do_count(s)

    def update(
        self,
        suggestion_id: str,
        upd: SuggestionUpdate,
        session: Session | None = None,
    ) -> SuggestionResponse | None:
        """Update suggestion status and optionally proposed text."""
        values: dict[str, Any] = {"status": upd.status.value}
        if upd.proposed is not None:
            values["proposed"] = upd.proposed

        stmt = (
            update(suggestion_table).where(suggestion_table.c.id == suggestion_id).values(**values)
        )

        def _do_update(s: Session) -> SuggestionResponse | None:
            res = s.execute(stmt)
            if cast(CursorResult[Any], res).rowcount == 0:
                return None
            row = s.execute(
                select(suggestion_table).where(suggestion_table.c.id == suggestion_id)
            ).first()
            return self._row_to_response(row) if row else None

        if session is not None:
            return _do_update(session)
        with Session(self.engine) as s:
            item = _do_update(s)
            s.commit()
            return item

    def bulk_update_status(
        self,
        project_id: str,
        action: str,
        category: SuggestionCategory | None = None,
        status: SuggestionStatus | None = None,
        chapter_id: str | None = None,
        limit: int | None = None,
        batch_id: str | None = None,
        session: Session | None = None,
    ) -> tuple[str, int]:
        """Perform bulk accept or reject with a batch_id for undo."""
        batch = batch_id or generate_id(BATCH_PREFIX)
        new_status = SuggestionStatus.ACCEPTED if action == "accept" else SuggestionStatus.REJECTED

        conditions = [suggestion_table.c.project_id == project_id]
        if status is not None:
            conditions.append(suggestion_table.c.status == status.value)
        else:
            conditions.append(suggestion_table.c.status == SuggestionStatus.PENDING.value)

        if category is not None:
            conditions.append(suggestion_table.c.category == category.value)
        if chapter_id is not None:
            conditions.append(suggestion_table.c.chapter_id == chapter_id)

        # Find matching IDs up to limit
        select_stmt = select(suggestion_table.c.id).where(and_(*conditions))
        if limit is not None:
            select_stmt = select_stmt.limit(limit)

        def _do_bulk(s: Session) -> tuple[str, int]:
            ids = [r[0] for r in s.execute(select_stmt).all()]
            if not ids:
                return batch, 0

            upd_stmt = (
                update(suggestion_table)
                .where(suggestion_table.c.id.in_(ids))
                .values(status=new_status.value, batch_id=batch)
            )
            res = s.execute(upd_stmt)
            return batch, int(cast(CursorResult[Any], res).rowcount)

        if session is not None:
            return _do_bulk(session)
        with Session(self.engine) as s:
            ret = _do_bulk(s)
            s.commit()
            return ret
