# SPDX-License-Identifier: Apache-2.0
"""Tests for the bearer token and the Origin allow-list (PLAN.md D-10)."""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers

from praelector.errors import AppError, ErrorCode
from praelector.security import (
    DEFAULT_ALLOWED_ORIGINS,
    AuthPolicy,
    bearer_token,
    generate_token,
)

TOKEN = "correct-horse-battery-staple"


@pytest.fixture
def policy() -> AuthPolicy:
    return AuthPolicy(token=TOKEN)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (f"Bearer {TOKEN}", TOKEN),
        (f"bearer {TOKEN}", TOKEN),
        (f"Bearer   {TOKEN}  ", TOKEN),
        ("Basic dXNlcjpwYXNz", None),
        ("Bearer ", None),
        ("Bearer", None),
        ("", None),
        (None, None),
    ],
)
def test_bearer_token_parsing(header: str | None, expected: str | None) -> None:
    assert bearer_token(header) == expected


def test_missing_and_wrong_tokens_are_distinguishable(policy: AuthPolicy) -> None:
    with pytest.raises(AppError) as missing:
        policy.check_token(None)
    with pytest.raises(AppError) as wrong:
        policy.check_token("not-the-token")
    assert missing.value.code is ErrorCode.AUTH_MISSING_TOKEN
    assert wrong.value.code is ErrorCode.AUTH_INVALID_TOKEN


def test_the_right_token_passes(policy: AuthPolicy) -> None:
    policy.check_token(TOKEN)


def test_a_request_without_an_origin_is_allowed(policy: AuthPolicy) -> None:
    # The Rust supervisor and curl send no Origin; only browsers do.
    policy.check_origin(None)


@pytest.mark.parametrize("origin", DEFAULT_ALLOWED_ORIGINS)
def test_allow_listed_origins_pass(policy: AuthPolicy, origin: str) -> None:
    policy.check_origin(origin)


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "https://localhost:1420",  # right host, wrong scheme
        "http://localhost:1421",
        "tauri://localhost.evil.example",
        "null",
    ],
)
def test_foreign_origins_are_rejected(policy: AuthPolicy, origin: str) -> None:
    with pytest.raises(AppError) as excinfo:
        policy.check_origin(origin)
    assert excinfo.value.code is ErrorCode.AUTH_ORIGIN_REJECTED
    assert excinfo.value.detail == {"origin": origin}


def test_origin_is_checked_before_the_token(policy: AuthPolicy) -> None:
    """A foreign page must not be able to probe whether a token is valid."""
    headers = Headers({"origin": "http://evil.example", "authorization": f"Bearer {TOKEN}"})
    with pytest.raises(AppError) as excinfo:
        policy.authorize(headers)
    assert excinfo.value.code is ErrorCode.AUTH_ORIGIN_REJECTED


def test_authorize_accepts_a_clean_request(policy: AuthPolicy) -> None:
    headers = Headers({"origin": "http://tauri.localhost", "authorization": f"Bearer {TOKEN}"})
    policy.authorize(headers)


def test_generated_tokens_are_unique_and_url_safe() -> None:
    tokens = {generate_token() for _ in range(200)}
    assert len(tokens) == 200
    assert all(len(token) >= 32 for token in tokens)
    assert all(char.isalnum() or char in "-_" for token in tokens for char in token)


def test_the_allow_list_covers_every_platform_shape() -> None:
    # Linux/macOS Tauri, Windows Tauri, and the Vite dev server.
    assert "tauri://localhost" in DEFAULT_ALLOWED_ORIGINS
    assert "http://tauri.localhost" in DEFAULT_ALLOWED_ORIGINS
    assert "http://localhost:1420" in DEFAULT_ALLOWED_ORIGINS
