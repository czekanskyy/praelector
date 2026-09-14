# SPDX-License-Identifier: Apache-2.0
"""Google Gemini LLM client adapter (LM-01, LM-02)."""

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


class GeminiClient(LlmClient):
    """Adapter for Google Gemini REST API."""

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        api_key: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com",
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
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        return headers

    async def chat_completion(
        self,
        messages: list[LlmMessage],
        schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> LlmCompletionResponse:
        """Execute chat completion request via :generateContent."""
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"

        system_instruction: dict[str, Any] | None = None
        system_texts: list[str] = []
        contents: list[dict[str, Any]] = []

        for m in messages:
            if m.role == LlmRole.SYSTEM:
                system_texts.append(m.content)
            else:
                gemini_role = "user" if m.role == LlmRole.USER else "model"
                contents.append(
                    {
                        "role": gemini_role,
                        "parts": [{"text": m.content}],
                    }
                )

        if system_texts:
            system_instruction = {"parts": [{"text": "\n\n".join(system_texts)}]}

        gen_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": self.max_tokens,
        }
        if schema is not None:
            gen_config["responseMimeType"] = "application/json"
            gen_config["responseSchema"] = schema

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": gen_config,
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        client = self._client or httpx.AsyncClient(timeout=self.timeout_s)
        try:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates", [])
            content = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                content = "".join(p.get("text", "") for p in parts)

            raw_json: dict[str, Any] | None = None
            if schema is not None and content:
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        raw_json = parsed
                except Exception:
                    pass

            meta = data.get("usageMetadata", {})
            prompt_tokens = meta.get("promptTokenCount", 0)
            completion_tokens = meta.get("candidatesTokenCount", 0)
            usage = LlmUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )

            return LlmCompletionResponse(
                content=content,
                raw_json=raw_json,
                usage=usage,
                model=self.model,
            )
        finally:
            if self._client is None:
                await client.aclose()

    async def test_connection(self) -> LlmTestResult:
        """Test Google Gemini API connectivity and credentials (LM-02)."""
        start = time.perf_counter()
        client = self._client or httpx.AsyncClient(timeout=min(self.timeout_s, 15.0))
        try:
            url = f"{self.base_url}/v1beta/models"
            resp = await client.get(url, headers=self._get_headers())
            latency_ms = (time.perf_counter() - start) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                models = [
                    str(m.get("name", "")).replace("models/", "")
                    for m in data.get("models", [])
                    if m.get("name")
                ]
                return LlmTestResult(
                    ok=True,
                    latency_ms=round(latency_ms, 1),
                    models=models[:20] if models else [self.model],
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
