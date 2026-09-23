# SPDX-License-Identifier: Apache-2.0
"""Stable error codes and the error envelope.

The engine never returns user-facing prose (PLAN.md D-16). Every failure leaves
this process as ``{"error": {"code", "detail", "retryable", "trace_id"}}`` and
``apps/ui`` localises the code. That is what makes IX-02 mechanically checkable:
a code that is not in the UI catalogue is a bug in the UI, not a string to
translate here.

``ErrorCode`` is the published contract — it is exported to TypeScript by
``scripts/gen_ts_types.py`` and mirrored by ``apps/ui/src/lib/errors``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    # auth / transport
    AUTH_MISSING_TOKEN = "auth.missing_token"
    AUTH_INVALID_TOKEN = "auth.invalid_token"
    AUTH_ORIGIN_REJECTED = "auth.origin_rejected"

    # internal
    INTERNAL_ERROR = "internal.error"
    INTERNAL_NOT_FOUND = "internal.not_found"
    INTERNAL_METHOD_NOT_ALLOWED = "internal.method_not_allowed"
    INTERNAL_VALIDATION_FAILED = "internal.validation_failed"

    # projects
    PROJECT_NOT_FOUND = "project.not_found"
    PROJECT_ALREADY_OPEN = "project.already_open"
    PROJECT_LOCKED = "project.locked"
    PROJECT_MANIFEST_INVALID = "project.manifest_invalid"
    PROJECT_SCHEMA_TOO_NEW = "project.schema_too_new"
    PROJECT_NOT_OPEN = "project.not_open"

    # ebook ingest (EB-01…EB-09)
    EBOOK_UNSUPPORTED_FORMAT = "ebook.unsupported_format"
    EBOOK_DRM_DETECTED = "ebook.drm_detected"
    EBOOK_EMPTY_TEXT = "ebook.empty_text"
    EBOOK_NO_TEXT_LAYER = "ebook.no_text_layer"
    EBOOK_CALIBRE_MISSING = "ebook.calibre_missing"
    EBOOK_CONVERSION_FAILED = "ebook.conversion_failed"
    EBOOK_PARSE_FAILED = "ebook.parse_failed"

    # text and lector model (ED-*, AI-*)
    TEXT_CHAPTER_NOT_FOUND = "text.chapter_not_found"
    TEXT_BLOCK_NOT_FOUND = "text.block_not_found"
    TEXT_SPAN_OUT_OF_RANGE = "text.span_out_of_range"
    TEXT_SPAN_OVERLAP = "text.span_overlap"
    TEXT_REVISION_CONFLICT = "text.revision_conflict"
    TEXT_SUGGESTION_NOT_FOUND = "text.suggestion_not_found"

    # llm (LM-*, AI-03)
    LLM_NO_PROFILE = "llm.no_profile"
    LLM_PROFILE_NOT_FOUND = "llm.profile_not_found"
    LLM_CLOUD_DISABLED = "llm.cloud_disabled"
    LLM_UNREACHABLE = "llm.unreachable"
    LLM_AUTH_FAILED = "llm.auth_failed"
    LLM_RATE_LIMITED = "llm.rate_limited"
    LLM_INVALID_JSON = "llm.invalid_json"
    LLM_TIMEOUT = "llm.timeout"

    # voices (TTS-04)
    VOICE_NOT_FOUND = "voice.not_found"
    VOICE_SAMPLE_UNREADABLE = "voice.sample_unreadable"
    VOICE_SAMPLE_TOO_SHORT = "voice.sample_too_short"
    VOICE_SAMPLE_TOO_LONG = "voice.sample_too_long"
    VOICE_REF_TEXT_REQUIRED = "voice.ref_text_required"
    VOICE_SLOT_CONFLICT = "voice.slot_conflict"

    # tts backends and workers (TTS-*, D-05)
    TTS_BACKEND_NOT_FOUND = "tts.backend_not_found"
    TTS_LANGUAGE_UNSUPPORTED = "tts.language_unsupported"
    TTS_LICENSE_NOT_ACKNOWLEDGED = "tts.license_not_acknowledged"
    TTS_VOICE_SLOT_MISSING = "tts.voice_slot_missing"
    TTS_MODEL_MISSING = "tts.model_missing"
    TTS_LOAD_FAILED = "tts.load_failed"
    TTS_INPUT_TOO_LONG = "tts.input_too_long"
    TTS_OOM = "tts.oom"
    TTS_WORKER_CRASHED = "tts.worker_crashed"
    TTS_INTERNAL = "tts.internal"

    # runtime provisioning (D-04, GPU-07)
    RUNTIME_NOT_PROVISIONED = "runtime.not_provisioned"
    RUNTIME_PROVISION_FAILED = "runtime.provision_failed"
    RUNTIME_MISMATCH = "runtime.mismatch"
    RUNTIME_BUSY = "runtime.busy"

    # gpu (GPU-*)
    GPU_UNAVAILABLE = "gpu.unavailable"
    GPU_DEVICE_NOT_FOUND = "gpu.device_not_found"
    GPU_INSUFFICIENT_VRAM = "gpu.insufficient_vram"

    # jobs (JB-*, D-14)
    JOB_NOT_FOUND = "job.not_found"
    JOB_ALREADY_ACTIVE = "job.already_active"
    JOB_INVALID_TRANSITION = "job.invalid_transition"
    JOB_NO_PLAN = "job.no_plan"
    JOB_NOT_RESUMABLE = "job.not_resumable"

    # audio (MX-04, D-06)
    AUDIO_FFMPEG_MISSING = "audio.ffmpeg_missing"
    AUDIO_FFMPEG_TOO_OLD = "audio.ffmpeg_too_old"
    AUDIO_PROBE_FAILED = "audio.probe_failed"
    AUDIO_ENCODE_FAILED = "audio.encode_failed"

    # export (MX-*, EX-*)
    EXPORT_INCOMPLETE = "export.incomplete"
    EXPORT_FAILED = "export.failed"
    EXPORT_NOTHING_TO_EXPORT = "export.nothing_to_export"


_STATUS: dict[ErrorCode, int] = {
    ErrorCode.AUTH_MISSING_TOKEN: 401,
    ErrorCode.AUTH_INVALID_TOKEN: 401,
    ErrorCode.AUTH_ORIGIN_REJECTED: 403,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.INTERNAL_NOT_FOUND: 404,
    ErrorCode.INTERNAL_METHOD_NOT_ALLOWED: 405,
    ErrorCode.INTERNAL_VALIDATION_FAILED: 422,
    ErrorCode.PROJECT_NOT_FOUND: 404,
    ErrorCode.PROJECT_ALREADY_OPEN: 409,
    ErrorCode.PROJECT_LOCKED: 409,
    ErrorCode.PROJECT_MANIFEST_INVALID: 422,
    ErrorCode.PROJECT_SCHEMA_TOO_NEW: 422,
    ErrorCode.PROJECT_NOT_OPEN: 409,
    ErrorCode.EBOOK_UNSUPPORTED_FORMAT: 415,
    ErrorCode.EBOOK_DRM_DETECTED: 422,
    ErrorCode.EBOOK_EMPTY_TEXT: 422,
    ErrorCode.EBOOK_NO_TEXT_LAYER: 422,
    ErrorCode.EBOOK_CALIBRE_MISSING: 424,
    ErrorCode.EBOOK_CONVERSION_FAILED: 422,
    ErrorCode.EBOOK_PARSE_FAILED: 422,
    ErrorCode.TEXT_CHAPTER_NOT_FOUND: 404,
    ErrorCode.TEXT_BLOCK_NOT_FOUND: 404,
    ErrorCode.TEXT_SPAN_OUT_OF_RANGE: 422,
    ErrorCode.TEXT_SPAN_OVERLAP: 409,
    ErrorCode.TEXT_REVISION_CONFLICT: 409,
    ErrorCode.TEXT_SUGGESTION_NOT_FOUND: 404,
    ErrorCode.LLM_NO_PROFILE: 424,
    ErrorCode.LLM_PROFILE_NOT_FOUND: 404,
    ErrorCode.LLM_CLOUD_DISABLED: 403,
    ErrorCode.LLM_UNREACHABLE: 502,
    ErrorCode.LLM_AUTH_FAILED: 502,
    ErrorCode.LLM_RATE_LIMITED: 429,
    ErrorCode.LLM_INVALID_JSON: 502,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.VOICE_NOT_FOUND: 404,
    ErrorCode.VOICE_SAMPLE_UNREADABLE: 422,
    ErrorCode.VOICE_SAMPLE_TOO_SHORT: 422,
    ErrorCode.VOICE_SAMPLE_TOO_LONG: 422,
    ErrorCode.VOICE_REF_TEXT_REQUIRED: 422,
    ErrorCode.VOICE_SLOT_CONFLICT: 409,
    ErrorCode.TTS_BACKEND_NOT_FOUND: 404,
    ErrorCode.TTS_LANGUAGE_UNSUPPORTED: 422,
    ErrorCode.TTS_LICENSE_NOT_ACKNOWLEDGED: 403,
    ErrorCode.TTS_VOICE_SLOT_MISSING: 424,
    ErrorCode.TTS_MODEL_MISSING: 424,
    ErrorCode.TTS_LOAD_FAILED: 500,
    ErrorCode.TTS_INPUT_TOO_LONG: 422,
    ErrorCode.TTS_OOM: 503,
    ErrorCode.TTS_WORKER_CRASHED: 500,
    ErrorCode.TTS_INTERNAL: 500,
    ErrorCode.RUNTIME_NOT_PROVISIONED: 424,
    ErrorCode.RUNTIME_PROVISION_FAILED: 500,
    ErrorCode.RUNTIME_MISMATCH: 409,
    ErrorCode.RUNTIME_BUSY: 409,
    ErrorCode.GPU_UNAVAILABLE: 424,
    ErrorCode.GPU_DEVICE_NOT_FOUND: 404,
    ErrorCode.GPU_INSUFFICIENT_VRAM: 409,
    ErrorCode.JOB_NOT_FOUND: 404,
    ErrorCode.JOB_ALREADY_ACTIVE: 409,
    ErrorCode.JOB_INVALID_TRANSITION: 409,
    ErrorCode.JOB_NO_PLAN: 409,
    ErrorCode.JOB_NOT_RESUMABLE: 409,
    ErrorCode.AUDIO_FFMPEG_MISSING: 424,
    ErrorCode.AUDIO_FFMPEG_TOO_OLD: 424,
    ErrorCode.AUDIO_PROBE_FAILED: 422,
    ErrorCode.AUDIO_ENCODE_FAILED: 500,
    ErrorCode.EXPORT_INCOMPLETE: 422,
    ErrorCode.EXPORT_FAILED: 500,
    ErrorCode.EXPORT_NOTHING_TO_EXPORT: 422,
}

_RETRYABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.LLM_RATE_LIMITED,
        ErrorCode.LLM_UNREACHABLE,
        ErrorCode.LLM_TIMEOUT,
        ErrorCode.TTS_OOM,
        ErrorCode.TTS_WORKER_CRASHED,
        ErrorCode.RUNTIME_PROVISION_FAILED,
        ErrorCode.INTERNAL_ERROR,
    }
)


def status_for(code: ErrorCode) -> int:
    """HTTP status for a code. Unknown codes are 500, never a silent 200."""
    return _STATUS.get(code, 500)


def is_retryable(code: ErrorCode) -> bool:
    return code in _RETRYABLE


def new_trace_id() -> str:
    return uuid.uuid4().hex


class ErrorBody(BaseModel):
    """The single error shape the UI is allowed to see."""

    code: ErrorCode
    detail: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
    trace_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """A failure with a stable code. ``message`` is logged, never sent."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        detail: dict[str, Any] | None = None,
        retryable: bool | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(message or str(code))
        self.code = code
        self.detail: dict[str, Any] = detail or {}
        self.retryable = is_retryable(code) if retryable is None else retryable
        self.message = message or str(code)

    def body(self, trace_id: str | None = None) -> ErrorBody:
        return ErrorBody(
            code=self.code,
            detail=self.detail,
            retryable=self.retryable,
            trace_id=trace_id,
        )


def error_response(exc: AppError, trace_id: str | None) -> JSONResponse:
    body = ErrorResponse(error=exc.body(trace_id))
    return JSONResponse(
        status_code=status_for(exc.code),
        content=body.model_dump(mode="json"),
        headers={"X-Trace-Id": trace_id} if trace_id else None,
    )


# 424 Failed Dependency reads oddly but is the honest code for "an external
# binary or runtime this request needs is not present" (ffmpeg, Calibre, the TTS
# runtime, a missing model, a missing voice slot).
_HTTP_FALLBACK: dict[int, ErrorCode] = {
    400: ErrorCode.INTERNAL_VALIDATION_FAILED,
    401: ErrorCode.AUTH_INVALID_TOKEN,
    403: ErrorCode.AUTH_ORIGIN_REJECTED,
    404: ErrorCode.INTERNAL_NOT_FOUND,
    405: ErrorCode.INTERNAL_METHOD_NOT_ALLOWED,
    422: ErrorCode.INTERNAL_VALIDATION_FAILED,
}


class TraceMiddleware(BaseHTTPMiddleware):
    """Give every request a trace id and echo it back for bug reports."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


def trace_id_of(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def register_error_handlers(app: FastAPI) -> None:
    """Attach the envelope to every failure path, including unhandled ones."""

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        trace_id = trace_id_of(request)
        logger.warning(
            "request failed",
            extra={
                "error_code": str(exc.code),
                "error_message": exc.message,
                "error_detail": exc.detail,
                "trace_id": trace_id,
                "path": request.url.path,
            },
        )
        return error_response(exc, trace_id)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        trace_id = trace_id_of(request)
        logger.warning(
            "request validation failed",
            extra={
                "error_code": str(ErrorCode.INTERNAL_VALIDATION_FAILED),
                "trace_id": trace_id,
                "path": request.url.path,
                "errors": exc.errors(),
            },
        )
        return error_response(
            AppError(
                ErrorCode.INTERNAL_VALIDATION_FAILED,
                detail={"errors": _safe_validation_errors(exc)},
            ),
            trace_id,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        trace_id = trace_id_of(request)
        code = _HTTP_FALLBACK.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        detail: dict[str, Any] = {"path": request.url.path}
        if isinstance(exc.detail, str):
            detail["reason"] = exc.detail
        return error_response(AppError(code, detail=detail), trace_id)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        trace_id = trace_id_of(request)
        logger.exception(
            "unhandled error",
            extra={
                "error_code": str(ErrorCode.INTERNAL_ERROR),
                "trace_id": trace_id,
                "path": request.url.path,
                "exc_type": type(exc).__name__,
            },
        )
        return error_response(
            AppError(ErrorCode.INTERNAL_ERROR, detail={"type": type(exc).__name__}),
            trace_id,
        )


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Validation errors without the submitted value: it may be book text."""
    return [
        {"loc": [str(part) for part in err.get("loc", ())], "type": err.get("type", "unknown")}
        for err in exc.errors()
    ]
