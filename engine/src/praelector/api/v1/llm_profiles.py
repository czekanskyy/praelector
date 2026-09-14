# SPDX-License-Identifier: Apache-2.0
"""API endpoints for LLM profile configuration and connection testing (LM-01, LM-02, LM-04)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from praelector.api.deps import get_settings_store
from praelector.domain.models import (
    LlmProfile,
    LlmProfileCreate,
    LlmProfilePatch,
    LlmTestResponse,
    TaskRouting,
)
from praelector.errors import PraelectorError
from praelector.llm.router import LlmRouter
from praelector.store.settings import SettingsStore

router = APIRouter(prefix="/settings", tags=["llm"])


@router.get("/llm-profiles", response_model=list[LlmProfile])
def list_llm_profiles(
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> list[LlmProfile]:
    """List configured LLM profiles with secrets masked (LM-01, LM-03)."""
    return settings_store.list_profiles()


@router.post("/llm-profiles", response_model=LlmProfile, status_code=201)
def create_llm_profile(
    payload: LlmProfileCreate,
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> LlmProfile:
    """Create a new LLM provider profile. Secrets are written directly to keyring (LM-01, LM-03)."""
    return settings_store.create_profile(payload)


@router.patch("/llm-profiles/{profile_id}", response_model=LlmProfile)
def patch_llm_profile(
    profile_id: str,
    payload: LlmProfilePatch,
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> LlmProfile:
    """Update an existing LLM provider profile."""
    return settings_store.update_profile(profile_id, payload)


@router.delete("/llm-profiles/{profile_id}", status_code=204)
def delete_llm_profile(
    profile_id: str,
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> None:
    """Delete an LLM provider profile and remove its secret from keyring."""
    settings_store.delete_profile(profile_id)


@router.post("/llm-profiles/{profile_id}/test", response_model=LlmTestResponse)
async def test_llm_profile(
    profile_id: str,
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> LlmTestResponse:
    """Test connection and measure latency for an LLM profile (LM-02)."""
    profile = settings_store.get_profile(profile_id)
    if profile is None:
        raise PraelectorError(
            code="settings.profile_not_found",
            message=f"LLM profile '{profile_id}' not found",
        )

    router_inst = LlmRouter(settings_store=settings_store, secret_store=settings_store.secrets)
    client = router_inst.get_client_for_profile(profile)
    res = await client.test_connection()
    return LlmTestResponse(
        ok=res.ok,
        latency_ms=res.latency_ms,
        models=res.models,
        error=res.error,
    )


@router.get("/task-routing", response_model=TaskRouting)
def get_task_routing(
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> TaskRouting:
    """Get mapping of LLM tasks to configured profiles (LM-04)."""
    return settings_store.get_task_routing()


@router.put("/task-routing", response_model=TaskRouting)
def update_task_routing(
    payload: TaskRouting,
    settings_store: Annotated[SettingsStore, Depends(get_settings_store)],
) -> TaskRouting:
    """Update mapping of LLM tasks to configured profiles (LM-04)."""
    return settings_store.update_task_routing(payload)
