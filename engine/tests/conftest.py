# SPDX-License-Identifier: Apache-2.0
"""Test configuration and shared fixtures."""

from __future__ import annotations

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend

from praelector.app import create_app
from praelector.config import Settings


class InMemoryKeyring(KeyringBackend):
    """In-memory keyring for test isolation, preventing pollution of OS credentials."""

    priority = 1

    def __init__(self) -> None:
        self._passwords: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._passwords.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._passwords.pop((service, username), None)


@pytest.fixture(autouse=True)
def isolated_keyring(monkeypatch: pytest.MonkeyPatch) -> InMemoryKeyring:
    """Isolate OS keyring in all unit tests."""
    backend = InMemoryKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "set_password", backend.set_password)
    monkeypatch.setattr(keyring, "get_password", backend.get_password)
    monkeypatch.setattr(keyring, "delete_password", backend.delete_password)
    return backend


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
