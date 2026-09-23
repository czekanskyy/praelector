# SPDX-License-Identifier: Apache-2.0
"""Tests for the error envelope and the code → status mapping (PLAN.md D-16)."""

from __future__ import annotations

import json
from typing import cast

import pytest

from praelector.errors import (
    AppError,
    ErrorCode,
    error_response,
    is_retryable,
    new_trace_id,
    status_for,
)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (ErrorCode.AUTH_MISSING_TOKEN, 401),
        (ErrorCode.AUTH_INVALID_TOKEN, 401),
        (ErrorCode.AUTH_ORIGIN_REJECTED, 403),
        (ErrorCode.EBOOK_DRM_DETECTED, 422),
        (ErrorCode.EBOOK_NO_TEXT_LAYER, 422),
        (ErrorCode.EBOOK_CALIBRE_MISSING, 424),
        (ErrorCode.LLM_CLOUD_DISABLED, 403),
        (ErrorCode.LLM_RATE_LIMITED, 429),
        (ErrorCode.TTS_LANGUAGE_UNSUPPORTED, 422),
        (ErrorCode.TTS_OOM, 503),
        (ErrorCode.RUNTIME_NOT_PROVISIONED, 424),
        (ErrorCode.JOB_ALREADY_ACTIVE, 409),
        (ErrorCode.AUDIO_FFMPEG_MISSING, 424),
        (ErrorCode.INTERNAL_NOT_FOUND, 404),
        (ErrorCode.INTERNAL_ERROR, 500),
    ],
)
def test_documented_codes_map_to_their_status(code: ErrorCode, status: int) -> None:
    assert status_for(code) == status


def test_every_code_has_a_status() -> None:
    unmapped = [code for code in ErrorCode if status_for(code) == 500 and code not in _EXPECTED_500]
    assert unmapped == [], f"codes without an explicit mapping: {unmapped}"


_EXPECTED_500 = frozenset(
    {
        ErrorCode.INTERNAL_ERROR,
        ErrorCode.TTS_LOAD_FAILED,
        ErrorCode.TTS_WORKER_CRASHED,
        ErrorCode.TTS_INTERNAL,
        ErrorCode.RUNTIME_PROVISION_FAILED,
        ErrorCode.AUDIO_ENCODE_FAILED,
        ErrorCode.EXPORT_FAILED,
    }
)


def test_an_unmapped_code_is_a_server_error_never_a_success() -> None:
    assert status_for(cast(ErrorCode, "something.new")) == 500


@pytest.mark.parametrize(
    "code",
    [
        ErrorCode.LLM_RATE_LIMITED,
        ErrorCode.LLM_UNREACHABLE,
        ErrorCode.LLM_TIMEOUT,
        ErrorCode.TTS_OOM,
        ErrorCode.TTS_WORKER_CRASHED,
    ],
)
def test_retryable_by_default(code: ErrorCode) -> None:
    assert is_retryable(code)


@pytest.mark.parametrize("code", [ErrorCode.EBOOK_DRM_DETECTED, ErrorCode.AUTH_INVALID_TOKEN])
def test_not_retryable_by_default(code: ErrorCode) -> None:
    assert not is_retryable(code)


def test_retryable_can_be_overridden_per_error() -> None:
    assert AppError(ErrorCode.EBOOK_DRM_DETECTED, retryable=True).retryable is True
    assert AppError(ErrorCode.TTS_OOM, retryable=False).retryable is False


def test_envelope_shape() -> None:
    exc = AppError(
        ErrorCode.EBOOK_DRM_DETECTED,
        detail={"encrypted_items": ["OEBPS/ch01.xhtml"]},
    )
    response = error_response(exc, "trace-123")
    assert response.status_code == 422
    assert response.headers["X-Trace-Id"] == "trace-123"
    body = json.loads(response.body)
    assert set(body) == {"error"}
    assert body["error"] == {
        "code": "ebook.drm_detected",
        "detail": {"encrypted_items": ["OEBPS/ch01.xhtml"]},
        "retryable": False,
        "trace_id": "trace-123",
    }


def test_the_server_side_message_never_leaves_the_engine() -> None:
    exc = AppError(
        ErrorCode.LLM_AUTH_FAILED,
        message="api key sk-live-abcdef was rejected by the provider",
    )
    body = json.loads(error_response(exc, None).body)
    assert "api key" not in json.dumps(body)
    assert body["error"]["trace_id"] is None


def test_detail_defaults_to_an_empty_object() -> None:
    body = json.loads(error_response(AppError(ErrorCode.INTERNAL_ERROR), None).body)
    assert body["error"]["detail"] == {}


def test_trace_ids_are_unique() -> None:
    assert len({new_trace_id() for _ in range(1000)}) == 1000
