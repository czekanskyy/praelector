# SPDX-License-Identifier: Apache-2.0
"""Per-task LLM routing, cloud policy enforcement, and schema validation with retry (LM-04, LM-05, AI-03, AI-10)."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx

from praelector.domain.models import LlmProfile
from praelector.errors import PraelectorError
from praelector.llm.protocol import LlmClient, LlmCompletionResponse, LlmMessage, LlmRole
from praelector.llm.providers.anthropic import AnthropicClient
from praelector.llm.providers.gemini import GeminiClient
from praelector.llm.providers.openai_compat import OpenAiCompatibleClient
from praelector.llm.schemas import TASK_SCHEMAS, get_task_schema
from praelector.llm.secrets import get_profile_api_key
from praelector.llm.usage import LlmUsageTracker
from praelector.store.secrets import SecretStore
from praelector.store.settings import SettingsStore


def build_bounded_context(
    target_block: str,
    prev_block: str | None = None,
    next_block: str | None = None,
    max_chars_per_side: int = 1200,
) -> str:
    """Construct bounded context window for AI-03 (target block ± 1 block, max 1200 chars/side)."""
    parts: list[str] = []
    if prev_block:
        trimmed_prev = prev_block[-max_chars_per_side:].strip()
        if trimmed_prev:
            parts.append(f"[PREVIOUS CONTEXT]\n{trimmed_prev}")

    parts.append(f"[TARGET BLOCK]\n{target_block.strip()}")

    if next_block:
        trimmed_next = next_block[:max_chars_per_side].strip()
        if trimmed_next:
            parts.append(f"[NEXT CONTEXT]\n{trimmed_next}")

    return "\n\n".join(parts)


class LlmRouter:
    """Manages profile selection, cloud toggles, failovers, and validated task execution."""

    def __init__(
        self,
        settings_store: SettingsStore,
        secret_store: SecretStore,
        usage_tracker: LlmUsageTracker | None = None,
    ) -> None:
        self.settings_store = settings_store
        self.secret_store = secret_store
        self.usage_tracker = usage_tracker

    def get_client_for_profile(self, profile: LlmProfile) -> LlmClient:
        """Instantiate the appropriate LlmClient adapter for a configured profile."""
        api_key = get_profile_api_key(self.secret_store, profile.id)

        kind_lower = profile.kind.lower()
        if kind_lower == "anthropic":
            return AnthropicClient(
                model=profile.model,
                api_key=api_key,
                base_url=profile.base_url,
                timeout_s=float(profile.timeout_s),
                max_tokens=profile.max_tokens,
            )
        elif kind_lower == "gemini":
            return GeminiClient(
                model=profile.model,
                api_key=api_key,
                base_url=profile.base_url,
                timeout_s=float(profile.timeout_s),
                max_tokens=profile.max_tokens,
            )
        else:
            # Default to OpenAI-compatible (Ollama, LM Studio, Groq, OpenRouter, etc.)
            return OpenAiCompatibleClient(
                base_url=profile.base_url,
                model=profile.model,
                api_key=api_key,
                timeout_s=float(profile.timeout_s),
                max_tokens=profile.max_tokens,
                supports_json_schema=profile.supports_json_schema,
            )

    def resolve_profile_for_task(
        self,
        task_key: str,
        cloud_llm_enabled: bool,
    ) -> tuple[LlmProfile, LlmClient]:
        """Resolve the target profile for a task obeying cloud permissions and fallbacks."""
        settings = self.settings_store.get_settings()
        routing = settings.task_routing

        # Determine target profile ID
        profile_id = getattr(routing, task_key, None)
        profile = next((p for p in settings.llm_profiles if p.id == profile_id), None)

        if profile is None and settings.llm_profiles:
            profile = settings.llm_profiles[0]

        if profile is None:
            raise PraelectorError(
                code="llm.no_profile_configured",
                message=f"No LLM profile configured for task '{task_key}'",
            )

        # Cloud policy check (LM-05, NF-02)
        if profile.is_cloud and not cloud_llm_enabled:
            # Look for a local profile as silent fallback
            local_profile = next((p for p in settings.llm_profiles if not p.is_cloud), None)
            if local_profile is not None:
                profile = local_profile
            else:
                raise PraelectorError(
                    code="llm.cloud_disabled",
                    message="Cloud LLM profile required but project cloud_llm_enabled toggle is disabled.",
                )

        client = self.get_client_for_profile(profile)
        return profile, client

    async def execute_task(
        self,
        task_key: str,
        messages: list[LlmMessage],
        project_id: str,
        cloud_llm_enabled: bool = False,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Execute a task with schema validation and one retry on invalid output (AI-03, D-15).

        Returns:
            (validated_dict, None) on success
            (None, error_code) on failure (e.g. "llm.invalid_json")
        """
        profile, client = self.resolve_profile_for_task(task_key, cloud_llm_enabled)
        schema = get_task_schema(task_key)
        model_cls = TASK_SCHEMAS.get(task_key)

        async def _call(
            active_client: LlmClient, msg_list: list[LlmMessage]
        ) -> LlmCompletionResponse:
            try:
                return await active_client.chat_completion(msg_list, schema=schema)
            except httpx.HTTPStatusError as e:
                # Failover offer on 429 or 5xx from cloud (AI-10)
                if profile.is_cloud and e.response.status_code in (429, 500, 502, 503, 504):
                    settings = self.settings_store.get_settings()
                    local_prof = next((p for p in settings.llm_profiles if not p.is_cloud), None)
                    if local_prof is not None:
                        local_client = self.get_client_for_profile(local_prof)
                        return await local_client.chat_completion(msg_list, schema=schema)
                raise

        try:
            # 1. First attempt
            resp = await _call(client, messages)
            if self.usage_tracker and resp.usage:
                self.usage_tracker.record(project_id, profile.id, task_key, resp.usage)

            # Validate response
            parsed_dict = self._validate_response(resp, model_cls)
            if parsed_dict is not None:
                return parsed_dict, None

            # 2. Retry once with error feedback (AI-03)
            retry_messages = list(messages)
            retry_messages.append(LlmMessage(role=LlmRole.ASSISTANT, content=resp.content))
            retry_messages.append(
                LlmMessage(
                    role=LlmRole.USER,
                    content=(
                        "Your previous response was not valid JSON conforming to the requested schema. "
                        "Please output strictly valid JSON matching the schema."
                    ),
                )
            )

            retry_resp = await _call(client, retry_messages)
            if self.usage_tracker and retry_resp.usage:
                self.usage_tracker.record(project_id, profile.id, task_key, retry_resp.usage)

            retry_dict = self._validate_response(retry_resp, model_cls)
            if retry_dict is not None:
                return retry_dict, None

            # Two failed attempts -> report llm.invalid_json
            return None, "llm.invalid_json"

        except Exception:
            return None, "llm.request_failed"

    def _validate_response(
        self,
        resp: LlmCompletionResponse,
        model_cls: type[Any] | None,
    ) -> dict[str, Any] | None:
        """Validate LLM output against Pydantic model class."""
        data_to_validate: Any = resp.raw_json
        if data_to_validate is None and resp.content:
            try:
                data_to_validate = json.loads(resp.content)
            except Exception:
                return None

        if data_to_validate is None:
            return None

        if model_cls is not None:
            try:
                validated = model_cls.model_validate(data_to_validate)
                return cast(dict[str, Any], validated.model_dump())
            except Exception:
                return None

        return dict(data_to_validate) if isinstance(data_to_validate, dict) else None
