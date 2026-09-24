# SPDX-License-Identifier: Apache-2.0
"""Job state machine (JB-01, PLAN.md §8.1).

States are the PRD set. A prep job finishes from ``running`` and never
enters ``muxing``. Crash recovery forces ``running`` or ``muxing`` back
to ``paused``.
"""

from __future__ import annotations

from enum import StrEnum

from praelector.domain.enums import JobKind, JobStage, JobState
from praelector.errors import AppError, ErrorCode


class JobEvent(StrEnum):
    START = "start"
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    RENDERED = "rendered"
    FAIL = "fail"
    MUXED = "muxed"
    FFMPEG_ERROR = "ffmpeg_error"


_EDGES: dict[tuple[JobState, JobEvent], JobState] = {
    (JobState.QUEUED, JobEvent.START): JobState.RUNNING,
    (JobState.QUEUED, JobEvent.CANCEL): JobState.CANCELLED,
    (JobState.RUNNING, JobEvent.PAUSE): JobState.PAUSED,
    (JobState.PAUSED, JobEvent.RESUME): JobState.RUNNING,
    (JobState.RUNNING, JobEvent.STOP): JobState.CANCELLED,
    (JobState.PAUSED, JobEvent.STOP): JobState.CANCELLED,
    (JobState.MUXING, JobEvent.STOP): JobState.CANCELLED,
    (JobState.RUNNING, JobEvent.FAIL): JobState.FAILED,
    (JobState.PAUSED, JobEvent.FAIL): JobState.FAILED,
    (JobState.MUXING, JobEvent.MUXED): JobState.DONE,
    (JobState.MUXING, JobEvent.FFMPEG_ERROR): JobState.FAILED,
}


def transition(state: JobState, event: JobEvent, *, kind: JobKind) -> JobState:
    """Next state. An edge that is not in the diagram is ``job.invalid_transition``."""
    if event is JobEvent.RENDERED and state is JobState.RUNNING:
        if kind is JobKind.PREP:
            return JobState.DONE
        return JobState.MUXING
    nxt = _EDGES.get((state, event))
    if nxt is None:
        raise AppError(
            ErrorCode.JOB_INVALID_TRANSITION,
            detail={"state": state, "event": event, "kind": kind},
        )
    return nxt


def recover(state: JobState) -> tuple[JobState, str | None]:
    """On engine start, an in-flight job becomes paused with ``crash_recovery``."""
    if state in {JobState.RUNNING, JobState.MUXING}:
        return JobState.PAUSED, "crash_recovery"
    return state, None


def stage_for(state: JobState, *, kind: JobKind) -> JobStage:
    """Informational stage. It is not a state."""
    if state is JobState.QUEUED:
        return JobStage.PLAN
    if state is JobState.MUXING or (state is JobState.DONE and kind is JobKind.RECORD):
        return JobStage.MUX
    return JobStage.SYNTH
