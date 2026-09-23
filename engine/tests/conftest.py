# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures. Every path is under tmp_path so tests never touch real state."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from praelector.app import create_app
from praelector.config import (
    ENV_CONFIG_DIR,
    ENV_DATA_DIR,
    ENV_HOST,
    ENV_LOG_DIR,
    ENV_LOG_LEVEL,
    ENV_PORT,
    ENV_PROJECTS_DIR,
    ENV_TOKEN,
    RuntimeEnv,
    load_runtime_env,
)
from praelector.state import AppState

TEST_TOKEN = "test-token-0123456789abcdefghijklmnopqrstuvwxyz"


@pytest.fixture
def runtime_env(tmp_path: Path) -> RuntimeEnv:
    return load_runtime_env(
        {
            ENV_TOKEN: TEST_TOKEN,
            ENV_HOST: "127.0.0.1",
            ENV_PORT: "0",
            ENV_LOG_LEVEL: "DEBUG",
            ENV_DATA_DIR: os.fspath(tmp_path / "data"),
            ENV_CONFIG_DIR: os.fspath(tmp_path / "config"),
            ENV_LOG_DIR: os.fspath(tmp_path / "logs"),
            ENV_PROJECTS_DIR: os.fspath(tmp_path / "projects"),
        }
    )


@pytest.fixture
def app(runtime_env: RuntimeEnv) -> FastAPI:
    return create_app(runtime_env)


@pytest.fixture
def app_state(app: FastAPI) -> AppState:
    state: AppState = app.state.praelector
    return state


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager runs the lifespan, which attaches the event loop to the
    # bus — without it WebSocket delivery silently does nothing.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def token() -> str:
    return TEST_TOKEN
