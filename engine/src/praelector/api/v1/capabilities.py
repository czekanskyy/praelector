# SPDX-License-Identifier: Apache-2.0
"""System capabilities probe endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from praelector.api.deps import get_settings_store
from praelector.domain.models import CapabilitiesResponse
from praelector.probes import probe_all_capabilities
from praelector.store.settings import SettingsStore

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
def get_capabilities(
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> CapabilitiesResponse:
    """Probe installed CLI tools (ffmpeg, calibre), keyring backend, and TTS runtimes."""
    return probe_all_capabilities(settings_store.data_dir)
