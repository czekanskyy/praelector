# SPDX-License-Identifier: Apache-2.0
"""High-level project lifecycle and workspace management service."""

from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from praelector.domain.ids import PROJECT_PREFIX, generate_id
from praelector.domain.models import (
    ProjectCounts,
    ProjectCreate,
    ProjectManifest,
    ProjectResponse,
    ProjectStats,
    ProjectSummary,
    ProjectUpdate,
)
from praelector.errors import AppError
from praelector.store.db import create_project_engine
from praelector.store.locks import ProjectLock
from praelector.store.manifest import read_manifest, write_manifest
from praelector.store.migrations.runner import apply_migrations
from praelector.store.project_dir import (
    ProjectPaths,
    create_project_dir,
    get_project_paths,
    list_project_dirs,
)
from praelector.store.repositories.chapters import ChapterRepository
from praelector.store.repositories.project import ProjectRepository
from praelector.store.settings import SettingsStore


def _sanitize_folder_name(name: str) -> str:
    """Convert project name into a safe filesystem directory name."""
    s = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    s = re.sub(r"\s+", "-", s)
    return s or "project"


class ProjectManager:
    """Singleton service managing project creation, opening, locking, and queries."""

    def __init__(self, settings_store: SettingsStore) -> None:
        self.settings_store = settings_store
        self.active_project_id: str | None = None
        self.active_paths: ProjectPaths | None = None
        self.active_lock: ProjectLock | None = None
        self.active_engine: Engine | None = None
        self.active_repo: ProjectRepository | None = None
        self.active_chapter_repo: ChapterRepository | None = None

    @property
    def is_open(self) -> bool:
        return self.active_project_id is not None and self.active_lock is not None

    def _get_projects_parent_dir(self) -> Path:
        settings = self.settings_store.get_settings()
        parent = Path(settings.projects_dir).resolve()
        parent.mkdir(parents=True, exist_ok=True)
        return parent

    def find_project_dir(self, project_id: str) -> ProjectPaths:
        """Locate project directory across the configured projects directory."""
        if self.active_project_id == project_id and self.active_paths is not None:
            return self.active_paths

        parent = self._get_projects_parent_dir()
        for p_dir in list_project_dirs(parent):
            manifest_path = p_dir / "project.json"
            try:
                manifest = read_manifest(manifest_path)
                if manifest.id == project_id:
                    return get_project_paths(p_dir)
            except Exception:
                continue

        raise AppError(
            code="project.not_found",
            detail={"project_id": project_id},
            status_code=404,
        )

    def list_projects(self) -> list[ProjectSummary]:
        """List all valid projects found in the configured projects directory."""
        parent = self._get_projects_parent_dir()
        summaries: list[ProjectSummary] = []

        for p_dir in list_project_dirs(parent):
            manifest_path = p_dir / "project.json"
            try:
                manifest = read_manifest(manifest_path)
                is_open = self.active_project_id == manifest.id
                summaries.append(
                    ProjectSummary(
                        id=manifest.id,
                        name=manifest.name,
                        path=str(p_dir),
                        created_at=manifest.created_at,
                        updated_at=manifest.updated_at,
                        spoken_language=manifest.spoken_language,
                        voice_mode=manifest.voice_mode,
                        backend_id=manifest.backend_id,
                        current_revision=manifest.current_revision,
                        is_open=is_open,
                    )
                )
            except Exception:
                continue

        # Most recently updated first
        return sorted(summaries, key=lambda s: s.updated_at, reverse=True)

    def create_project(self, payload: ProjectCreate) -> ProjectResponse:
        """Create a new Praelector project on disk with SQLite and baseline schema."""
        project_id = generate_id(PROJECT_PREFIX)
        now = datetime.now(UTC).isoformat()

        parent_dir = self._get_projects_parent_dir()
        if payload.dir:
            target_path = Path(payload.dir).resolve()
        else:
            folder_name = f"{_sanitize_folder_name(payload.name)}_{project_id[-6:]}"
            target_path = parent_dir / folder_name

        if target_path.exists() and any(target_path.iterdir()):
            raise AppError(
                code="project.directory_not_empty",
                detail={"path": str(target_path)},
                status_code=409,
            )

        paths = create_project_dir(target_path)

        manifest = ProjectManifest(
            schema_version=1,
            id=project_id,
            name=payload.name,
            created_at=now,
            updated_at=now,
            voice_mode=payload.voice_mode,
            backend_id=payload.backend_id,
            spoken_language=payload.spoken_language,
            current_revision=0,
        )
        write_manifest(paths.manifest, manifest)

        # Apply database migrations to create baseline tables
        apply_migrations(paths.db)

        # Insert project record and initial revision into project.db
        engine = create_project_engine(paths.db)
        try:
            repo = ProjectRepository(engine)
            repo.create(manifest)
        finally:
            engine.dispose()

        return ProjectResponse(
            id=manifest.id,
            name=manifest.name,
            path=str(paths.root),
            created_at=manifest.created_at,
            updated_at=manifest.updated_at,
            schema_version=manifest.schema_version,
            spoken_language=manifest.spoken_language,
            voice_mode=manifest.voice_mode,
            backend_id=manifest.backend_id,
            current_revision=0,
            is_open=False,
            counts=ProjectCounts(),
        )

    def open_project(self, project_id: str) -> ProjectResponse:
        """Acquire lock, run any pending migrations, and mark project as active."""
        if self.active_project_id == project_id and self.active_paths is not None:
            return self.get_project(project_id)

        # Close currently active project if another one is open
        if self.active_project_id is not None:
            self.close_project(self.active_project_id)

        paths = self.find_project_dir(project_id)

        # Acquire exclusive lock (raises AppError 409 if locked)
        lock = ProjectLock(paths.lock)
        lock.acquire()

        try:
            # Run migrations to guarantee database schema is up-to-date
            apply_migrations(paths.db)

            engine = create_project_engine(paths.db)
            repo = ProjectRepository(engine)
            chapter_repo = ChapterRepository(engine)

            self.active_project_id = project_id
            self.active_paths = paths
            self.active_lock = lock
            self.active_engine = engine
            self.active_repo = repo
            self.active_chapter_repo = chapter_repo

            return self.get_project(project_id)
        except Exception:
            lock.release()
            raise

    def close_project(self, project_id: str) -> None:
        """Release lock and unload currently open project."""
        if self.active_project_id != project_id:
            return

        if self.active_engine is not None:
            self.active_engine.dispose()
            self.active_engine = None

        if self.active_lock is not None:
            self.active_lock.release()
            self.active_lock = None

        self.active_project_id = None
        self.active_paths = None
        self.active_repo = None
        self.active_chapter_repo = None

    def get_open_chapter_repo(self, project_id: str) -> tuple[ChapterRepository, ProjectPaths]:
        """Ensure project is open and return active ChapterRepository and ProjectPaths."""
        if (
            self.active_project_id != project_id
            or self.active_chapter_repo is None
            or self.active_paths is None
        ):
            raise AppError(
                "project.not_open",
                status_code=400,
                detail={"project_id": project_id, "message": "Project must be opened first."},
            )
        return self.active_chapter_repo, self.active_paths

    def get_project(self, project_id: str) -> ProjectResponse:
        """Retrieve project status, manifest, and counts."""
        paths = self.find_project_dir(project_id)
        manifest = read_manifest(paths.manifest)
        is_open = self.active_project_id == project_id

        counts = ProjectCounts()
        db_fields: dict[str, Any] = {}

        if is_open and self.active_repo is not None:
            counts = self.active_repo.get_counts(project_id)
            db_row = self.active_repo.get(project_id)
            if db_row:
                db_fields = db_row
        else:
            # Temporary read-only inspection
            temp_engine = create_project_engine(paths.db)
            try:
                repo = ProjectRepository(temp_engine)
                counts = repo.get_counts(project_id)
                db_row = repo.get(project_id)
                if db_row:
                    db_fields = db_row
            except Exception:
                pass
            finally:
                temp_engine.dispose()

        return ProjectResponse(
            id=manifest.id,
            name=manifest.name,
            path=str(paths.root),
            created_at=manifest.created_at,
            updated_at=manifest.updated_at,
            schema_version=manifest.schema_version,
            source_format=db_fields.get("source_format"),
            source_original_rel=db_fields.get("source_original_rel"),
            working_epub_rel=db_fields.get("working_epub_rel"),
            converter=db_fields.get("converter"),
            book_language=db_fields.get("book_language"),
            spoken_language=manifest.spoken_language,
            voice_mode=manifest.voice_mode,
            backend_id=manifest.backend_id,
            backend_params_json=db_fields.get("backend_params_json"),
            precision=db_fields.get("precision", "fp16"),
            cloud_llm_enabled=bool(db_fields.get("cloud_llm_enabled", 0)),
            current_revision=int(db_fields.get("current_revision", manifest.current_revision)),
            is_open=is_open,
            counts=counts,
        )

    def update_project(self, project_id: str, update_req: ProjectUpdate) -> ProjectResponse:
        """Update manifest and database fields for a project."""
        paths = self.find_project_dir(project_id)
        manifest = read_manifest(paths.manifest)
        now = datetime.now(UTC).isoformat()

        db_updates: dict[str, Any] = {"updated_at": now}

        if update_req.name is not None:
            manifest.name = update_req.name
            db_updates["name"] = update_req.name
        if update_req.voice_mode is not None:
            manifest.voice_mode = update_req.voice_mode
            db_updates["voice_mode"] = update_req.voice_mode.value
        if update_req.backend_id is not None:
            manifest.backend_id = update_req.backend_id
            db_updates["backend_id"] = update_req.backend_id
        if update_req.spoken_language is not None:
            manifest.spoken_language = update_req.spoken_language
            db_updates["spoken_language"] = update_req.spoken_language
        if update_req.cloud_llm_enabled is not None:
            db_updates["cloud_llm_enabled"] = 1 if update_req.cloud_llm_enabled else 0

        manifest.updated_at = now
        write_manifest(paths.manifest, manifest)

        # Update SQLite table
        if self.active_project_id == project_id and self.active_repo is not None:
            self.active_repo.update(project_id, db_updates)
        else:
            temp_engine = create_project_engine(paths.db)
            try:
                repo = ProjectRepository(temp_engine)
                repo.update(project_id, db_updates)
            finally:
                temp_engine.dispose()

        return self.get_project(project_id)

    def delete_project(self, project_id: str, delete_files: bool = False) -> None:
        """Close project and optionally delete its workspace files from disk."""
        paths = self.find_project_dir(project_id)

        if self.active_project_id == project_id:
            self.close_project(project_id)

        if delete_files and paths.root.is_dir():
            shutil.rmtree(paths.root)

    def get_project_stats(self, project_id: str) -> ProjectStats:
        """Retrieve chapter, block, word, and suggestion statistics."""
        if self.active_project_id == project_id and self.active_repo is not None:
            return self.active_repo.get_stats(project_id)

        paths = self.find_project_dir(project_id)
        temp_engine = create_project_engine(paths.db)
        try:
            repo = ProjectRepository(temp_engine)
            return repo.get_stats(project_id)
        finally:
            temp_engine.dispose()
