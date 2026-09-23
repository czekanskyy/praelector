# SPDX-License-Identifier: Apache-2.0
"""Tests for the store primitives: atomic writes, the manifest, and project.lock."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from praelector.domain.enums import VoiceMode
from praelector.errors import AppError, ErrorCode
from praelector.store.atomic import canonical_json, write_bytes_atomic, write_json_atomic
from praelector.store.locks import ProjectLock
from praelector.store.manifest import (
    PROJECT_SCHEMA_VERSION,
    ProjectManifest,
    read_manifest,
    write_manifest,
)
from praelector.store.project_dir import find_project_dirs, layout_for


def test_atomic_write_creates_the_file_and_no_leftovers(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "job.json"
    write_bytes_atomic(target, b'{"state":"running"}')
    assert target.read_bytes() == b'{"state":"running"}'
    assert list(target.parent.iterdir()) == [target]


def test_atomic_write_replaces_the_previous_contents(tmp_path: Path) -> None:
    target = tmp_path / "job.json"
    write_bytes_atomic(target, b"first")
    write_bytes_atomic(target, b"second")
    assert target.read_bytes() == b"second"
    assert list(tmp_path.iterdir()) == [target]


def test_canonical_json_is_stable_regardless_of_insertion_order() -> None:
    first = canonical_json({"b": 1, "a": 2})
    second = canonical_json({"a": 2, "b": 1})
    assert first == second
    assert first.endswith("\n")
    assert " " not in first.strip()


def test_canonical_json_keeps_non_ascii_readable() -> None:
    assert "Nie zdążymy" in canonical_json({"text": "Nie zdążymy"})


def test_write_json_atomic_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "sidecar.json"
    write_json_atomic(target, {"render_key": "ab12", "duration_s": 4.12})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "render_key": "ab12",
        "duration_s": 4.12,
    }


def _manifest(**overrides: object) -> ProjectManifest:
    base: dict[str, object] = {
        "id": "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "name": "Kroniki Wrzosowiska",
        "created_at": datetime(2026, 9, 13, 10, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 9, 13, 11, 20, tzinfo=UTC),
        "voice_mode": VoiceMode.NARRATOR_MALE_FEMALE,
    }
    base.update(overrides)
    return ProjectManifest.model_validate(base)


def test_manifest_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    original = _manifest(backend_id="omnivoice", current_revision=7)
    write_manifest(path, original)
    assert read_manifest(path) == original


def test_manifest_defaults(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    write_manifest(path, _manifest())
    loaded = read_manifest(path)
    assert loaded.spoken_language == "pl"
    assert loaded.current_revision == 0
    assert loaded.backend_id is None
    assert loaded.schema_version == PROJECT_SCHEMA_VERSION


def test_a_newer_schema_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    payload = _manifest().model_dump(mode="json")
    payload["schema_version"] = PROJECT_SCHEMA_VERSION + 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AppError) as excinfo:
        read_manifest(path)
    assert excinfo.value.code is ErrorCode.PROJECT_SCHEMA_TOO_NEW
    assert excinfo.value.detail["supported"] == PROJECT_SCHEMA_VERSION


def test_corrupt_json_is_a_manifest_error(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(AppError) as excinfo:
        read_manifest(path)
    assert excinfo.value.code is ErrorCode.PROJECT_MANIFEST_INVALID
    assert excinfo.value.detail["reason"] == "not_json"


def test_a_json_array_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(AppError) as excinfo:
        read_manifest(path)
    assert excinfo.value.detail["reason"] == "not_an_object"


def test_a_missing_field_is_reported_with_its_path(tmp_path: Path) -> None:
    path = tmp_path / "project.json"
    payload = _manifest().model_dump(mode="json")
    del payload["name"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AppError) as excinfo:
        read_manifest(path)
    assert excinfo.value.code is ErrorCode.PROJECT_MANIFEST_INVALID
    assert ["name"] in excinfo.value.detail["fields"]


def test_reading_a_missing_manifest_is_project_not_found(tmp_path: Path) -> None:
    with pytest.raises(AppError) as excinfo:
        read_manifest(tmp_path / "project.json")
    assert excinfo.value.code is ErrorCode.PROJECT_NOT_FOUND


def test_the_lock_is_exclusive_and_reports_the_owner(tmp_path: Path) -> None:
    path = tmp_path / "project.lock"
    first = ProjectLock(path)
    second = ProjectLock(path)
    first.acquire()
    try:
        with pytest.raises(AppError) as excinfo:
            second.acquire()
        assert excinfo.value.code is ErrorCode.PROJECT_LOCKED
        assert excinfo.value.detail["owner_pid"] == os.getpid()
    finally:
        first.release()

    # Releasing makes it available again — and a stale file is not a blocker.
    assert path.exists()
    second.acquire()
    second.release()


def test_the_lock_is_idempotent_and_releasable_when_not_held(tmp_path: Path) -> None:
    lock = ProjectLock(tmp_path / "project.lock")
    lock.acquire()
    lock.acquire()
    assert lock.held
    lock.release()
    lock.release()
    assert not lock.held


def test_the_lock_works_as_a_context_manager(tmp_path: Path) -> None:
    path = tmp_path / "project.lock"
    with ProjectLock(path) as lock:
        assert lock.held
        with pytest.raises(AppError):
            ProjectLock(path).acquire()
    assert not lock.held
    ProjectLock(path).acquire()


def test_layout_derives_every_path_from_the_root(tmp_path: Path) -> None:
    layout = layout_for(tmp_path / "prj_x")
    assert layout.manifest.name == "project.json"
    assert layout.db.name == "project.db"
    assert layout.lock.name == "project.lock"
    assert layout.working_epub == layout.source / "working.epub"
    assert layout.chunk_wav("abcdef123") == layout.chunks / "ab" / "abcdef123.wav"
    assert layout.chunk_sidecar("abcdef123").suffix == ".json"
    assert layout.job_dir("job_1") == layout.jobs / "job_1"
    assert layout.relative(layout.output / "book.m4b") == "output/book.m4b"


def test_ensure_dirs_creates_the_documented_tree(tmp_path: Path) -> None:
    layout = layout_for(tmp_path / "prj_x")
    layout.ensure_dirs()
    for directory in (
        layout.source,
        layout.reader,
        layout.voices,
        layout.chunks,
        layout.quarantine,
        layout.jobs,
        layout.output,
        layout.cache,
    ):
        assert directory.is_dir(), directory


def test_find_project_dirs_only_lists_real_projects(tmp_path: Path) -> None:
    (tmp_path / "prj_a").mkdir()
    (tmp_path / "prj_a" / "project.json").write_text("{}", encoding="utf-8")
    (tmp_path / "not-a-project").mkdir()
    (tmp_path / "stray.txt").write_text("x", encoding="utf-8")
    assert find_project_dirs(tmp_path) == [tmp_path / "prj_a"]


def test_find_project_dirs_on_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert find_project_dirs(tmp_path / "nope") == []
