# SPDX-License-Identifier: Apache-2.0
"""Structured error domain models and exception handling."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorPayload(BaseModel):
    """Machine-readable structured error payload."""

    code: str = Field(..., description="Stable error code (e.g. auth.unauthorized)")
    detail: dict[str, Any] = Field(default_factory=dict, description="Machine-readable details")
    retryable: bool = Field(
        default=False, description="Whether the client may retry this operation"
    )
    trace_id: str = Field(..., description="Unique trace identifier for this error")


class ErrorEnvelope(BaseModel):
    """Standard error response envelope."""

    error: ErrorPayload


def generate_trace_id() -> str:
    """Generate a pseudo-ULID / trace string."""
    now_ms = int(time.time() * 1000)
    rand_hex = uuid.uuid4().hex[:16]
    return f"{now_ms:012x}{rand_hex}"


class AppError(Exception):
    """Base application exception with structured error representation."""

    def __init__(
        self,
        code: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detail: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.detail = detail or {}
        self.retryable = retryable
        self.trace_id = generate_trace_id()

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorPayload(
                code=self.code,
                detail=self.detail,
                retryable=self.retryable,
                trace_id=self.trace_id,
            )
        )


class PraelectorError(AppError):
    """Domain-specific error with optional human message and auto-mapped status code."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        detail: dict[str, Any] | None = None,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        det = dict(detail or {})
        if message:
            det["message"] = message
        if status_code is None:
            if "not_found" in code:
                status_code = status.HTTP_404_NOT_FOUND
            elif "already_active" in code or "conflict" in code:
                status_code = status.HTTP_409_CONFLICT
            elif "unauthorized" in code:
                status_code = status.HTTP_401_UNAUTHORIZED
            elif "forbidden" in code:
                status_code = status.HTTP_403_FORBIDDEN
            else:
                status_code = status.HTTP_400_BAD_REQUEST
        super().__init__(code=code, status_code=status_code, detail=det, retryable=retryable)
        self.message = message or code


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Handler for custom AppError."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_envelope().model_dump(),
    )


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handler for standard Starlette/FastAPI HTTPExceptions."""
    code_map = {
        401: "auth.unauthorized",
        403: "auth.forbidden",
        404: "internal.not_found",
        405: "internal.method_not_allowed",
    }
    code = code_map.get(exc.status_code, "internal.http_error")
    detail = {"message": exc.detail} if isinstance(exc.detail, str) else (exc.detail or {})
    envelope = ErrorEnvelope(
        error=ErrorPayload(
            code=code,
            detail=detail,
            retryable=exc.status_code >= 500,
            trace_id=generate_trace_id(),
        )
    )
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump())


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handler for request payload validation errors."""
    envelope = ErrorEnvelope(
        error=ErrorPayload(
            code="internal.validation_error",
            detail={"errors": exc.errors()},
            retryable=False,
            trace_id=generate_trace_id(),
        )
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=envelope.model_dump(),
    )


async def unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Handler for unexpected internal server errors."""
    envelope = ErrorEnvelope(
        error=ErrorPayload(
            code="internal.unhandled_error",
            detail={},
            retryable=True,
            trace_id=generate_trace_id(),
        )
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=envelope.model_dump(),
    )
