# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory.

Middleware order matters and is easy to break, so it is spelled out here. The
last middleware added is the outermost one, giving:

    ServerError → CORS → Trace → Auth → ExceptionHandlers → routes

CORS must be outside Auth because the WebView preflights any cross-origin
request carrying an ``Authorization`` header, and a preflight has no credentials
by definition. Trace must be outside Auth so a rejected request still gets a
trace id in the error envelope and in the log line.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from praelector import __version__
from praelector.api.v1 import gpu, health, projects, settings, ws
from praelector.config import RuntimeEnv, load_runtime_env
from praelector.errors import TraceMiddleware, register_error_handlers
from praelector.logging import register_secret
from praelector.security import AuthMiddleware
from praelector.state import AppState

logger = logging.getLogger(__name__)

API_PREFIX = "/v1"


def create_app(env: RuntimeEnv | None = None, *, state: AppState | None = None) -> FastAPI:
    """Build the engine app. Pure: no directories are created until startup."""
    resolved_env = env if env is not None else load_runtime_env()
    app_state = state if state is not None else AppState.create(resolved_env)
    # The token must be unprintable before the first request can log anything.
    register_secret(resolved_env.token)

    async def _release_project() -> None:
        # Drops project.lock and disposes the database engine, so a killed shell
        # cannot leave a project locked for the next launch (JB-06).
        app_state.projects.close_current()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        app_state.events.attach_loop(asyncio.get_running_loop())
        app_state.env.paths.ensure()
        app_state.shutdown_hooks.append(_release_project)
        logger.info(
            "engine started",
            extra={
                "version": __version__,
                "log_level": app_state.env.log_level,
                "data_dir": str(app_state.env.paths.data_dir),
                "projects_dir": str(app_state.env.paths.projects_dir),
                "settings_error": app_state.env.settings_error,
            },
        )
        yield
        await _release_project()
        logger.info("engine stopped", extra={"uptime_s": round(app_state.uptime_s, 3)})

    app = FastAPI(
        title="Praelector Engine",
        version=__version__,
        summary="Local-first lector preparation and audiobook rendering.",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        # Interactive docs are disabled: they would be an unauthenticated UI for
        # the engine if the token ever leaked, and the OpenAPI document itself is
        # the contract (it is behind auth too).
        docs_url=None,
        redoc_url=None,
    )
    app.state.praelector = app_state

    register_error_handlers(app)

    app.add_middleware(AuthMiddleware, policy=app_state.policy)
    app.add_middleware(TraceMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_state.policy.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Trace-Id"],
        expose_headers=["X-Trace-Id"],
        max_age=600,
    )

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(settings.router, prefix=API_PREFIX)
    app.include_router(projects.router, prefix=API_PREFIX)
    app.include_router(gpu.router, prefix=API_PREFIX)
    app.include_router(ws.router, prefix=API_PREFIX)
    return app
