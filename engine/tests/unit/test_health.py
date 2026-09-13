# SPDX-License-Identifier: Apache-2.0
"""Unit tests for /v1/health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint_success(authed_client: TestClient) -> None:
    response = authed_client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["uptime_s"], (int, float))
    assert data["project_open"] is False
    assert data["active_job_id"] is None
