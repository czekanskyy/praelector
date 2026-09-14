# SPDX-License-Identifier: Apache-2.0
"""Praelector LLM module providing provider adapters, routing, and usage tracking."""

from __future__ import annotations

from praelector.llm.protocol import (
    LlmClient,
    LlmCompletionResponse,
    LlmMessage,
    LlmRole,
    LlmTestResult,
    LlmUsage,
)
from praelector.llm.providers.anthropic import AnthropicClient
from praelector.llm.providers.gemini import GeminiClient
from praelector.llm.providers.openai_compat import OpenAiCompatibleClient
from praelector.llm.router import LlmRouter, build_bounded_context
from praelector.llm.schemas import (
    TASK_SCHEMAS,
    ClassificationBatchResponse,
    DialogueSplitHardResponse,
    PronounceBatchResponse,
    get_task_schema,
)
from praelector.llm.secrets import delete_profile_api_key, get_profile_api_key, set_profile_api_key
from praelector.llm.usage import LlmUsageTracker

__all__ = [
    "AnthropicClient",
    "ClassificationBatchResponse",
    "DialogueSplitHardResponse",
    "GeminiClient",
    "LlmClient",
    "LlmCompletionResponse",
    "LlmMessage",
    "LlmRole",
    "LlmRouter",
    "LlmTestResult",
    "LlmUsage",
    "LlmUsageTracker",
    "OpenAiCompatibleClient",
    "PronounceBatchResponse",
    "TASK_SCHEMAS",
    "build_bounded_context",
    "delete_profile_api_key",
    "get_profile_api_key",
    "get_task_schema",
    "set_profile_api_key",
]
