# SPDX-License-Identifier: Apache-2.0
"""FastAPI request dependencies for service injection."""

from __future__ import annotations

from fastapi import Request

from praelector.jobs.manager import JobManager
from praelector.llm.router import LlmRouter
from praelector.store.project_manager import ProjectManager
from praelector.store.settings import SettingsStore


def get_settings_store(request: Request) -> SettingsStore:
    """Retrieve SettingsStore instance from application state."""
    return request.app.state.settings_store  # type: ignore[no-any-return]


def get_project_manager(request: Request) -> ProjectManager:
    """Retrieve ProjectManager instance from application state."""
    return request.app.state.project_manager  # type: ignore[no-any-return]


def get_job_manager(request: Request) -> JobManager:
    """Retrieve JobManager instance from application state."""
    return request.app.state.job_manager  # type: ignore[no-any-return]


def get_llm_router(request: Request) -> LlmRouter:
    """Retrieve LlmRouter instance from application state."""
    return request.app.state.llm_router  # type: ignore[no-any-return]
