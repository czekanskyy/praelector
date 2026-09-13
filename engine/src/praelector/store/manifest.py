# SPDX-License-Identifier: Apache-2.0
"""Project manifest reader, writer, and schema validation."""

from __future__ import annotations

import json
from pathlib import Path

from praelector.domain.models import ProjectManifest
from praelector.errors import AppError
from praelector.store.atomic import atomic_write

CURRENT_PROJECT_SCHEMA_VERSION = 1


def read_manifest(manifest_path: Path | str) -> ProjectManifest:
    """Read and validate project.json from disk."""
    path = Path(manifest_path)
    if not path.is_file():
        raise AppError(
            code="project.not_found",
            detail={"path": str(path)},
            status_code=404,
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as err:
        raise AppError(
            code="project.corrupted",
            detail={"path": str(path), "error": str(err)},
            status_code=500,
        ) from err

    schema_version = data.get("schema_version", 0)
    if schema_version > CURRENT_PROJECT_SCHEMA_VERSION:
        raise AppError(
            code="project.schema_too_new",
            detail={
                "project_schema": schema_version,
                "engine_schema": CURRENT_PROJECT_SCHEMA_VERSION,
            },
            status_code=400,
        )

    try:
        return ProjectManifest.model_validate(data)
    except Exception as err:
        raise AppError(
            code="project.corrupted",
            detail={"path": str(path), "error": str(err)},
            status_code=500,
        ) from err


def write_manifest(manifest_path: Path | str, manifest: ProjectManifest) -> None:
    """Write project manifest atomically to disk."""
    path = Path(manifest_path)
    payload = manifest.model_dump_json(indent=2)
    atomic_write(path, payload)
