# SPDX-License-Identifier: Apache-2.0
"""Process-wide application state shared by routers.

Lives outside ``app.py`` so routers can depend on it without an import cycle.
Later milestones hang their services off this object (job manager, GPU monitor,
TTS registry) instead of adding module-level globals.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast

from starlette.requests import HTTPConnection

from praelector.config import RuntimeEnv, SettingsStore
from praelector.events import EventBus
from praelector.security import AuthPolicy
from praelector.store.projects import ProjectStore
from praelector.store.secrets import SecretStore

if TYPE_CHECKING:
    from praelector.api.v1.settings import CapabilitiesResponse


class ServerHandle(Protocol):
    """The one part of ``uvicorn.Server`` we need: the flag that ends serving."""

    should_exit: bool


#: Registered by later milestones so ``POST /v1/shutdown`` can pause a running
#: job, checkpoint it and close SQLite before the process exits (PLAN.md §1.6).
ShutdownHook = Callable[[], Awaitable[None]]


@dataclass
class AppState:
    env: RuntimeEnv
    policy: AuthPolicy
    settings_store: SettingsStore
    secrets: SecretStore
    projects: ProjectStore
    events: EventBus = field(default_factory=EventBus)
    server: ServerHandle | None = None
    shutdown_hooks: list[ShutdownHook] = field(default_factory=list)
    started_monotonic: float = field(default_factory=time.monotonic)

    #: Probes spawn subprocesses, so the answer is cached until settings change.
    capabilities_cache: CapabilitiesResponse | None = None

    #: Set by the job manager (M4). ``GET /v1/health`` reports it so the supervisor
    #: can tell a busy engine from a dead one.
    active_job_id: str | None = None
    shutting_down: bool = False

    @classmethod
    def create(cls, env: RuntimeEnv, *, policy: AuthPolicy | None = None) -> AppState:
        return cls(
            env=env,
            policy=policy if policy is not None else AuthPolicy(token=env.token),
            settings_store=SettingsStore(env.paths),
            secrets=SecretStore(env.paths.config_dir),
            projects=ProjectStore(env),
        )

    @property
    def current_project_id(self) -> str | None:
        """Delegated, not mirrored: a copy would go stale when the store closes a
        project on shutdown and ``/v1/health`` would keep reporting it as open."""
        return self.projects.current_id

    @property
    def uptime_s(self) -> float:
        return time.monotonic() - self.started_monotonic

    def request_shutdown(self) -> bool:
        """Ask the server to exit once the response is flushed.

        Returns False when there is no server to stop, which is the case under
        ``TestClient``; the route still reports the request so tests can assert
        on it.
        """
        self.shutting_down = True
        if self.server is None:
            return False
        self.server.should_exit = True
        return True

    async def run_shutdown_hooks(self) -> None:
        for hook in self.shutdown_hooks:
            await hook()


def get_state(connection: HTTPConnection) -> AppState:
    """FastAPI dependency for the shared state.

    Typed against ``HTTPConnection`` rather than ``Request`` so the same
    dependency works on WebSocket routes, which receive no ``Request``.
    """
    return cast(AppState, connection.app.state.praelector)
