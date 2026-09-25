# SPDX-License-Identifier: Apache-2.0
"""The job history and the event replay a reconnect uses."""

from __future__ import annotations

from fastapi.testclient import TestClient

from praelector.domain.enums import JobKind, JobState
from praelector.domain.ids import IdPrefix, new_id
from praelector.jobs.checkpoint import JobLog, JobRecord
from praelector.jobs.state import JobEvent
from praelector.state import AppState


def test_an_open_project_lists_its_jobs_and_replays_events(
    client: TestClient, auth: dict[str, str], app_state: AppState
) -> None:
    project = app_state.projects.create(name="Jobs")
    app_state.projects.open(project.id)
    job_id = new_id(IdPrefix.JOB)
    stamp = "2026-09-25T00:00:00Z"
    log = JobLog(app_state.projects.require_open(project.id).layout.job_dir(job_id))
    log.apply(
        log.create(
            JobRecord(
                id=job_id,
                project_id=project.id,
                kind=JobKind.RECORD,
                state=JobState.QUEUED,
                revision=1,
                created_at=stamp,
                updated_at=stamp,
            )
        ),
        JobEvent.START,
    )
    try:
        listed = client.get(f"/v1/projects/{project.id}/jobs", headers=auth)
        assert listed.status_code == 200
        assert listed.json()["jobs"][0]["id"] == job_id
        assert listed.json()["jobs"][0]["state"] == "running"

        one = client.get(f"/v1/jobs/{job_id}", headers=auth)
        assert one.status_code == 200
        assert one.json()["last_seq"] == 1

        replay = client.get(f"/v1/jobs/{job_id}/events", headers=auth, params={"since": 0})
        assert replay.status_code == 200
        assert [event["seq"] for event in replay.json()["events"]] == [1]

        gap = client.get(f"/v1/jobs/{job_id}/events", headers=auth, params={"since": 1})
        assert gap.json()["events"] == []

        missing = client.get(f"/v1/jobs/{new_id(IdPrefix.JOB)}", headers=auth)
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "job.not_found"
    finally:
        app_state.projects.close_current()


def test_job_routes_require_an_open_project(
    client: TestClient, auth: dict[str, str], app_state: AppState
) -> None:
    project = app_state.projects.create(name="Closed")
    response = client.get(f"/v1/projects/{project.id}/jobs", headers=auth)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "project.not_open"
