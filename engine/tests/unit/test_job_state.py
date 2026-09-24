# SPDX-License-Identifier: Apache-2.0
"""Job transitions from PLAN.md §8.1."""

from __future__ import annotations

import pytest

from praelector.domain.enums import JobKind, JobStage, JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.state import JobEvent, recover, stage_for, transition


def test_a_record_job_walks_queued_running_muxing_done() -> None:
    state = JobState.QUEUED
    state = transition(state, JobEvent.START, kind=JobKind.RECORD)
    assert state is JobState.RUNNING
    state = transition(state, JobEvent.RENDERED, kind=JobKind.RECORD)
    assert state is JobState.MUXING
    state = transition(state, JobEvent.MUXED, kind=JobKind.RECORD)
    assert state is JobState.DONE
    assert stage_for(state, kind=JobKind.RECORD) is JobStage.MUX


def test_a_prep_job_finishes_without_muxing() -> None:
    state = transition(JobState.RUNNING, JobEvent.RENDERED, kind=JobKind.PREP)
    assert state is JobState.DONE
    assert stage_for(state, kind=JobKind.PREP) is JobStage.SYNTH


def test_pause_and_resume() -> None:
    paused = transition(JobState.RUNNING, JobEvent.PAUSE, kind=JobKind.RECORD)
    assert paused is JobState.PAUSED
    assert transition(paused, JobEvent.RESUME, kind=JobKind.RECORD) is JobState.RUNNING


@pytest.mark.parametrize(
    "state",
    [JobState.QUEUED, JobState.RUNNING, JobState.PAUSED, JobState.MUXING],
)
def test_stop_or_cancel_keeps_the_job_cancelled(state: JobState) -> None:
    event = JobEvent.CANCEL if state is JobState.QUEUED else JobEvent.STOP
    assert transition(state, event, kind=JobKind.RECORD) is JobState.CANCELLED


def test_failures() -> None:
    assert transition(JobState.RUNNING, JobEvent.FAIL, kind=JobKind.RECORD) is JobState.FAILED
    assert transition(JobState.PAUSED, JobEvent.FAIL, kind=JobKind.RECORD) is JobState.FAILED
    assert (
        transition(JobState.MUXING, JobEvent.FFMPEG_ERROR, kind=JobKind.RECORD) is JobState.FAILED
    )


def test_an_illegal_edge_is_rejected() -> None:
    with pytest.raises(AppError) as caught:
        transition(JobState.DONE, JobEvent.START, kind=JobKind.RECORD)
    assert caught.value.code is ErrorCode.JOB_INVALID_TRANSITION


def test_crash_recovery_pauses_an_in_flight_job() -> None:
    assert recover(JobState.RUNNING) == (JobState.PAUSED, "crash_recovery")
    assert recover(JobState.MUXING) == (JobState.PAUSED, "crash_recovery")
    assert recover(JobState.PAUSED) == (JobState.PAUSED, None)
    assert recover(JobState.DONE) == (JobState.DONE, None)


def test_queued_is_still_the_plan_stage() -> None:
    assert stage_for(JobState.QUEUED, kind=JobKind.RECORD) is JobStage.PLAN
