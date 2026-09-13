# SPDX-License-Identifier: Apache-2.0
"""Database repository implementations for Praelector entities."""

from __future__ import annotations

from praelector.store.repositories.chapters import ChapterRepository
from praelector.store.repositories.project import ProjectRepository

__all__ = [
    "ChapterRepository",
    "ProjectRepository",
]
