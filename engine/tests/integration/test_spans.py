# SPDX-License-Identifier: Apache-2.0
"""Accepted readings are stored as spans and change only the spoken view."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.ebook_factory import tiny_epub3
from tests.integration.test_chapters import _chapters, _ingest, _open_project, _write

from praelector.state import AppState
from praelector.store.chapters import ChapterStore
from praelector.text.suggestion import make_suggestion


def test_a_pronunciation_changes_the_spoken_view_and_not_the_print(
    client: TestClient, auth: dict[str, str], app_state: AppState, tmp_path: Path
) -> None:
    project_id, _root = _open_project(client, auth)
    _ingest(client, auth, project_id, _write(tmp_path / "book.epub", tiny_epub3()))
    tree = _chapters(client, auth, project_id)
    chapters = tree["chapters"]
    assert isinstance(chapters, list)
    chapter_id = chapters[0]["id"]
    assert isinstance(chapter_id, str)
    store = ChapterStore(app_state.projects.require_open(project_id))
    current = store.text(chapter_id, "display")
    block = next(item for item in current.blocks if "April" in item.text)
    start = block.text.index("April")
    suggestion = make_suggestion(
        text=block.text,
        start=start,
        end=start + len("April"),
        replacement="ejpryl",
        kind="foreign_word",
        reason="lexicon",
        confidence=0.99,
    )
    committed = store.apply_reading(chapter_id, current.revision, {block.id: [suggestion]})
    assert committed.conflicts == ()
    assert committed.revision == current.revision + 1
    display = store.text(chapter_id, "display")
    spoken = store.text(chapter_id, "spoken")
    assert "April" in display.text
    assert "ejpryl" in spoken.text
    assert "April" not in spoken.text


def test_a_stale_suggestion_is_a_conflict_and_does_not_bump_the_revision(
    client: TestClient, auth: dict[str, str], app_state: AppState, tmp_path: Path
) -> None:
    project_id, _root = _open_project(client, auth)
    _ingest(client, auth, project_id, _write(tmp_path / "book.epub", tiny_epub3()))
    tree = _chapters(client, auth, project_id)
    chapters = tree["chapters"]
    assert isinstance(chapters, list)
    chapter_id = chapters[0]["id"]
    assert isinstance(chapter_id, str)
    store = ChapterStore(app_state.projects.require_open(project_id))
    current = store.text(chapter_id, "display")
    block = current.blocks[0]
    stale = make_suggestion(
        text=block.text + "  ",
        start=len(block.text),
        end=len(block.text) + 2,
        replacement=" ",
        kind="conversion_artifact",
        reason="whitespace",
        confidence=0.99,
    )
    committed = store.apply_reading(chapter_id, current.revision, {block.id: [stale]})
    assert committed.revision == current.revision
    assert committed.conflicts == ((block.id, "  "),)
