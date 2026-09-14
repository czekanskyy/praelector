# SPDX-License-Identifier: Apache-2.0
"""Unit and API tests for LLM profile settings, secrets masking, and connection testing (LM-01..LM-04)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from praelector.app import create_app
from praelector.config import Settings
from praelector.llm.protocol import LlmTestResult


def test_llm_profiles_api_lifecycle(tmp_path: Path) -> None:
    token = "secret-token-1234567890123456"
    test_settings = Settings(
        port=0,
        token=token,
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_level="INFO",
    )

    app = create_app(test_settings)
    client = TestClient(app)
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "http://localhost:1420",
    }

    # 1. List default profiles
    res = client.get("/v1/settings/llm-profiles", headers=headers)
    assert res.status_code == 200
    profiles = res.json()
    assert len(profiles) >= 1
    # Secret must be masked (LM-03)
    assert "set" in profiles[0]["api_key"]
    assert "sk-" not in str(profiles[0]["api_key"])

    # 2. Create new profile with secret
    create_payload = {
        "name": "Groq Llama",
        "kind": "groq",
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
        "is_cloud": True,
        "api_key": "gsk_secret12345",
        "supports_json_schema": True,
    }
    create_res = client.post("/v1/settings/llm-profiles", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    created = create_res.json()
    prof_id = created["id"]
    assert created["name"] == "Groq Llama"
    assert created["api_key"]["set"] is True
    # Verify raw secret was NOT returned
    assert "gsk_secret12345" not in str(created)

    # 3. Patch profile
    patch_res = client.patch(
        f"/v1/settings/llm-profiles/{prof_id}",
        json={"timeout_s": 45.0},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["timeout_s"] == 45.0

    # 4. Connection test (mocked)
    with patch(
        "praelector.llm.providers.openai_compat.OpenAiCompatibleClient.test_connection",
        new_callable=AsyncMock,
    ) as mock_test:
        mock_test.return_value = LlmTestResult(
            ok=True, latency_ms=123.4, models=["llama-3.3-70b-versatile"]
        )
        test_res = client.post(f"/v1/settings/llm-profiles/{prof_id}/test", headers=headers)
        assert test_res.status_code == 200
        test_data = test_res.json()
        assert test_data["ok"] is True
        assert test_data["latency_ms"] == 123.4
        assert "llama-3.3-70b-versatile" in test_data["models"]

    # 5. Task routing GET and PUT
    routing_res = client.get("/v1/settings/task-routing", headers=headers)
    assert routing_res.status_code == 200

    put_routing_res = client.put(
        "/v1/settings/task-routing",
        json={"classify_cheap": prof_id, "dialogue_hard": prof_id, "pronounce": prof_id},
        headers=headers,
    )
    assert put_routing_res.status_code == 200
    updated_routing = put_routing_res.json()
    assert updated_routing["classify_cheap"] == prof_id
    assert updated_routing["dialogue_hard"] == prof_id

    # 6. Delete profile
    del_res = client.delete(f"/v1/settings/llm-profiles/{prof_id}", headers=headers)
    assert del_res.status_code == 204

    # Verify gone
    list_after = client.get("/v1/settings/llm-profiles", headers=headers).json()
    assert not any(p["id"] == prof_id for p in list_after)
