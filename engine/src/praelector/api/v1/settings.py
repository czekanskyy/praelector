# SPDX-License-Identifier: Apache-2.0
"""Application configuration settings endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from praelector.api.deps import get_settings_store
from praelector.domain.models import AppSettings, SettingsUpdate
from praelector.store.settings import SettingsStore

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=AppSettings)
def get_settings(
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> AppSettings:
    """Retrieve full application configuration with secret fields masked (LM-03)."""
    return settings_store.get_settings()


@router.put("/settings", response_model=AppSettings)
def update_settings(
    update: SettingsUpdate,
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> AppSettings:
    """Update application configuration settings."""
    return settings_store.update_settings(update)
