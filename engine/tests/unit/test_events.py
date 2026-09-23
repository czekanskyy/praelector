# SPDX-License-Identifier: Apache-2.0
"""Tests for the event bus: sequence numbers, replay and back-pressure."""

from __future__ import annotations

import pytest

from praelector import SCHEMA_VERSION
from praelector.domain.enums import EventType
from praelector.events import EventBus


@pytest.fixture
def bus() -> EventBus:
    return EventBus(buffer_size=8, queue_size=4)


def test_last_seq_starts_at_zero(bus: EventBus) -> None:
    assert bus.last_seq == 0


def test_seq_is_monotonic_across_event_types(bus: EventBus) -> None:
    first = bus.publish(EventType.GPU_SAMPLE, {"device_index": 0})
    second = bus.publish(EventType.JOB_PROGRESS, {"chunks_done": 1}, job_id="job_a")
    third = bus.publish(EventType.RUNTIME_PROGRESS, {"phase": "resolve"})
    assert [first.seq, second.seq, third.seq] == [1, 2, 3]
    assert bus.last_seq == 3


def test_since_returns_only_newer_events(bus: EventBus) -> None:
    bus.publish(EventType.GPU_SAMPLE, {"n": 1})
    second = bus.publish(EventType.GPU_SAMPLE, {"n": 2})
    bus.publish(EventType.GPU_SAMPLE, {"n": 3})
    assert [e.payload["n"] for e in bus.since(second.seq - 1)] == [2, 3]


def test_since_can_replay_one_job_only(bus: EventBus) -> None:
    bus.publish(EventType.JOB_CHUNK, {"ordinal": 1}, job_id="job_a")
    bus.publish(EventType.JOB_CHUNK, {"ordinal": 1}, job_id="job_b")
    bus.publish(EventType.JOB_CHUNK, {"ordinal": 2}, job_id="job_a")
    replayed = bus.since(0, job_id="job_a")
    assert [e.payload["ordinal"] for e in replayed] == [1, 2]
    assert all(e.job_id == "job_a" for e in replayed)


def test_since_respects_the_limit(bus: EventBus) -> None:
    for n in range(6):
        bus.publish(EventType.GPU_SAMPLE, {"n": n})
    assert len(bus.since(0, limit=2)) == 2


def test_the_replay_buffer_is_bounded(bus: EventBus) -> None:
    for n in range(20):
        bus.publish(EventType.GPU_SAMPLE, {"n": n})
    # Only the tail survives, so `since` cannot grow without limit.
    assert [e.payload["n"] for e in bus.since(0)] == list(range(12, 20))
    assert bus.last_seq == 20


def test_subscribers_receive_published_events(bus: EventBus) -> None:
    sub = bus.subscribe()
    event = bus.publish(EventType.JOB_STATE, {"state": "running"}, job_id="job_a")
    assert sub.queue.get_nowait() is event
    assert bus.subscriber_count == 1


def test_topics_narrow_delivery(bus: EventBus) -> None:
    sub = bus.subscribe()
    bus.set_topics(sub, [EventType.JOB_STATE])
    bus.publish(EventType.GPU_SAMPLE, {"device_index": 0})
    bus.publish(EventType.JOB_STATE, {"state": "paused"})
    assert sub.queue.qsize() == 1
    assert sub.queue.get_nowait().type == EventType.JOB_STATE.value


def test_an_empty_topic_list_means_everything(bus: EventBus) -> None:
    sub = bus.subscribe()
    bus.set_topics(sub, [EventType.JOB_STATE])
    bus.set_topics(sub, [])
    bus.publish(EventType.GPU_SAMPLE, {"device_index": 0})
    assert sub.queue.qsize() == 1


def test_a_slow_subscriber_drops_events_and_says_so(bus: EventBus) -> None:
    sub = bus.subscribe(queue_size=2)
    for n in range(5):
        bus.publish(EventType.GPU_SAMPLE, {"n": n})
    assert sub.queue.qsize() == 2
    assert sub.dropped == 3


def test_unsubscribe_stops_delivery(bus: EventBus) -> None:
    sub = bus.subscribe()
    bus.unsubscribe(sub)
    bus.publish(EventType.GPU_SAMPLE, {"n": 1})
    assert sub.queue.empty()
    assert bus.subscriber_count == 0


def test_wire_envelope_matches_the_documented_shape(bus: EventBus) -> None:
    event = bus.publish(EventType.JOB_CHUNK, {"ordinal": 7, "reused": True}, job_id="job_a")
    wire = event.to_wire()
    assert set(wire) == {"v", "seq", "ts", "type", "payload", "job_id"}
    assert wire["v"] == SCHEMA_VERSION
    assert wire["type"] == "job.chunk"
    assert wire["ts"].endswith("Z")
    assert wire["payload"] == {"ordinal": 7, "reused": True}


def test_job_id_is_omitted_for_global_events(bus: EventBus) -> None:
    wire = bus.publish(EventType.RUNTIME_PROGRESS, {"phase": "download"}).to_wire()
    assert "job_id" not in wire
