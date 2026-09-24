# SPDX-License-Identifier: Apache-2.0
"""One active job per engine (JB-03, JB-04, JB-06).

Starting a second job while one is queued, running, paused, or muxing
returns ``job.already_active``. Pause deletes the partials it is given.
Reset drops the slot and deletes chunk audio only when asked.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from praelector.domain.enums import ACTIVE_JOB_STATES, JobState
from praelector.errors import AppError, ErrorCode
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.state import JobEvent


class JobManager:
    """In-memory slot in front of one ``JobLog``."""

    def __init__(self) -> None:
        self._log: JobLog | None = None
        self._record: JobRecord | None = None

    @property
    def record(self) -> JobRecord | None:
        return self._record

    def adopt(self, log: JobLog, record: JobRecord) -> JobRecord:
        """Take a queued job. A live job already in the slot blocks this."""
        self._reject_if_busy(record.id)
        self._log = log
        self._record = log.create(record)
        return self._record

    def start(self) -> JobRecord:
        return self._apply(JobEvent.START)

    def pause(self, *, parts: Sequence[Path] = ()) -> JobRecord:
        """Pause, then delete each partial. Finished WAVs stay."""
        updated = self._apply(JobEvent.PAUSE)
        for part in parts:
            part.unlink(missing_ok=True)
        return updated

    def resume(self) -> JobRecord:
        return self._apply(JobEvent.RESUME)

    def stop(self) -> JobRecord:
        """Cancel a queued job, or stop any other non-terminal state."""
        record = self._require()
        event = JobEvent.CANCEL if record.state is JobState.QUEUED else JobEvent.STOP
        return self._apply(event)

    def reset(self, *, delete_audio: bool = False, chunks_dir: Path | None = None) -> None:
        """Free the slot. Audio is removed only when ``delete_audio`` is true."""
        record = self._require()
        if record.state in ACTIVE_JOB_STATES:
            raise AppError(
                ErrorCode.JOB_INVALID_TRANSITION,
                detail={"state": record.state, "event": "reset"},
            )
        if delete_audio and chunks_dir is not None and chunks_dir.exists():
            shutil.rmtree(chunks_dir)
        self._log = None
        self._record = None

    def _apply(self, event: JobEvent) -> JobRecord:
        log = self._log
        record = self._require()
        if log is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND)
        self._record = log.apply(record, event)
        return self._record

    def _require(self) -> JobRecord:
        if self._record is None:
            raise AppError(ErrorCode.JOB_NOT_FOUND)
        return self._record

    def _reject_if_busy(self, incoming_id: str) -> None:
        current = self._record
        if current is not None and current.state in ACTIVE_JOB_STATES:
            raise AppError(
                ErrorCode.JOB_ALREADY_ACTIVE,
                detail={"id": current.id, "incoming": incoming_id},
            )
