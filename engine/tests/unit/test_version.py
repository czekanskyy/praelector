# SPDX-License-Identifier: Apache-2.0
"""Unit tests for /v1/version endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

import praelector


def test_version_endpoint_success(authed_client: TestClient) -> None:
    response = authed_client.get("/v1/version")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "0.1.0"
    assert data["engine"] == praelector.__version__
    assert data["schema"] == 1
    assert "python" in data
    assert "platform" in data
