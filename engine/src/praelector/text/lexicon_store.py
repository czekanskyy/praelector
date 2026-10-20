# SPDX-License-Identifier: Apache-2.0
"""Project lexicon rows (DATA_MODEL.md §12, AI-09).

The matching engine is ``text/lexicon.py``. This module only stores the
rules. A duplicate ``(pattern, is_regex)`` in the same project is rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from praelector.domain.enums import SuggestionCategory
from praelector.domain.ids import IdPrefix, new_id
from praelector.errors import AppError, ErrorCode
from praelector.store.manifest import utc_now
from praelector.store.tables import LexiconEntryRow, to_db_time


@dataclass(frozen=True, slots=True)
class LexiconEntry:
    id: str
    project_id: str
    pattern: str
    is_regex: bool
    spoken: str
    language: str
    category: str
    auto_apply: bool
    case_sensitive: bool
    priority: int
    created_at: str


def add_entry(
    session: Session,
    *,
    project_id: str,
    pattern: str,
    spoken: str,
    is_regex: bool = False,
    language: str = "pl",
    category: str = SuggestionCategory.DICT_HIT,
    auto_apply: bool = False,
    case_sensitive: bool = False,
    priority: int = 100,
) -> LexiconEntry:
    """Insert one rule. A bad regex or a duplicate pattern is a 422."""
    text = _required(pattern, "pattern")
    reading = _required(spoken, "spoken")
    chosen = _category(category)
    _regex(text, is_regex)
    _unique(session, project_id, text, is_regex, ignore_id=None)
    row = LexiconEntryRow(
        id=new_id(IdPrefix.LEXICON_ENTRY),
        project_id=project_id,
        pattern=text,
        is_regex=is_regex,
        spoken=reading,
        language=language,
        category=chosen,
        auto_apply=auto_apply,
        case_sensitive=case_sensitive,
        priority=priority,
        created_at=to_db_time(utc_now()),
    )
    session.add(row)
    session.flush()
    return _entry(row)


def list_entries(session: Session, project_id: str) -> list[LexiconEntry]:
    """Lower priority first, then pattern, so the matcher can walk in order."""
    rows = session.scalars(
        select(LexiconEntryRow)
        .where(LexiconEntryRow.project_id == project_id)
        .order_by(LexiconEntryRow.priority, LexiconEntryRow.pattern, LexiconEntryRow.id)
    ).all()
    return [_entry(row) for row in rows]


def delete_entry(session: Session, entry_id: str) -> None:
    row = session.get(LexiconEntryRow, entry_id)
    if row is None:
        raise AppError(ErrorCode.INTERNAL_NOT_FOUND, detail={"id": entry_id})
    session.delete(row)
    session.flush()


def _required(value: str, field: str) -> str:
    text = value.strip()
    if not text:
        raise AppError(ErrorCode.INTERNAL_VALIDATION_FAILED, detail={"field": field})
    return text


def _category(category: str) -> str:
    if category not in set(SuggestionCategory):
        raise AppError(ErrorCode.INTERNAL_VALIDATION_FAILED, detail={"field": "category"})
    return category


def _regex(pattern: str, is_regex: bool) -> None:
    if not is_regex:
        return
    try:
        re.compile(pattern)
    except re.error as exc:
        raise AppError(
            ErrorCode.INTERNAL_VALIDATION_FAILED,
            detail={"field": "pattern", "reason": "regex"},
        ) from exc


def _unique(
    session: Session,
    project_id: str,
    pattern: str,
    is_regex: bool,
    *,
    ignore_id: str | None,
) -> None:
    taken = session.scalars(
        select(LexiconEntryRow).where(
            LexiconEntryRow.project_id == project_id,
            LexiconEntryRow.pattern == pattern,
            LexiconEntryRow.is_regex == is_regex,
        )
    ).one_or_none()
    if taken is not None and taken.id != ignore_id:
        raise AppError(
            ErrorCode.INTERNAL_VALIDATION_FAILED,
            detail={"field": "pattern", "reason": "duplicate", "id": taken.id},
        )


def _entry(row: LexiconEntryRow) -> LexiconEntry:
    return LexiconEntry(
        id=row.id,
        project_id=row.project_id,
        pattern=row.pattern,
        is_regex=row.is_regex,
        spoken=row.spoken,
        language=row.language,
        category=row.category,
        auto_apply=row.auto_apply,
        case_sensitive=row.case_sensitive,
        priority=row.priority,
        created_at=row.created_at,
    )
