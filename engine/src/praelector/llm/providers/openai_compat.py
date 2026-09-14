# SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible LLM client adapter (LM-01, LM-02).

Serves Ollama, LM Studio, OpenAI, Groq, OpenRouter, xAI, and generic OpenAI-compatible APIs.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from praelector.llm.protocol import (
    LlmClient,
    LlmCompletionResponse,
    LlmMessage,
    LlmTestResult,
    LlmUsage,
)


class OpenAiCompatibleClient(LlmClient):
    """Adapter for endpoints implementing the OpenAI chat completions REST protocol."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 120.0,
        max_tokens: int = 1024,
        supports_json_schema: bool = True,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.supports_json_schema = supports_json_schema
        self._client = http_client

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat_completion(
        self,
        messages: list[LlmMessage],
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> LlmCompletionResponse:
        """Execute chat completion request against /chat/completions."""
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }

        if schema is not None:
            if self.supports_json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_output",
                        "strict": True,
                        "schema": schema,
                    },
                }
            else:
                payload["response_format"] = {"type": "json_object"}

        client = self._client or httpx.AsyncClient(timeout=self.timeout_s)
        try:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()

            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")

            # Extract raw json if parseable
            raw_json: dict[str, Any] | None = None
            if schema is not None and content:
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        raw_json = parsed
                except Exception:
                    pass

            usage_data = data.get("usage", {})
            usage = LlmUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
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
        """Test connectivity and measure roundtrip latency (LM-02)."""
        start = time.perf_counter()
        client = self._client or httpx.AsyncClient(timeout=min(self.timeout_s, 15.0))
        try:
            # First attempt: GET /models
            models_url = f"{self.base_url}/models"
            try:
                resp = await client.get(models_url, headers=self._get_headers())
                latency_ms = (time.perf_counter() - start) * 1000.0
                if resp.status_code == 200:
                    data = resp.json()
                    model_list: list[str] = []
                    for item in data.get("data", []):
                        if isinstance(item, dict) and "id" in item:
                            model_list.append(str(item["id"]))
                        elif isinstance(item, str):
                            model_list.append(item)
                    return LlmTestResult(
                        ok=True,
                        latency_ms=round(latency_ms, 1),
                        models=model_list[:50],
                    )
            except Exception:
                pass

            # Fallback attempt: minimalist completion
            test_resp = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
                headers=self._get_headers(),
            )
            latency_ms = (time.perf_counter() - start) * 1000.0
            test_resp.raise_for_status()
            return LlmTestResult(
                ok=True,
                latency_ms=round(latency_ms, 1),
                models=[self.model],
            )
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
