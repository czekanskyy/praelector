# SPDX-License-Identifier: Apache-2.0
"""Unit tests for error handling and envelopes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from praelector.errors import AppError


def test_not_found_envelope(authed_client: TestClient) -> None:
    response = authed_client.get("/v1/non-existent-endpoint")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "internal.not_found"
    assert "trace_id" in data["error"]


def test_custom_app_error() -> None:
    err = AppError(
        code="ebook.drm_detected",
        status_code=422,
        detail={"files": ["content.opf"]},
        retryable=False,
    )
    envelope = err.to_envelope()
    assert envelope.error.code == "ebook.drm_detected"
    assert envelope.error.detail == {"files": ["content.opf"]}
    assert envelope.error.retryable is False
    assert len(envelope.error.trace_id) > 10
