# SPDX-License-Identifier: Apache-2.0
"""v1 routers. Mounted under ``/v1`` by ``praelector.app.create_app``."""

from __future__ import annotations

from praelector.api.v1 import chapters, gpu, health, ingest, jobs, projects, settings, ws

__all__ = ["chapters", "gpu", "health", "ingest", "jobs", "projects", "settings", "ws"]
