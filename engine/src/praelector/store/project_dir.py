# SPDX-License-Identifier: Apache-2.0
"""Project directory layout and filesystem structure management."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    """Strongly-typed directory layout for a Praelector project."""

    root: Path
    manifest: Path
    db: Path
    lock: Path
    source_dir: Path
    voices_dir: Path
    audio_dir: Path
    chunks_dir: Path
    quarantine_dir: Path
    jobs_dir: Path
    output_dir: Path


def get_project_paths(root: Path | str) -> ProjectPaths:
    """Resolve standard paths within a project root directory."""
    root_path = Path(root).resolve()
    audio = root_path / "audio"

    return ProjectPaths(
        root=root_path,
        manifest=root_path / "project.json",
        db=root_path / "project.db",
        lock=root_path / "project.lock",
        source_dir=root_path / "source",
        voices_dir=root_path / "voices",
        audio_dir=audio,
        chunks_dir=audio / "chunks",
        quarantine_dir=audio / "quarantine",
        jobs_dir=root_path / "jobs",
        output_dir=root_path / "output",
    )


def create_project_dir(root: Path | str) -> ProjectPaths:
    """Create the physical directory skeleton for a project."""
    paths = get_project_paths(root)

    paths.root.mkdir(parents=True, exist_ok=True)
    paths.source_dir.mkdir(exist_ok=True)
    paths.voices_dir.mkdir(exist_ok=True)
    paths.audio_dir.mkdir(exist_ok=True)
    paths.chunks_dir.mkdir(exist_ok=True)
    paths.quarantine_dir.mkdir(exist_ok=True)
    paths.jobs_dir.mkdir(exist_ok=True)
    paths.output_dir.mkdir(exist_ok=True)

    return paths


def is_project_dir(root: Path | str) -> bool:
    """Check whether a directory contains a Praelector project manifest."""
    root_path = Path(root).resolve()
    manifest_path = root_path / "project.json"
    return manifest_path.is_file()


def list_project_dirs(projects_parent_dir: Path | str) -> list[Path]:
    """Scan a parent directory for valid Praelector project directories."""
    parent = Path(projects_parent_dir).resolve()
    if not parent.is_dir():
        return []

    results: list[Path] = []
    try:
        for entry in parent.iterdir():
            if entry.is_dir() and is_project_dir(entry):
                results.append(entry)
    except OSError:
        pass
    return sorted(results, key=lambda p: p.name.lower())
