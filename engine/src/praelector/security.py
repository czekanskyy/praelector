# SPDX-License-Identifier: Apache-2.0
"""The loopback trust boundary: bearer token plus Origin allow-list (PLAN.md D-10).

Binding ``127.0.0.1`` alone (NF-01) still leaves the engine reachable by any
local process and by any web page the user visits. The token comes from the
environment, never argv, because argv is world-readable in process listings on
both Windows and Linux.

A deviation from PLAN.md §1.5 worth recording: the WebView *is* a browser, so a
cross-origin ``fetch`` with an ``Authorization`` header is preflighted, and a
``WebSocket`` handshake cannot set headers at all. Both are handled here rather
than in the UI — CORS is restricted to the same allow-list as the Origin check,
and the WS token may arrive as a query parameter. The access log is disabled and
the token is registered with the redaction filter, so that query parameter cannot
leak into a log line (see ``logging.py``).
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from praelector.errors import AppError, ErrorCode, error_response, new_trace_id, trace_id_of

#: Tauri serves the bundled UI from ``tauri://localhost`` on Linux and macOS and
#: from ``http://tauri.localhost`` on Windows; ``http://localhost:1420`` is the
#: Vite dev server used by ``just dev``.
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "tauri://localhost",
    "http://tauri.localhost",
    "http://localhost:1420",
)

TOKEN_QUERY_PARAM = "token"
WS_SUBPROTOCOL = "praelector.v1"


def generate_token(nbytes: int = 32) -> str:
    """A per-launch bearer token. 32 bytes, URL-safe, no padding surprises."""
    return secrets.token_urlsafe(nbytes)


@dataclass(frozen=True, slots=True)
class AuthPolicy:
    """Everything needed to decide whether a caller may drive the engine."""

    token: str
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS

    def check_origin(self, origin: str | None) -> None:
        # A request with no Origin header is not a browser request (the Rust
        # supervisor, curl, tests) and is allowed; the token still applies.
        if origin is None or origin in self.allowed_origins:
            return
        raise AppError(
            ErrorCode.AUTH_ORIGIN_REJECTED,
            detail={"origin": origin},
            message="request origin is not in the allow-list",
        )

    def check_token(self, presented: str | None) -> None:
        if presented is None:
            raise AppError(ErrorCode.AUTH_MISSING_TOKEN, message="no bearer token presented")
        if not hmac.compare_digest(presented.encode(), self.token.encode()):
            raise AppError(ErrorCode.AUTH_INVALID_TOKEN, message="bearer token mismatch")

    def authorize(self, headers: Headers) -> None:
        self.check_origin(headers.get("origin"))
        self.check_token(bearer_token(headers.get("authorization")))


def bearer_token(header: str | None) -> str | None:
    """Extract the token from an ``Authorization: Bearer <token>`` header."""
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


class AuthMiddleware(BaseHTTPMiddleware):
    """Rejects unauthenticated and foreign-origin requests before any route."""

    def __init__(self, app: Any, policy: AuthPolicy) -> None:
        super().__init__(app)
        self.policy = policy

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            self.policy.authorize(request.headers)
        except AppError as exc:
            return error_response(exc, trace_id_of(request) or new_trace_id())
        return await call_next(request)


def websocket_token(websocket: WebSocket) -> str | None:
    """Token for a WS handshake: header first, then the query parameter.

    The WebView's ``WebSocket`` constructor cannot set headers, so the query
    parameter is the only transport available to the UI.
    """
    from_header = bearer_token(websocket.headers.get("authorization"))
    if from_header:
        return from_header
    return websocket.query_params.get(TOKEN_QUERY_PARAM)


def authorize_websocket(websocket: WebSocket, policy: AuthPolicy) -> AppError | None:
    """Non-raising WS check: the caller closes the socket with the error code."""
    try:
        policy.check_origin(websocket.headers.get("origin"))
        policy.check_token(websocket_token(websocket))
    except AppError as exc:
        return exc
    return None
