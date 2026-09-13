# SPDX-License-Identifier: Apache-2.0
"""Unit tests for project manifest reading and writing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from praelector.domain.enums import VoiceMode
from praelector.domain.models import ProjectManifest
from praelector.errors import AppError
from praelector.store.manifest import read_manifest, write_manifest


def test_manifest_roundtrip(tmp_path: Path) -> None:
    manifest_path = tmp_path / "project.json"
    manifest = ProjectManifest(
        schema_version=1,
        id="prj_01TEST1234567890ABCDEFGH",
        name="Test Book",
        created_at="2026-09-13T10:00:00Z",
        updated_at="2026-09-13T10:00:00Z",
        voice_mode=VoiceMode.NARRATOR_DIALOGUE,
        backend_id="omnivoice",
        spoken_language="pl",
        current_revision=0,
    )

    write_manifest(manifest_path, manifest)
    loaded = read_manifest(manifest_path)

    assert loaded.id == manifest.id
    assert loaded.name == "Test Book"
    assert loaded.voice_mode == VoiceMode.NARRATOR_DIALOGUE


def test_manifest_schema_too_new(tmp_path: Path) -> None:
    manifest_path = tmp_path / "project.json"
    payload = {
        "schema_version": 999,
        "id": "prj_01TEST",
        "name": "Future Project",
        "created_at": "2026-09-13T10:00:00Z",
        "updated_at": "2026-09-13T10:00:00Z",
        "voice_mode": "single",
        "backend_id": "omnivoice",
        "spoken_language": "pl",
        "current_revision": 0,
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        read_manifest(manifest_path)

    assert exc_info.value.code == "project.schema_too_new"
    assert exc_info.value.status_code == 400


def test_manifest_not_found(tmp_path: Path) -> None:
    manifest_path = tmp_path / "nonexistent.json"
    with pytest.raises(AppError) as exc_info:
        read_manifest(manifest_path)

    assert exc_info.value.code == "project.not_found"
    assert exc_info.value.status_code == 404
