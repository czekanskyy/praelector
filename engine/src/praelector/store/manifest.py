# SPDX-License-Identifier: Apache-2.0
"""``project.json``: the manifest the Library reads without opening a database.

Deliberately tiny (D-02). SQLite is authoritative for everything else; the
manifest exists so listing recent projects does not mean opening N databases, and
so a project can be identified after its database is damaged.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from praelector.domain.enums import VoiceMode
from praelector.errors import AppError, ErrorCode
from praelector.store.atomic import write_json_atomic

MANIFEST_NAME = "project.json"

#: Bumped when the on-disk project schema changes incompatibly. A newer manifest
#: is refused rather than half-read (DATA_MODEL.md §14).
PROJECT_SCHEMA_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(tz=UTC).replace(microsecond=0)


class ProjectManifest(BaseModel):
    schema_version: int = PROJECT_SCHEMA_VERSION
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    voice_mode: VoiceMode = VoiceMode.SINGLE
    backend_id: str | None = None
    spoken_language: str = "pl"
    current_revision: int = Field(default=0, ge=0)

    @classmethod
    def new(cls, *, project_id: str, name: str, voice_mode: VoiceMode) -> ProjectManifest:
        now = utc_now()
        return cls(
            id=project_id,
            name=name,
            created_at=now,
            updated_at=now,
            voice_mode=voice_mode,
        )


def read_manifest(path: Path) -> ProjectManifest:
    """Read and validate a manifest, failing with a stable code.

    A newer ``schema_version`` is refused outright (``project.schema_too_new``):
    reading it would silently drop fields the newer writer expects to survive.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AppError(
            ErrorCode.PROJECT_NOT_FOUND,
            detail={"path": path.as_posix()},
            message="project.json is missing",
        ) from exc
    except OSError as exc:
        raise AppError(
            ErrorCode.PROJECT_MANIFEST_INVALID,
            detail={"path": path.as_posix(), "reason": "unreadable"},
            message=str(exc),
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppError(
            ErrorCode.PROJECT_MANIFEST_INVALID,
            detail={"path": path.as_posix(), "reason": "not_json", "position": exc.pos},
            message="project.json is not valid JSON",
        ) from exc

    if not isinstance(data, dict):
        raise AppError(
            ErrorCode.PROJECT_MANIFEST_INVALID,
            detail={"path": path.as_posix(), "reason": "not_an_object"},
        )

    version = data.get("schema_version", PROJECT_SCHEMA_VERSION)
    if isinstance(version, int) and version > PROJECT_SCHEMA_VERSION:
        raise AppError(
            ErrorCode.PROJECT_SCHEMA_TOO_NEW,
            detail={"found": version, "supported": PROJECT_SCHEMA_VERSION},
            message="project was created by a newer Praelector",
        )

    try:
        return ProjectManifest.model_validate(data)
    except ValidationError as exc:
        raise AppError(
            ErrorCode.PROJECT_MANIFEST_INVALID,
            detail={
                "path": path.as_posix(),
                "reason": "schema",
                "fields": [list(err["loc"]) for err in exc.errors()],
            },
            message=f"project.json failed validation: {exc.error_count()} fields",
        ) from exc


def write_manifest(path: Path, manifest: ProjectManifest) -> None:
    write_json_atomic(path, manifest.model_dump(mode="json"))
