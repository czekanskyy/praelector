# SPDX-License-Identifier: Apache-2.0
"""Unit tests for token auth and Origin allowlist."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_missing_auth_header(client: TestClient) -> None:
    response = client.get("/v1/health")
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "auth.unauthorized"
    assert "trace_id" in error


def test_invalid_token(client: TestClient) -> None:
    response = client.get("/v1/health", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "auth.unauthorized"


def test_valid_token(client: TestClient, test_settings: object) -> None:
    token = test_settings.token
    response = client.get("/v1/health", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_valid_origin(authed_client: TestClient) -> None:
    response = authed_client.get("/v1/health", headers={"Origin": "tauri://localhost"})
    assert response.status_code == 200

    response_dev = authed_client.get("/v1/health", headers={"Origin": "http://localhost:1420"})
    assert response_dev.status_code == 200


def test_forbidden_origin(authed_client: TestClient) -> None:
    response = authed_client.get("/v1/health", headers={"Origin": "https://malicious-website.com"})
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "auth.forbidden_origin"
