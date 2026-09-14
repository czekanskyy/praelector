# SPDX-License-Identifier: Apache-2.0
"""Unit tests for LLM Router, bounded context, failover, and retry validation (LM-04, LM-05, AI-03, AI-10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from praelector.domain.models import (
    LlmProfile,
    LlmProfileCreate,
    TaskRouting,
)
from praelector.errors import PraelectorError
from praelector.llm.protocol import LlmClient, LlmCompletionResponse, LlmMessage, LlmRole, LlmUsage
from praelector.llm.router import LlmRouter, build_bounded_context
from praelector.llm.usage import LlmUsageTracker
from praelector.store.settings import SettingsStore


def test_build_bounded_context() -> None:
    """Verify context assembly and 1200 char window bounds (AI-03)."""
    target = "To be or not to be."
    prev_txt = "A" * 1500
    next_txt = "B" * 1500

    ctx = build_bounded_context(target, prev_block=prev_txt, next_block=next_txt, max_chars_per_side=1200)
    assert "[TARGET BLOCK]\nTo be or not to be." in ctx
    assert "[PREVIOUS CONTEXT]" in ctx
    assert "[NEXT CONTEXT]" in ctx

    # Prev block is capped to last 1200 chars
    assert len(prev_txt[-1200:]) == 1200
    assert prev_txt[-1200:] in ctx
    # Next block is capped to first 1200 chars
    assert len(next_txt[:1200]) == 1200
    assert next_txt[:1200] in ctx


def test_router_cloud_policy_and_fallback(tmp_path: Path) -> None:
    """Verify local-first privacy policy and fallback (LM-05, NF-02)."""
    settings_store = SettingsStore(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    router = LlmRouter(settings_store=settings_store, secret_store=settings_store.secrets)

    # Clear any default profiles so we test cleanly
    for p in settings_store.list_profiles():
        settings_store.delete_profile(p.id)

    # 1. Create a cloud profile and a local profile
    cloud_prof = settings_store.create_profile(
        LlmProfileCreate(
            name="OpenAI Cloud",
            kind="openai",
            model="gpt-4o-mini",
            is_cloud=True,
            api_key="sk-test-key",
        )
    )
    local_prof = settings_store.create_profile(
        LlmProfileCreate(
            name="Ollama Local",
            kind="ollama",
            model="llama3.2",
            is_cloud=False,
            base_url="http://localhost:11434/v1",
        )
    )

    # Route dialogue_hard to cloud profile
    settings_store.update_task_routing(TaskRouting(dialogue_hard=cloud_prof.id))

    # Case A: cloud_llm_enabled is True -> returns cloud profile
    prof, _ = router.resolve_profile_for_task("dialogue_hard", cloud_llm_enabled=True)
    assert prof.id == cloud_prof.id
    assert prof.is_cloud is True

    # Case B: cloud_llm_enabled is False, local exists -> falls back silently to local profile
    prof, _ = router.resolve_profile_for_task("dialogue_hard", cloud_llm_enabled=False)
    assert prof.id == local_prof.id
    assert prof.is_cloud is False

    # Case C: delete local profile, cloud_llm_enabled is False -> raises PraelectorError(code="llm.cloud_disabled")
    settings_store.delete_profile(local_prof.id)
    with pytest.raises(PraelectorError) as exc_info:
        router.resolve_profile_for_task("dialogue_hard", cloud_llm_enabled=False)
    assert exc_info.value.code == "llm.cloud_disabled"


@pytest.mark.asyncio
async def test_router_schema_validation_success_first_attempt(tmp_path: Path) -> None:
    """Task succeeds on first valid attempt and records token usage (LM-07, AI-03)."""
    settings_store = SettingsStore(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    usage_tracker = LlmUsageTracker(tmp_path / "usage.json")
    router = LlmRouter(settings_store=settings_store, secret_store=settings_store.secrets, usage_tracker=usage_tracker)

    local_prof = settings_store.create_profile(
        LlmProfileCreate(
            name="Local Llama",
            kind="ollama",
            model="llama3.2",
            is_cloud=False,
        )
    )
    settings_store.update_task_routing(TaskRouting(pronounce=local_prof.id))

    mock_client = AsyncMock(spec=LlmClient)
    mock_client.chat_completion.return_value = LlmCompletionResponse(
        content='{"items": [{"id": "item1", "original": "Walker", "spoken": "Łoker"}]}',
        raw_json={"items": [{"id": "item1", "original": "Walker", "spoken": "Łoker"}]},
        usage=LlmUsage(prompt_tokens=40, completion_tokens=15, total_tokens=55),
    )
    router.get_client_for_profile = lambda p: mock_client  # type: ignore[method-assign]

    messages = [LlmMessage(role=LlmRole.USER, content="Pronounce Walker")]
    result, error_code = await router.execute_task("pronounce", messages, project_id="prj_1", cloud_llm_enabled=False)

    assert error_code is None
    assert result is not None
    assert result["items"][0]["spoken"] == "Łoker"
    assert mock_client.chat_completion.call_count == 1

    usage = usage_tracker.get_project_usage("prj_1")
    assert usage["total_tokens"] == 55


@pytest.mark.asyncio
async def test_router_schema_validation_retry_and_failure(tmp_path: Path) -> None:
    """Invalid JSON is retried once; failure after two attempts yields llm.invalid_json (AI-03, D-15)."""
    settings_store = SettingsStore(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    router = LlmRouter(settings_store=settings_store, secret_store=settings_store.secrets)

    local_prof = settings_store.create_profile(
        LlmProfileCreate(
            name="Local Llama",
            kind="ollama",
            model="llama3.2",
            is_cloud=False,
        )
    )
    settings_store.update_task_routing(TaskRouting(pronounce=local_prof.id))

    # 1. Invalid on first attempt, valid on retry
    mock_client_recover = AsyncMock(spec=LlmClient)
    mock_client_recover.chat_completion.side_effect = [
        LlmCompletionResponse(content="Sorry, here is the text without json"),
        LlmCompletionResponse(
            content='{"items": [{"id": "item1", "original": "test", "spoken": "test"}]}',
            raw_json={"items": [{"id": "item1", "original": "test", "spoken": "test"}]},
        ),
    ]
    router.get_client_for_profile = lambda p: mock_client_recover  # type: ignore[method-assign]

    messages = [LlmMessage(role=LlmRole.USER, content="Pronounce test")]
    res_rec, err_rec = await router.execute_task("pronounce", messages, project_id="prj_1")
    assert err_rec is None
    assert res_rec is not None
    assert mock_client_recover.chat_completion.call_count == 2

    # 2. Invalid on both attempts -> returns (None, 'llm.invalid_json')
    mock_client_fail = AsyncMock(spec=LlmClient)
    mock_client_fail.chat_completion.side_effect = [
        LlmCompletionResponse(content="Still plain text"),
        LlmCompletionResponse(content="Another non-json output"),
    ]
    router.get_client_for_profile = lambda p: mock_client_fail  # type: ignore[method-assign]

    res_fail, err_fail = await router.execute_task("pronounce", messages, project_id="prj_1")
    assert res_fail is None
    assert err_fail == "llm.invalid_json"
    assert mock_client_fail.chat_completion.call_count == 2


@pytest.mark.asyncio
async def test_router_failover_on_http_error(tmp_path: Path) -> None:
    """When a cloud provider returns 429/5xx, router fails over to local profile (AI-10)."""
    settings_store = SettingsStore(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    router = LlmRouter(settings_store=settings_store, secret_store=settings_store.secrets)

    cloud_prof = settings_store.create_profile(
        LlmProfileCreate(
            name="Cloud LLM",
            kind="openai",
            model="gpt-4o",
            is_cloud=True,
            api_key="sk-cloud",
        )
    )
    local_prof = settings_store.create_profile(
        LlmProfileCreate(
            name="Local Fallback",
            kind="ollama",
            model="llama3.2",
            is_cloud=False,
        )
    )
    settings_store.update_task_routing(TaskRouting(pronounce=cloud_prof.id))

    cloud_client = AsyncMock(spec=LlmClient)
    # Simulate HTTP 429 Rate Limit from cloud provider
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(429, request=req)
    cloud_client.chat_completion.side_effect = httpx.HTTPStatusError("Rate limited", request=req, response=resp)

    local_client = AsyncMock(spec=LlmClient)
    local_client.chat_completion.return_value = LlmCompletionResponse(
        content='{"items": [{"id": "1", "original": "city", "spoken": "siti"}]}',
        raw_json={"items": [{"id": "1", "original": "city", "spoken": "siti"}]},
    )

    def _client_factory(p: LlmProfile) -> LlmClient:
        return cloud_client if p.id == cloud_prof.id else local_client

    router.get_client_for_profile = _client_factory  # type: ignore[method-assign]

    messages = [LlmMessage(role=LlmRole.USER, content="Pronounce city")]
    result, error_code = await router.execute_task("pronounce", messages, project_id="prj_1", cloud_llm_enabled=True)

    assert error_code is None
    assert result is not None
    assert result["items"][0]["spoken"] == "siti"
    assert cloud_client.chat_completion.call_count == 1
    assert local_client.chat_completion.call_count == 1
