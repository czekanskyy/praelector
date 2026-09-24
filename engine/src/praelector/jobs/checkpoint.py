# SPDX-License-Identifier: Apache-2.0
"""On-disk job record and its event log (JB-01, JB-07).

A transition appends one ``job.state`` line to ``events.jsonl`` and then
rewrites ``job.json`` with temp+rename. If the process dies between the two,
the next open takes ``last_seq`` from the log and still applies crash recovery.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praelector import SCHEMA_VERSION
from praelector.domain.enums import TERMINAL_JOB_STATES, EventType, JobKind, JobState
from praelector.jobs.state import JobEvent, recover, stage_for, transition
from praelector.store.atomic import canonical_json, write_json_atomic
from praelector.store.tables import to_db_time

Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _event_ts(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class JobRecord:
    """The crash-recovery record stored in ``job.json``."""

    id: str
    project_id: str
    kind: JobKind
    state: JobState
    revision: int
    created_at: str
    updated_at: str
    paused_reason: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    voice_assignment: dict[str, str | None] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    cursor: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    last_seq: int = 0
    error: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "project_id": self.project_id,
            "kind": self.kind,
            "state": self.state,
            "stage": stage_for(self.state, kind=self.kind),
            "paused_reason": self.paused_reason,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "revision": self.revision,
            "options": self.options,
            "voice_assignment": self.voice_assignment,
            "warnings": self.warnings,
            "counts": self.counts,
            "cursor": self.cursor,
            "metrics": self.metrics,
            "last_seq": self.last_seq,
            "error": self.error,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> JobRecord:
        return cls(
            id=payload["id"],
            project_id=payload["project_id"],
            kind=JobKind(payload["kind"]),
            state=JobState(payload["state"]),
            revision=int(payload["revision"]),
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
            paused_reason=payload.get("paused_reason"),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            options=dict(payload.get("options") or {}),
            voice_assignment=dict(payload.get("voice_assignment") or {}),
            warnings=list(payload.get("warnings") or []),
            counts=dict(payload.get("counts") or {}),
            cursor=dict(payload.get("cursor") or {}),
            metrics=dict(payload.get("metrics") or {}),
            last_seq=int(payload.get("last_seq") or 0),
            error=payload.get("error"),
        )


class JobLog:
    """``jobs/<id>/`` : ``job.json`` plus an append-only ``events.jsonl``."""

    def __init__(self, directory: Path, *, clock: Clock | None = None) -> None:
        self.directory = directory
        self.job_path = directory / "job.json"
        self.events_path = directory / "events.jsonl"
        self._clock = clock or _now

    def create(self, record: JobRecord) -> JobRecord:
        """Write the first ``job.json``. No event yet; ``last_seq`` stays 0."""
        self.directory.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.job_path, record.to_json())
        return record

    def apply(self, record: JobRecord, event: JobEvent) -> JobRecord:
        """Legal transition, then the event line, then the new ``job.json``."""
        nxt = transition(record.state, event, kind=record.kind)
        when = self._clock()
        stamp = to_db_time(when)
        paused_reason = None if nxt is not JobState.PAUSED else record.paused_reason
        started_at = record.started_at
        if record.state is JobState.QUEUED and nxt is JobState.RUNNING:
            started_at = stamp
        finished_at = stamp if nxt in TERMINAL_JOB_STATES else record.finished_at
        updated = replace(
            record,
            state=nxt,
            paused_reason=paused_reason,
            started_at=started_at,
            finished_at=finished_at,
            updated_at=stamp,
            last_seq=record.last_seq + 1,
        )
        self._append(
            updated,
            event_type=EventType.JOB_STATE,
            payload={
                "event": event,
                "state": nxt,
                "stage": stage_for(nxt, kind=record.kind),
                "paused_reason": paused_reason,
            },
            when=when,
        )
        write_json_atomic(self.job_path, updated.to_json())
        return updated

    def open(self) -> JobRecord:
        """Load the record, catch ``last_seq`` up to the log, then crash-recover."""
        record = JobRecord.from_json(json.loads(self.job_path.read_text(encoding="utf-8")))
        logged = self._last_logged_seq()
        if logged > record.last_seq:
            record = replace(record, last_seq=logged)
        state, reason = recover(record.state)
        if reason is None:
            if logged > int(json.loads(self.job_path.read_text(encoding="utf-8"))["last_seq"]):
                write_json_atomic(self.job_path, record.to_json())
            return record
        when = self._clock()
        updated = replace(
            record,
            state=state,
            paused_reason=reason,
            updated_at=to_db_time(when),
            last_seq=record.last_seq + 1,
        )
        self._append(
            updated,
            event_type=EventType.JOB_STATE,
            payload={
                "event": "crash_recovery",
                "state": state,
                "stage": stage_for(state, kind=record.kind),
                "paused_reason": reason,
            },
            when=when,
        )
        write_json_atomic(self.job_path, updated.to_json())
        return updated

    def events(self) -> list[dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        lines = self.events_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line]

    def _append(
        self,
        record: JobRecord,
        *,
        event_type: EventType,
        payload: dict[str, Any],
        when: datetime,
    ) -> None:
        line = canonical_json(
            {
                "v": SCHEMA_VERSION,
                "seq": record.last_seq,
                "ts": _event_ts(when),
                "type": event_type,
                "job_id": record.id,
                "payload": payload,
            }
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _last_logged_seq(self) -> int:
        found = 0
        for event in self.events():
            found = max(found, int(event["seq"]))
        return found
