# SPDX-License-Identifier: Apache-2.0
"""Test configuration and shared fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from praelector.app import create_app
from praelector.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        token="test-secret-token-1234567890",
        log_level="DEBUG",
        allowed_origins=["tauri://localhost", "http://localhost:1420"],
    )


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    app = create_app(test_settings)
    return TestClient(app)


@pytest.fixture
def authed_client(client: TestClient, test_settings: Settings) -> TestClient:
    client.headers.update({"Authorization": f"Bearer {test_settings.token}"})
    return client
