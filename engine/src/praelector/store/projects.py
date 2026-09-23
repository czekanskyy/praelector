# SPDX-License-Identifier: Apache-2.0
"""Project lifecycle: create, list, open, close, patch, delete.

One project is open at a time (PRD §4 principle 6). Opening acquires
``project.lock``, runs migrations forward and hands back a live engine; the lock
is what stops a developer's ``just dev-engine`` from writing to a project the app
already owns (JB-06, D-14).

The Library is a **directory scan**, not a registry: ``projects_dir`` is the list.
That is why deleting a project means removing files — there is no separate index
to forget it from.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from praelector.config import RuntimeEnv
from praelector.domain.enums import VoiceMode
from praelector.domain.ids import IdPrefix, is_valid_id, new_id
from praelector.domain.models import ProjectDetail, ProjectSummary
from praelector.errors import AppError, ErrorCode
from praelector.store.db import create_project_engine, run_migrations, session_scope
from praelector.store.locks import ProjectLock
from praelector.store.manifest import (
    PROJECT_SCHEMA_VERSION,
    ProjectManifest,
    read_manifest,
    utc_now,
    write_manifest,
)
from praelector.store.project_dir import ProjectLayout, find_project_dirs, layout_for
from praelector.store.tables import ProjectRow, RevisionRow, to_db_time

logger = logging.getLogger(__name__)

AS_INGESTED_LABEL = "as-ingested"


@dataclass
class OpenProject:
    """A project this engine owns: lock held, database migrated."""

    layout: ProjectLayout
    manifest: ProjectManifest
    engine: Engine
    lock: ProjectLock
    db_revision: str

    @property
    def id(self) -> str:
        return self.manifest.id

    def dispose(self) -> None:
        self.lock.release()
        self.engine.dispose()


@dataclass
class ProjectPatch:
    """The fields ``PATCH /v1/projects/{pid}`` may change."""

    name: str | None = None
    voice_mode: VoiceMode | None = None
    backend_id: str | None = None
    spoken_language: str | None = None
    cloud_llm_enabled: bool | None = None


class ProjectStore:
    """Owns the projects directory and the single open project.

    Takes the whole :class:`RuntimeEnv` rather than a snapshot of ``AppPaths``:
    ``PUT /v1/settings`` can move ``projects_dir`` while a project is open, and
    rebuilding this object to pick that up would drop the lock.
    """

    def __init__(self, env: RuntimeEnv) -> None:
        self._env = env
        self._open: OpenProject | None = None

    @property
    def projects_dir(self) -> Path:
        return self._env.paths.projects_dir

    @property
    def current(self) -> OpenProject | None:
        return self._open

    @property
    def current_id(self) -> str | None:
        return self._open.id if self._open else None

    # -- create ---------------------------------------------------------------

    def create(
        self,
        *,
        name: str,
        voice_mode: VoiceMode = VoiceMode.SINGLE,
        spoken_language: str = "pl",
        backend_id: str | None = None,
        directory: Path | None = None,
    ) -> ProjectDetail:
        """Create the directory tree, the manifest and an empty database.

        Does not ingest anything (OPENAPI_SKETCH.md §3) — that is a separate call.
        """
        cleaned = name.strip()
        if not cleaned:
            raise AppError(
                ErrorCode.INTERNAL_VALIDATION_FAILED,
                detail={"field": "name", "reason": "empty"},
                message="a project needs a name",
            )

        project_id = new_id(IdPrefix.PROJECT)
        root = directory if directory is not None else self.projects_dir / project_id
        if root.exists() and any(root.iterdir()):
            raise AppError(
                ErrorCode.PROJECT_ALREADY_OPEN,
                detail={"path": root.as_posix()},
                message="target directory is not empty",
            )

        layout = layout_for(root)
        layout.ensure_dirs()

        now = utc_now()
        manifest = ProjectManifest.new(
            project_id=project_id, name=cleaned, voice_mode=voice_mode
        ).model_copy(
            update={
                "spoken_language": spoken_language,
                "backend_id": backend_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        write_manifest(layout.manifest, manifest)

        try:
            revision = run_migrations(layout.db)
            engine = create_project_engine(layout.db)
            try:
                with session_scope(engine) as session:
                    session.add(
                        ProjectRow(
                            id=project_id,
                            name=cleaned,
                            created_at=to_db_time(manifest.created_at),
                            updated_at=to_db_time(manifest.updated_at),
                            schema_version=PROJECT_SCHEMA_VERSION,
                            spoken_language=spoken_language,
                            voice_mode=voice_mode.value,
                            backend_id=backend_id,
                            current_revision=0,
                        )
                    )
                    session.add(
                        RevisionRow(
                            n=0,
                            created_at=to_db_time(now),
                            label=AS_INGESTED_LABEL,
                        )
                    )
            finally:
                engine.dispose()
        except Exception:
            # Never leave a half-created project behind: the Library would list a
            # directory that cannot be opened.
            shutil.rmtree(root, ignore_errors=True)
            raise

        logger.info("project created", extra={"project_id": project_id, "path": root.as_posix()})
        return ProjectDetail(
            **_summary_fields(manifest, root, is_open=False),
            schema_version=manifest.schema_version,
            db_revision=revision,
            cloud_llm_enabled=False,
        )

    # -- read -----------------------------------------------------------------

    def list_summaries(self) -> list[ProjectSummary]:
        """Every project on disk, most recently updated first.

        A manifest that cannot be read is still listed, with its directory name as
        the name and ``unreadable`` set, so the Library can offer to delete it
        instead of hiding a directory the user can see in a file manager.
        """
        summaries: list[ProjectSummary] = []
        for root in find_project_dirs(self.projects_dir):
            manifest = self._try_read_manifest(root / "project.json")
            if manifest is None:
                summaries.append(
                    ProjectSummary(
                        id=root.name,
                        name=root.name,
                        voice_mode=VoiceMode.SINGLE,
                        spoken_language="pl",
                        current_revision=0,
                        path=root.as_posix(),
                        is_open=False,
                        unreadable=True,
                    )
                )
                continue
            summaries.append(
                ProjectSummary(
                    **_summary_fields(manifest, root, is_open=self.current_id == manifest.id)
                )
            )
        summaries.sort(key=lambda s: s.updated_at or datetime.min, reverse=True)
        return summaries

    def get(self, project_id: str) -> ProjectDetail:
        layout = self._layout_for(project_id)
        manifest = read_manifest(layout.manifest)
        is_open = self.current_id == project_id
        # The cloud toggle lives only in the database (LM-05), so a closed project
        # still needs a session. Guarded on the file existing: opening an engine
        # would otherwise create an empty database as a side effect of a GET.
        cloud = False
        if layout.db.is_file():
            with self._session_for(project_id) as session:
                cloud = _cloud_enabled(session, project_id)
        return ProjectDetail(
            **_summary_fields(manifest, layout.root, is_open=is_open),
            schema_version=manifest.schema_version,
            db_revision=self._open.db_revision if is_open and self._open else "",
            cloud_llm_enabled=cloud,
        )

    # -- open / close ---------------------------------------------------------

    def open(self, project_id: str) -> OpenProject:
        """Lock, migrate and hand back a live project. Idempotent for the same id."""
        if self._open is not None:
            if self._open.id == project_id:
                return self._open
            raise AppError(
                ErrorCode.PROJECT_ALREADY_OPEN,
                detail={"open_project_id": self._open.id},
                message="close the open project first",
            )

        layout = self._layout_for(project_id)
        manifest = read_manifest(layout.manifest)
        if manifest.id != project_id:
            raise AppError(
                ErrorCode.PROJECT_MANIFEST_INVALID,
                detail={"expected": project_id, "found": manifest.id},
                message="the manifest id does not match its directory",
            )

        lock = ProjectLock(layout.lock)
        lock.acquire()
        try:
            # Forward-only. A job that was mid-write when the app died is marked
            # paused with reason "crash_recovery" by the job engine (JB-07); the
            # chunk-index reconcile that goes with it lands in M4.
            revision = run_migrations(layout.db)
            engine = create_project_engine(layout.db)
        except Exception:
            lock.release()
            raise

        self._open = OpenProject(
            layout=layout,
            manifest=manifest,
            engine=engine,
            lock=lock,
            db_revision=revision,
        )
        logger.info(
            "project opened",
            extra={"project_id": project_id, "db_revision": revision},
        )
        return self._open

    def close(self, project_id: str) -> None:
        if self._open is None:
            raise AppError(
                ErrorCode.PROJECT_NOT_OPEN,
                detail={"project_id": project_id},
                message="no project is open",
            )
        if self._open.id != project_id:
            raise AppError(
                ErrorCode.PROJECT_NOT_OPEN,
                detail={"project_id": project_id, "open_project_id": self._open.id},
                message="a different project is open",
            )
        closing, self._open = self._open, None
        closing.dispose()
        logger.info("project closed", extra={"project_id": project_id})

    def close_current(self) -> None:
        """Shutdown hook: release the lock and dispose the engine."""
        if self._open is None:
            return
        closing, self._open = self._open, None
        closing.dispose()
        logger.info("project closed on shutdown", extra={"project_id": closing.id})

    # -- patch / delete -------------------------------------------------------

    def patch(self, project_id: str, patch: ProjectPatch) -> ProjectDetail:
        layout = self._layout_for(project_id)
        manifest = read_manifest(layout.manifest)
        updates: dict[str, object] = {"updated_at": utc_now()}
        if patch.name is not None:
            cleaned = patch.name.strip()
            if not cleaned:
                raise AppError(
                    ErrorCode.INTERNAL_VALIDATION_FAILED,
                    detail={"field": "name", "reason": "empty"},
                )
            updates["name"] = cleaned
        if patch.voice_mode is not None:
            updates["voice_mode"] = patch.voice_mode
        if patch.backend_id is not None:
            updates["backend_id"] = patch.backend_id
        if patch.spoken_language is not None:
            updates["spoken_language"] = patch.spoken_language

        if len(updates) > 1:
            manifest = manifest.model_copy(update=updates)
            write_manifest(layout.manifest, manifest)

        if patch.cloud_llm_enabled is not None:
            with self._session_for(project_id) as session:
                row = session.get(ProjectRow, project_id)
                if row is None:
                    raise AppError(ErrorCode.PROJECT_NOT_FOUND, detail={"project_id": project_id})
                # LM-05 / NF-02: book text may only leave the machine when this is
                # on, so the change is logged rather than silently applied.
                if row.cloud_llm_enabled != patch.cloud_llm_enabled:
                    logger.info(
                        "cloud llm toggle changed",
                        extra={
                            "project_id": project_id,
                            "cloud_llm_enabled": patch.cloud_llm_enabled,
                        },
                    )
                row.cloud_llm_enabled = patch.cloud_llm_enabled
                row.updated_at = to_db_time(manifest.updated_at)

        if self._open is not None and self._open.id == project_id:
            self._open.manifest = manifest

        return self.get(project_id)

    def delete(self, project_id: str, *, delete_files: bool) -> None:
        """Remove a project.

        ``delete_files=True`` deletes the whole directory, audio included — the UI
        must confirm it explicitly. ``False`` removes only the manifest, database
        and lock, which drops the project from the Library while leaving
        ``source/``, ``audio/`` and ``output/`` for the user to recover by hand.
        """
        layout = self._layout_for(project_id)
        if self.current_id == project_id:
            self.close(project_id)

        if delete_files:
            shutil.rmtree(layout.root, ignore_errors=False)
        else:
            for path in (layout.manifest, layout.db, layout.lock):
                path.unlink(missing_ok=True)
            # WAL and shared-memory files must not outlive the database.
            for suffix in ("-wal", "-shm"):
                Path(str(layout.db) + suffix).unlink(missing_ok=True)

        logger.info(
            "project deleted",
            extra={"project_id": project_id, "delete_files": delete_files},
        )

    # -- internals ------------------------------------------------------------

    def _layout_for(self, project_id: str) -> ProjectLayout:
        if not is_valid_id(project_id):
            raise AppError(
                ErrorCode.PROJECT_NOT_FOUND,
                detail={"project_id": project_id, "reason": "malformed_id"},
            )
        root = self.projects_dir / project_id
        if not root.is_dir():
            raise AppError(
                ErrorCode.PROJECT_NOT_FOUND,
                detail={"project_id": project_id, "path": root.as_posix()},
            )
        return layout_for(root)

    def _try_read_manifest(self, path: Path) -> ProjectManifest | None:
        try:
            return read_manifest(path)
        except AppError:
            logger.warning("unreadable project manifest", extra={"path": path.as_posix()})
            return None

    @contextmanager
    def _session_for(self, project_id: str) -> Iterator[Session]:
        """A session on the open project's engine, or a short-lived one."""
        if self._open is not None and self._open.id == project_id:
            with session_scope(self._open.engine) as session:
                yield session
            return
        layout = self._layout_for(project_id)
        engine = create_project_engine(layout.db)
        try:
            with session_scope(engine) as session:
                yield session
        finally:
            engine.dispose()


def _cloud_enabled(session: Session, project_id: str) -> bool:
    row = session.scalar(select(ProjectRow.cloud_llm_enabled).where(ProjectRow.id == project_id))
    return bool(row)


def _summary_fields(manifest: ProjectManifest, root: Path, *, is_open: bool) -> dict[str, Any]:
    return {
        "id": manifest.id,
        "name": manifest.name,
        "created_at": manifest.created_at,
        "updated_at": manifest.updated_at,
        "voice_mode": manifest.voice_mode,
        "backend_id": manifest.backend_id,
        "spoken_language": manifest.spoken_language,
        "current_revision": manifest.current_revision,
        "path": root.as_posix(),
        "is_open": is_open,
        "unreadable": False,
    }
