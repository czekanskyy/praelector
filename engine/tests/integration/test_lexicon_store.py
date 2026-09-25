# SPDX-License-Identifier: Apache-2.0
"""Project lexicon rows: order, duplicates, and a regex that does not compile."""

from __future__ import annotations

import pytest

from praelector.config import RuntimeEnv
from praelector.errors import AppError, ErrorCode
from praelector.store.db import session_scope
from praelector.store.projects import ProjectStore
from praelector.text.lexicon_store import add_entry, delete_entry, list_entries


def test_entries_list_by_priority_and_a_duplicate_is_rejected(runtime_env: RuntimeEnv) -> None:
    store = ProjectStore(runtime_env)
    detail = store.create(name="Lexicon")
    opened = store.open(detail.id)
    try:
        assert opened.db_revision == "0006_lexicon"
        with session_scope(opened.engine) as session:
            later = add_entry(
                session, project_id=detail.id, pattern="NASA", spoken="nasa", priority=50
            )
            earlier = add_entry(
                session, project_id=detail.id, pattern="PDF", spoken="pe de ef", priority=10
            )
            assert [item.id for item in list_entries(session, detail.id)] == [earlier.id, later.id]
            with pytest.raises(AppError) as caught:
                add_entry(session, project_id=detail.id, pattern="NASA", spoken="inne")
            assert caught.value.code is ErrorCode.INTERNAL_VALIDATION_FAILED
            assert caught.value.detail["reason"] == "duplicate"
            delete_entry(session, earlier.id)
            assert [item.pattern for item in list_entries(session, detail.id)] == ["NASA"]
    finally:
        store.close_current()


def test_a_broken_regex_is_not_stored(runtime_env: RuntimeEnv) -> None:
    store = ProjectStore(runtime_env)
    detail = store.create(name="Bad")
    opened = store.open(detail.id)
    try:
        with session_scope(opened.engine) as session:
            with pytest.raises(AppError) as caught:
                add_entry(
                    session,
                    project_id=detail.id,
                    pattern="(",
                    spoken="nawias",
                    is_regex=True,
                )
            assert caught.value.detail["reason"] == "regex"
            assert list_entries(session, detail.id) == []
    finally:
        store.close_current()
