# SPDX-License-Identifier: Apache-2.0
"""Anthropic Claude LLM client adapter (LM-01, LM-02)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from praelector.llm.protocol import (
    LlmClient,
    LlmCompletionResponse,
    LlmMessage,
    LlmRole,
    LlmTestResult,
    LlmUsage,
)


class AnthropicClient(LlmClient):
    """Adapter for Anthropic messages API."""

    def __init__(
        self,
        model: str = "claude-3-5-haiku-20241022",
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com",
        timeout_s: float = 120.0,
        max_tokens: int = 1024,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self._client = http_client

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    async def chat_completion(
        self,
        messages: list[LlmMessage],
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> LlmCompletionResponse:
        """Execute chat completion request via /v1/messages."""
        url = f"{self.base_url}/v1/messages"

        # Separate system messages from user/assistant messages
        system_parts: list[str] = []
        anthropic_messages: list[dict[str, str]] = []
        for m in messages:
            if m.role == LlmRole.SYSTEM:
                system_parts.append(m.content)
            else:
                anthropic_messages.append(
                    {
                        "role": "user" if m.role == LlmRole.USER else "assistant",
                        "content": m.content,
                    }
                )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        if schema is not None:
            # Use tool calling for guaranteed structured output
            payload["tools"] = [
                {
                    "name": "emit_structured_output",
                    "description": "Output structured JSON matching the schema.",
                    "input_schema": schema,
                }
            ]
            payload["tool_choice"] = {"type": "tool", "name": "emit_structured_output"}

        client = self._client or httpx.AsyncClient(timeout=self.timeout_s)
        try:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()

            content = ""
            raw_json: dict[str, Any] | None = None

            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text", "")
                elif block.get("type") == "tool_use":
                    tool_input = block.get("input", {})
                    if isinstance(tool_input, dict):
                        raw_json = tool_input
                        content = json.dumps(tool_input, ensure_ascii=False)

            # Fallback JSON parsing if tool_use wasn't populated but text was
            if raw_json is None and schema is not None and content:
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        raw_json = parsed
                except Exception:
                    pass

            usage_data = data.get("usage", {})
            prompt_tokens = usage_data.get("input_tokens", 0)
            completion_tokens = usage_data.get("output_tokens", 0)
            usage = LlmUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )

            return LlmCompletionResponse(
                content=content,
                raw_json=raw_json,
                usage=usage,
                model=data.get("model", self.model),
            )
        finally:
            if self._client is None:
                await client.aclose()

    async def test_connection(self) -> LlmTestResult:
        """Test Anthropic API connectivity and credentials (LM-02)."""
        start = time.perf_counter()
        client = self._client or httpx.AsyncClient(timeout=min(self.timeout_s, 15.0))
        try:
            url = f"{self.base_url}/v1/models"
            resp = await client.get(url, headers=self._get_headers())
            latency_ms = (time.perf_counter() - start) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                models = [str(item.get("id")) for item in data.get("data", []) if item.get("id")]
                return LlmTestResult(
                    ok=True,
                    latency_ms=round(latency_ms, 1),
                    models=models[:20] if models else [self.model],
                )
            elif resp.status_code == 404:
                # Fallback to minimal ping
                ping_resp = await client.post(
                    f"{self.base_url}/v1/messages",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5,
                    },
                    headers=self._get_headers(),
                )
                latency_ms = (time.perf_counter() - start) * 1000.0
                ping_resp.raise_for_status()
                return LlmTestResult(
                    ok=True,
                    latency_ms=round(latency_ms, 1),
                    models=[self.model],
                )
            else:
                resp.raise_for_status()
                return LlmTestResult(ok=True, latency_ms=round(latency_ms, 1), models=[self.model])
        except httpx.HTTPStatusError as e:
            latency_ms = (time.perf_counter() - start) * 1000.0
            return LlmTestResult(
                ok=False,
                latency_ms=round(latency_ms, 1),
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000.0
            return LlmTestResult(
                ok=False,
                latency_ms=round(latency_ms, 1),
                error=str(e),
            )
        finally:
            if self._client is None:
                await client.aclose()
