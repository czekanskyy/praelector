# SPDX-License-Identifier: Apache-2.0
"""Settings and capability probes (OPENAPI_SKETCH.md §1-§2, MX-04, EB-03)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from praelector.config import (
    BinaryProbe,
    Settings,
    SettingsStore,
    probe_calibre,
    probe_ffmpeg,
    probe_keyring,
)
from praelector.state import AppState, get_state
from praelector.store.secrets import SecretBackend

router = APIRouter(tags=["settings"])


class BinaryProbeModel(BaseModel):
    """One external binary. ``reason`` is a stable code, never prose (D-16)."""

    present: bool
    path: str | None = None
    version: str | None = None
    reason: str | None = None

    @classmethod
    def of(cls, probe: BinaryProbe) -> BinaryProbeModel:
        return cls(
            present=probe.present,
            path=probe.path,
            version=probe.version,
            reason=probe.reason,
        )


class PathsModel(BaseModel):
    """Where this installation keeps things, so the Settings screen can show it."""

    data_dir: str
    config_dir: str
    log_dir: str
    projects_dir: str
    models_dir: str
    runtimes_dir: str
    bin_dir: str


class CapabilitiesResponse(BaseModel):
    ffmpeg: BinaryProbeModel
    calibre: BinaryProbeModel
    keyring_backend: str
    #: ``file`` means secrets are obfuscated on disk rather than in the OS store;
    #: the UI must say so (LM-03).
    secret_backend: SecretBackend
    paths: PathsModel
    #: Set when ``config.json`` could not be read and defaults were used instead.
    settings_error: str | None = None


@router.get("/settings", response_model=Settings)
async def get_settings(state: AppState = Depends(get_state)) -> Settings:
    return state.settings_store.load()


@router.put("/settings", response_model=Settings)
async def put_settings(
    changes: dict[str, Any] = Body(..., description="RFC 7386 merge patch"),
    state: AppState = Depends(get_state),
) -> Settings:
    """Merge-patch the settings tree.

    Paths are re-resolved and the capability probes are dropped, because the patch
    may have moved ``projects_dir`` or pointed ``ffmpeg_path`` somewhere else.
    """
    settings = state.settings_store.patch(changes)
    state.env.apply_settings(settings)
    # Both hold a snapshot of the old paths; the stores are cheap to rebuild and
    # `ProjectStore` deliberately is not, because it owns the open project's lock.
    state.settings_store = SettingsStore(state.env.paths)
    state.capabilities_cache = None
    return settings


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities(state: AppState = Depends(get_state)) -> CapabilitiesResponse:
    """Probed once per settings change; the probes spawn subprocesses."""
    if state.capabilities_cache is not None:
        return state.capabilities_cache

    settings = state.env.settings
    paths = state.env.paths
    response = CapabilitiesResponse(
        ffmpeg=BinaryProbeModel.of(probe_ffmpeg(settings, paths)),
        calibre=BinaryProbeModel.of(probe_calibre(settings)),
        keyring_backend=probe_keyring(),
        secret_backend=state.secrets.backend,
        paths=PathsModel(
            data_dir=paths.data_dir.as_posix(),
            config_dir=paths.config_dir.as_posix(),
            log_dir=paths.log_dir.as_posix(),
            projects_dir=paths.projects_dir.as_posix(),
            models_dir=paths.models_dir.as_posix(),
            runtimes_dir=paths.runtimes_dir.as_posix(),
            bin_dir=paths.bin_dir.as_posix(),
        ),
        settings_error=state.env.settings_error,
    )
    state.capabilities_cache = response
    return response
