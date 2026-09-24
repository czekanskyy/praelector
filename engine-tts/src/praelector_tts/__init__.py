# SPDX-License-Identifier: Apache-2.0
"""Praelector TTS worker: model loading and synthesis behind a stdio protocol.

This package knows nothing about projects, SQLite or HTTP (REPO_LAYOUT.md §6).
It must stay importable with no extra installed, so ``torch`` is imported lazily
and only inside ``device``/``vram``/real backends.
"""

from __future__ import annotations

__version__ = "0.2.0"

__all__ = ["__version__"]
