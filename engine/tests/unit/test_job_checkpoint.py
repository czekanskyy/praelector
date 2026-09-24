# SPDX-License-Identifier: Apache-2.0
"""job.json is rewritten only after the event line is durable."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from praelector.domain.enums import JobKind, JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.state import JobEvent


def _clock() -> datetime:
    return datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _record() -> JobRecord:
    stamp = "2026-09-24T11:00:00Z"
    return JobRecord(
        id="job_01",
        project_id="prj_01",
        kind=JobKind.RECORD,
        state=JobState.QUEUED,
        revision=7,
        created_at=stamp,
        updated_at=stamp,
    )


def test_a_transition_appends_then_rewrites_the_record(tmp_path: Path) -> None:
    log = JobLog(tmp_path, clock=_clock)
    record = log.create(_record())
    running = log.apply(record, JobEvent.START)

    assert running.state is JobState.RUNNING
    assert running.started_at == "2026-09-24T12:00:00Z"
    assert running.last_seq == 1
    saved = json.loads((tmp_path / "job.json").read_text(encoding="utf-8"))
    assert saved["state"] == "running"
    assert saved["stage"] == "synth"
    events = log.events()
    assert len(events) == 1
    assert events[0]["seq"] == 1
    assert events[0]["type"] == "job.state"
    assert events[0]["payload"]["state"] == "running"


def test_an_illegal_transition_leaves_the_files_alone(tmp_path: Path) -> None:
    log = JobLog(tmp_path, clock=_clock)
    record = log.apply(log.create(_record()), JobEvent.START)
    before = (tmp_path / "job.json").read_bytes()

    with pytest.raises(AppError) as caught:
        log.apply(record, JobEvent.MUXED)
    assert caught.value.code is ErrorCode.JOB_INVALID_TRANSITION
    assert (tmp_path / "job.json").read_bytes() == before
    assert len(log.events()) == 1


def test_a_prep_job_is_stored_as_done(tmp_path: Path) -> None:
    log = JobLog(tmp_path, clock=_clock)
    record = _record()
    record.kind = JobKind.PREP
    running = log.apply(log.create(record), JobEvent.START)
    done = log.apply(running, JobEvent.RENDERED)
    assert done.state is JobState.DONE
    assert json.loads((tmp_path / "job.json").read_text(encoding="utf-8"))["stage"] == "synth"


def test_open_pauses_a_job_that_died_while_running(tmp_path: Path) -> None:
    log = JobLog(tmp_path, clock=_clock)
    log.apply(log.create(_record()), JobEvent.START)

    paused = log.open()
    assert paused.state is JobState.PAUSED
    assert paused.paused_reason == "crash_recovery"
    assert paused.last_seq == 2
    assert log.events()[-1]["payload"]["paused_reason"] == "crash_recovery"
    assert JobLog(tmp_path, clock=_clock).open().last_seq == 2


def test_open_catches_seq_when_the_record_lags_the_log(tmp_path: Path) -> None:
    log = JobLog(tmp_path, clock=_clock)
    record = log.apply(log.create(_record()), JobEvent.START)
    stale = json.loads((tmp_path / "job.json").read_text(encoding="utf-8"))
    extra = {
        "v": 1,
        "seq": record.last_seq + 1,
        "ts": "2026-09-24T12:00:00.000Z",
        "type": "job.state",
        "job_id": record.id,
        "payload": {"event": "pause", "state": "paused", "stage": "synth", "paused_reason": None},
    }
    with (tmp_path / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(extra) + "\n")
    stale["state"] = "running"
    stale["last_seq"] = record.last_seq
    (tmp_path / "job.json").write_text(json.dumps(stale), encoding="utf-8")

    opened = log.open()
    assert opened.last_seq == record.last_seq + 2
    assert opened.state is JobState.PAUSED
    assert [event["seq"] for event in log.events()] == [1, 2, 3]
