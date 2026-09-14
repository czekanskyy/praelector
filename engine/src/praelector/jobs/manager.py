# SPDX-License-Identifier: Apache-2.0
"""Global job supervisor enforcing single-active-job admission and state persistence (D-14, JB-01..JB-07)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select, update

from praelector.domain.enums import JobKind, JobState
from praelector.domain.models import JobCounts, JobMetrics, JobResponse
from praelector.errors import PraelectorError
from praelector.store.atomic import atomic_write
from praelector.store.project_manager import ProjectManager
from praelector.store.schema import job_table


class JobManager:
    """Manages background jobs with SQLite queryable mirrors and atomic job.json crash recovery records."""

    def __init__(self, project_manager: ProjectManager) -> None:
        self.project_manager = project_manager
        self._active_job_id: str | None = None
        self._active_task: asyncio.Task[None] | None = None

    @property
    def active_job_id(self) -> str | None:
        return self._active_job_id

    def _job_dir(self, project_id: str, job_id: str) -> Path:
        paths = self.project_manager.find_project_dir(project_id)
        job_dir = paths.root / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def _write_job_json(self, job: JobResponse) -> None:
        """Write authoritative atomic job.json file (DATA_MODEL.md §8)."""
        job_dir = self._job_dir(job.project_id, job.id)
        job_file = job_dir / "job.json"
        data = {
            "schema_version": 1,
            "id": job.id,
            "project_id": job.project_id,
            "kind": job.kind,
            "state": job.state,
            "stage": job.stage,
            "paused_reason": job.paused_reason,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "revision": job.revision,
            "options": job.options,
            "counts": job.counts.model_dump(),
            "metrics": job.metrics.model_dump(),
            "warnings": job.warnings,
            "error": job.error,
        }
        atomic_write(job_file, json.dumps(data, indent=2))

    def create_job(
        self,
        project_id: str,
        kind: str,
        options: dict[str, Any],
    ) -> JobResponse:
        """Register a new job if no other job is active (D-14, JB-06)."""
        if self._active_job_id is not None:
            active = self.get_job(self._active_job_id)
            if active and active.state in (
                JobState.QUEUED.value,
                JobState.RUNNING.value,
                JobState.PAUSED.value,
                JobState.MUXING.value,
            ):
                raise PraelectorError(
                    code="job.already_active",
                    message=f"Job '{self._active_job_id}' is currently active",
                )

        now = datetime.now(UTC).isoformat()
        job_id = f"job_{int(datetime.now(UTC).timestamp() * 1000)}"

        # Get project revision
        proj = self.project_manager.get_project(project_id)
        revision = proj.current_revision

        job = JobResponse(
            id=job_id,
            project_id=project_id,
            kind=kind,
            state=JobState.RUNNING.value,
            stage="prep" if kind == JobKind.PREP.value else "plan",
            paused_reason=None,
            revision=revision,
            options=options,
            counts=JobCounts(),
            metrics=JobMetrics(),
            warnings=[],
            error=None,
            created_at=now,
            started_at=now,
            finished_at=None,
        )

        # Write to SQLite
        engine = self.project_manager.get_project_engine(project_id)
        with engine.begin() as conn:
            conn.execute(
                insert(job_table).values(
                    id=job.id,
                    project_id=job.project_id,
                    kind=job.kind,
                    state=job.state,
                    stage=job.stage,
                    paused_reason=job.paused_reason,
                    revision=job.revision,
                    options_json=json.dumps(job.options),
                    counts_json=json.dumps(job.counts.model_dump()),
                    metrics_json=json.dumps(job.metrics.model_dump()),
                    warnings_json=json.dumps(job.warnings),
                    error_json=json.dumps(job.error),
                    last_seq=0,
                    created_at=job.created_at,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                )
            )

        self._write_job_json(job)
        self._active_job_id = job_id
        return job

    def get_job(self, job_id: str, project_id: str | None = None) -> JobResponse | None:
        """Retrieve a job by ID."""
        if project_id is None:
            # Look up across open projects or active job
            if self.project_manager.active_project_id:
                project_id = self.project_manager.active_project_id
            else:
                for p in self.project_manager.list_projects():
                    candidate = self.get_job(job_id, project_id=p.id)
                    if candidate is not None:
                        return candidate
                return None

        engine = self.project_manager.get_project_engine(project_id)
        with engine.begin() as conn:
            row = conn.execute(select(job_table).where(job_table.c.id == job_id)).fetchone()
            if row is None:
                return None

            return JobResponse(
                id=row.id,
                project_id=row.project_id,
                kind=row.kind,
                state=row.state,
                stage=row.stage,
                paused_reason=row.paused_reason,
                revision=row.revision,
                options=json.loads(row.options_json) if row.options_json else {},
                counts=JobCounts(**json.loads(row.counts_json)) if row.counts_json else JobCounts(),
                metrics=JobMetrics(**json.loads(row.metrics_json))
                if row.metrics_json
                else JobMetrics(),
                warnings=json.loads(row.warnings_json) if row.warnings_json else [],
                error=json.loads(row.error_json) if row.error_json else None,
                created_at=row.created_at,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )

    def list_jobs(self, project_id: str) -> list[JobResponse]:
        """List all jobs for a project, newest first."""
        engine = self.project_manager.get_project_engine(project_id)
        with engine.begin() as conn:
            rows = conn.execute(
                select(job_table)
                .where(job_table.c.project_id == project_id)
                .order_by(job_table.c.created_at.desc())
            ).fetchall()

            result: list[JobResponse] = []
            for row in rows:
                result.append(
                    JobResponse(
                        id=row.id,
                        project_id=row.project_id,
                        kind=row.kind,
                        state=row.state,
                        stage=row.stage,
                        paused_reason=row.paused_reason,
                        revision=row.revision,
                        options=json.loads(row.options_json) if row.options_json else {},
                        counts=JobCounts(**json.loads(row.counts_json))
                        if row.counts_json
                        else JobCounts(),
                        metrics=JobMetrics(**json.loads(row.metrics_json))
                        if row.metrics_json
                        else JobMetrics(),
                        warnings=json.loads(row.warnings_json) if row.warnings_json else [],
                        error=json.loads(row.error_json) if row.error_json else None,
                        created_at=row.created_at,
                        started_at=row.started_at,
                        finished_at=row.finished_at,
                    )
                )
            return result

    def update_job(
        self,
        job_id: str,
        state: str | None = None,
        stage: str | None = None,
        counts: JobCounts | None = None,
        metrics: JobMetrics | None = None,
        warnings: list[dict[str, Any]] | None = None,
        error: str | None = None,
        finished_at: str | None = None,
    ) -> JobResponse:
        """Update job progress or status atomically."""
        job = self.get_job(job_id)
        if job is None:
            raise PraelectorError(code="job.not_found", message=f"Job '{job_id}' not found")

        updates: dict[str, Any] = {}
        if state is not None:
            job.state = state
            updates["state"] = state
            if state in (JobState.DONE.value, JobState.FAILED.value, JobState.CANCELLED.value):
                if self._active_job_id == job_id:
                    self._active_job_id = None
                if finished_at is None:
                    finished_at = datetime.now(UTC).isoformat()
        if stage is not None:
            job.stage = stage
            updates["stage"] = stage
        if counts is not None:
            job.counts = counts
            updates["counts_json"] = json.dumps(counts.model_dump())
        if metrics is not None:
            job.metrics = metrics
            updates["metrics_json"] = json.dumps(metrics.model_dump())
        if warnings is not None:
            job.warnings = warnings
            updates["warnings_json"] = json.dumps(warnings)
        if error is not None:
            job.error = error
            updates["error_json"] = json.dumps(error)
        if finished_at is not None:
            job.finished_at = finished_at
            updates["finished_at"] = finished_at

        engine = self.project_manager.get_project_engine(job.project_id)
        with engine.begin() as conn:
            conn.execute(update(job_table).where(job_table.c.id == job_id).values(**updates))

        self._write_job_json(job)
        return job

    def cancel_job(self, job_id: str) -> JobResponse:
        """Cancel an active or running job."""
        if self._active_task and self._active_job_id == job_id:
            self._active_task.cancel()

        now = datetime.now(UTC).isoformat()
        return self.update_job(
            job_id=job_id,
            state=JobState.CANCELLED.value,
            finished_at=now,
        )

    def attach_task(self, job_id: str, task: asyncio.Task[None]) -> None:
        """Attach an asyncio Task to track active execution."""
        self._active_job_id = job_id
        self._active_task = task
