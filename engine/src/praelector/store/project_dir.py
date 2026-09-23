# SPDX-License-Identifier: Apache-2.0
"""The project directory layout (REPO_LAYOUT.md §10).

Two of PRD §5.2's directories are deliberately absent: ``book/`` (parsed chapters
and the span model) and ``suggestions/``. SQLite is authoritative for both
(D-02), so writing them to disk a second time would create two sources of truth
and a reconciliation problem with no benefit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from praelector.store.manifest import MANIFEST_NAME

DB_NAME = "project.db"
LOCK_NAME = "project.lock"

#: Content-addressed chunk audio is sharded two hex chars deep so no single
#: directory holds tens of thousands of files (D-07).
CHUNK_SHARD_LEN = 2


@dataclass(frozen=True, slots=True)
class ProjectLayout:
    """Every path inside one project, derived from its root."""

    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / MANIFEST_NAME

    @property
    def db(self) -> Path:
        return self.root / DB_NAME

    @property
    def lock(self) -> Path:
        return self.root / LOCK_NAME

    @property
    def source(self) -> Path:
        return self.root / "source"

    @property
    def working_epub(self) -> Path:
        return self.source / "working.epub"

    @property
    def reader(self) -> Path:
        return self.root / "reader"

    @property
    def voices(self) -> Path:
        return self.root / "voices"

    @property
    def audio(self) -> Path:
        return self.root / "audio"

    @property
    def chunks(self) -> Path:
        return self.audio / "chunks"

    @property
    def quarantine(self) -> Path:
        """Torn writes land here instead of being trusted again (DATA_MODEL.md §9.1)."""
        return self.audio / "quarantine"

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    def chunk_wav(self, render_key: str) -> Path:
        return self.chunks / render_key[:CHUNK_SHARD_LEN] / f"{render_key}.wav"

    def chunk_sidecar(self, render_key: str) -> Path:
        return self.chunks / render_key[:CHUNK_SHARD_LEN] / f"{render_key}.json"

    def job_dir(self, job_id: str) -> Path:
        return self.jobs / job_id

    def ensure_dirs(self) -> None:
        for directory in (
            self.root,
            self.source,
            self.reader,
            self.voices,
            self.chunks,
            self.quarantine,
            self.jobs,
            self.output,
            self.cache,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def relative(self, path: Path) -> str:
        """A project-relative POSIX path, which is what the database stores."""
        return path.relative_to(self.root).as_posix()


def layout_for(root: Path) -> ProjectLayout:
    return ProjectLayout(root=root)


def find_project_dirs(projects_dir: Path) -> list[Path]:
    """Directories that look like a project: they contain ``project.json``.

    Sorted by name so the Library listing is stable between calls.
    """
    if not projects_dir.is_dir():
        return []
    return sorted(
        (child for child in projects_dir.iterdir() if (child / MANIFEST_NAME).is_file()),
        key=lambda path: path.name,
    )
