# SPDX-License-Identifier: Apache-2.0
"""Protocol definitions for Praelector LLM integration (LM-01, LM-02)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class LlmRole(StrEnum):
    """Message role in an LLM conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LlmMessage(BaseModel):
    """Chat message exchanged with an LLM."""

    role: LlmRole = LlmRole.USER
    content: str


class LlmUsage(BaseModel):
    """Token usage counters returned by an LLM completion."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LlmTestResult(BaseModel):
    """Result of an LLM provider connection test (LM-02)."""

    ok: bool
    latency_ms: float = 0.0
    models: list[str] = Field(default_factory=list)
    error: str | None = None


class LlmCompletionResponse(BaseModel):
    """Normalized response from an LLM completion call."""

    content: str
    raw_json: dict[str, Any] | None = None
    usage: LlmUsage = Field(default_factory=LlmUsage)
    model: str | None = None


class LlmClient(Protocol):
    """Protocol for LLM provider adapters."""

    async def chat_completion(
        self,
        messages: list[LlmMessage],
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> LlmCompletionResponse:
        """Execute a chat completion request with optional structured JSON schema."""
        ...

    async def test_connection(self) -> LlmTestResult:
        """Execute a lightweight probe to test credentials and endpoint latency."""
        ...
