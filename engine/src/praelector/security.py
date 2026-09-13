# SPDX-License-Identifier: Apache-2.0
"""Security middlewares: Bearer token authentication and Origin allowlist."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from praelector.config import Settings
from praelector.errors import AppError


class SecurityMiddleware(BaseHTTPMiddleware):
    """Enforces Origin allowlist and Bearer token authentication."""

    def __init__(self, app: Callable[..., Any], settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        try:
            # 1. Origin header check (D-10)
            origin = request.headers.get("origin")
            if origin:
                normalized_origin = origin.rstrip("/")
                allowed = [o.rstrip("/") for o in self.settings.allowed_origins]
                if normalized_origin not in allowed:
                    raise AppError(
                        code="auth.forbidden_origin",
                        status_code=403,
                        detail={"origin": origin, "allowed": self.settings.allowed_origins},
                    )

            # 2. Bearer token check (D-10)
            expected_token = self.settings.token
            if expected_token:
                auth_header = request.headers.get("authorization")
                if not auth_header or not auth_header.startswith("Bearer "):
                    raise AppError(
                        code="auth.unauthorized",
                        status_code=401,
                        detail={"reason": "Missing or malformed Authorization header"},
                    )

                provided_token = auth_header[7:].strip()
                # Constant-time comparison to prevent timing side-channels
                if not hmac.compare_digest(
                    provided_token.encode("utf-8"), expected_token.encode("utf-8")
                ):
                    raise AppError(
                        code="auth.unauthorized",
                        status_code=401,
                        detail={"reason": "Invalid token"},
                    )

            return await call_next(request)  # type: ignore[no-any-return]
        except AppError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_envelope().model_dump(),
            )
