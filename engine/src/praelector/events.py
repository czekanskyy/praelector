# SPDX-License-Identifier: Apache-2.0
"""The in-process event bus that feeds the WebSocket hub.

``seq`` is a single monotonic counter for the whole process. Job event logs
(``jobs/<id>/events.jsonl``) store the same numbers, so a monotonic global
sequence is also monotonic per job and ``GET /v1/jobs/{id}/events?since=<seq>``
can replay exactly what a reconnecting client missed (PLAN.md §8.1).

Publishers may live outside the event loop — TTS workers report from their own
threads — so delivery is marshalled onto the loop when needed. A subscriber that
cannot keep up loses events and is told about it; the client resynchronises with
``since`` rather than silently missing a state change.
"""

from __future__ import annotations

import asyncio
import itertools
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from praelector import SCHEMA_VERSION
from praelector.domain.enums import EventType
from praelector.domain.models import WsEnvelope

DEFAULT_BUFFER_SIZE = 4096
DEFAULT_QUEUE_SIZE = 512


@dataclass(frozen=True, slots=True)
class Event:
    """One published event. :meth:`to_wire` renders the documented WS envelope."""

    seq: int
    type: EventType
    payload: dict[str, Any]
    ts: datetime
    job_id: str | None = None
    v: int = SCHEMA_VERSION

    def to_wire(self) -> dict[str, Any]:
        envelope = WsEnvelope(
            v=self.v,
            seq=self.seq,
            ts=self.ts,
            type=self.type,
            payload=self.payload,
            job_id=self.job_id,
        )
        return envelope.model_dump(mode="json", exclude_none=True)


@dataclass(slots=True, eq=False)
class Subscription:
    """One connected client. ``dropped`` drives the overflow control frame.

    ``eq=False`` keeps identity hashing, which is what lets the bus hold
    subscriptions in a set.
    """

    queue: asyncio.Queue[Event] = field(default_factory=asyncio.Queue)
    dropped: int = 0
    topics: frozenset[str] = frozenset()

    def wants(self, event: Event) -> bool:
        return not self.topics or event.type in self.topics


class EventBus:
    """Thread-safe fan-out with a bounded replay buffer."""

    def __init__(
        self, *, buffer_size: int = DEFAULT_BUFFER_SIZE, queue_size: int = DEFAULT_QUEUE_SIZE
    ):
        self._counter = itertools.count(1)
        self._buffer: deque[Event] = deque(maxlen=buffer_size)
        self._subscriptions: set[Subscription] = set()
        self._lock = threading.Lock()
        self._queue_size = queue_size
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the serving loop so worker threads can hand events over safely."""
        self._loop = loop
        self._loop_thread = threading.get_ident()

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._buffer[-1].seq if self._buffer else 0

    def publish(
        self,
        type_: EventType,
        payload: dict[str, Any],
        *,
        job_id: str | None = None,
    ) -> Event:
        event = Event(
            seq=next(self._counter),
            type=type_,
            payload=payload,
            ts=datetime.now(tz=UTC),
            job_id=job_id,
        )
        with self._lock:
            self._buffer.append(event)
            targets = [sub for sub in self._subscriptions if sub.wants(event)]
        for sub in targets:
            self._deliver(sub, event)
        return event

    def _deliver(self, sub: Subscription, event: Event) -> None:
        if self._loop is not None and threading.get_ident() != self._loop_thread:
            self._loop.call_soon_threadsafe(self._put, sub, event)
        else:
            self._put(sub, event)

    def _put(self, sub: Subscription, event: Event) -> None:
        try:
            sub.queue.put_nowait(event)
        except asyncio.QueueFull:
            sub.dropped += 1

    def since(self, seq: int, *, job_id: str | None = None, limit: int = 1000) -> list[Event]:
        """Buffered events after ``seq``, optionally for one job only."""
        with self._lock:
            snapshot = list(self._buffer)
        selected = [e for e in snapshot if e.seq > seq and (job_id is None or e.job_id == job_id)]
        return selected[:limit]

    def subscribe(self, *, queue_size: int | None = None) -> Subscription:
        sub = Subscription(queue=asyncio.Queue(maxsize=queue_size or self._queue_size))
        with self._lock:
            self._subscriptions.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            self._subscriptions.discard(sub)

    def set_topics(self, sub: Subscription, topics: list[str]) -> None:
        sub.topics = frozenset(topics)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)
