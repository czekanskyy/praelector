# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory and lifecycle wiring."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from praelector.api.v1.health import router as health_router
from praelector.api.v1.version import router as version_router
from praelector.config import Settings, get_settings, set_settings
from praelector.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from praelector.logging import configure_logging
from praelector.security import SecurityMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure FastAPI engine application."""
    if settings is not None:
        set_settings(settings)
    app_settings = get_settings()

    configure_logging(app_settings.log_level)

    app = FastAPI(
        title="Praelector Engine API",
        version="0.1.0",
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
    )

    # Middleware: Security & Authentication
    app.add_middleware(SecurityMiddleware, settings=app_settings)

    # Exception Handlers
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # v1 API Router
    v1_router = APIRouter(prefix="/v1")
    v1_router.include_router(health_router)
    v1_router.include_router(version_router)

    app.include_router(v1_router)

    return app
