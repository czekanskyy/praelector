# SPDX-License-Identifier: Apache-2.0
"""Domain entities and the shared wire contract.

Every model in this module is exported to TypeScript by ``scripts/gen_ts_types.py``
and consumed by ``apps/ui`` through ``@praelector/schemas``; the staleness check in
``ci-ui.yml`` is what stops the two from drifting. Router-local request/response
models live next to their router in ``api/v1`` and are exported from there.

The book-shaped entities (Chapter, Block, Span, Suggestion, VoiceProfile, Job,
PlanItem, Chunk, GpuBudget) arrive with the milestones that use them; see
``docs/plan/DATA_MODEL.md`` for the schema they must match.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from praelector import SCHEMA_VERSION
from praelector.domain.enums import EventType, VoiceMode


class WsEnvelope(BaseModel):
    """The WebSocket frame (OPENAPI_SKETCH.md §11).

    ``seq`` is monotonic per process, so a client that reconnects can replay from
    its last number with ``GET /v1/jobs/{id}/events?since=<seq>`` and miss nothing.
    """

    v: int = SCHEMA_VERSION
    seq: int = Field(ge=0)
    ts: datetime
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    job_id: str | None = None

    @field_serializer("ts")
    def _serialise_ts(self, value: datetime) -> str:
        """RFC 3339 UTC with a ``Z`` suffix, matching every other timestamp."""
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ProjectSummary(BaseModel):
    """One Library row, built from ``project.json`` without opening the database."""

    id: str
    name: str
    #: Null for a project whose manifest could not be read; ``unreadable`` says so.
    created_at: datetime | None = None
    updated_at: datetime | None = None
    voice_mode: VoiceMode
    backend_id: str | None = None
    spoken_language: str = "pl"
    current_revision: int = Field(default=0, ge=0)
    #: POSIX-style absolute path (PLAN.md §1.7).
    path: str
    is_open: bool = False
    unreadable: bool = False


class ProjectDetail(ProjectSummary):
    """A single project, including state that only the database knows."""

    schema_version: int = Field(ge=1)
    #: The Alembic revision the project database is at; empty until it is opened.
    db_revision: str = ""
    #: LM-05 / NF-02: book text may only leave the machine when this is true.
    cloud_llm_enabled: bool = False
