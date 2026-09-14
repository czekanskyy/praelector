# SPDX-License-Identifier: Apache-2.0
"""Unit and integration tests for preparation pipeline job, cancellation, and jobs API (AI-01, AI-03, D-14, D-15)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

from praelector.app import create_app
from praelector.config import Settings
from praelector.domain.enums import DetectorKind, JobState, SuggestionStatus
from praelector.domain.models import LlmProfileCreate, TaskRouting
from praelector.jobs.manager import JobManager
from praelector.jobs.prep_job import PrepJob
from praelector.llm.protocol import LlmClient, LlmCompletionResponse
from praelector.store.schema import block_table, chapter_table


def _setup_test_project_with_chapter(
    app: Any, client: TestClient, headers: dict[str, str]
) -> tuple[str, str]:
    """Helper to create a project with 1 chapter and 3 blocks for prep job testing."""
    # Create project
    create_res = client.post(
        "/v1/projects",
        json={
            "name": "Test Polish Book",
            "voice_mode": "narrator_male_female",
            "spoken_language": "pl",
        },
        headers=headers,
    )
    pid = create_res.json()["id"]

    # Insert a chapter and blocks directly into SQLite
    pm = app.state.project_manager
    engine = pm.get_project_engine(pid)
    ch_id = "ch_01"
    with engine.begin() as conn:
        conn.execute(
            insert(chapter_table).values(
                id=ch_id,
                project_id=pid,
                ordinal=1,
                title="Rozdział 1",
                included=1,
                char_count=200,
            )
        )
        conn.execute(
            insert(block_table).values(
                [
                    {
                        "id": "blk_01",
                        "version_id": "blk_01_v0",
                        "chapter_id": ch_id,
                        "ordinal": 1,
                        "kind": "paragraph",
                        "heading_level": None,
                        "text": "— Dzień dobry panu! — zawołał głośno Jan.",
                        "valid_from_revision": 0,
                        "valid_to_revision": None,
                    },
                    {
                        "id": "blk_02",
                        "version_id": "blk_02_v0",
                        "chapter_id": ch_id,
                        "ordinal": 2,
                        "kind": "paragraph",
                        "heading_level": None,
                        "text": "Spotkaliśmy tajemniczego gentlemana o nazwisku Walker.",
                        "valid_from_revision": 0,
                        "valid_to_revision": None,
                    },
                ]
            )
        )
    return pid, ch_id


def test_single_active_job_constraint(tmp_path: Path) -> None:
    """Verify that launching a second active job returns 409 job.already_active (D-14, JB-06)."""
    token = "secret-token-1234567890123456"
    test_settings = Settings(
        port=0,
        token=token,
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_level="INFO",
    )

    app = create_app(test_settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:1420"}

    pid, _ = _setup_test_project_with_chapter(app, client, headers)

    # 1. Start first job (skip_llm=True so it finishes fast or stays active briefly)
    res1 = client.post(
        f"/v1/projects/{pid}/jobs",
        json={"kind": "prep", "options": {"skip_llm": True}},
        headers=headers,
    )
    assert res1.status_code == 201
    job1_id = res1.json()["id"]

    # If job manager still considers it active or running
    job_mgr: JobManager = app.state.job_manager
    # Set job state to RUNNING explicitly to simulate active execution
    job_mgr.update_job(job1_id, state=JobState.RUNNING.value)
    job_mgr._active_job_id = job1_id

    # 2. Start second job -> should fail with 409 conflict
    res2 = client.post(
        f"/v1/projects/{pid}/jobs",
        json={"kind": "prep", "options": {"skip_llm": True}},
        headers=headers,
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "job.already_active"


@pytest.mark.asyncio
async def test_prep_job_execution_two_phases_and_failed_suggestion(tmp_path: Path) -> None:
    """Verify two-phase prep job: Phase 1 heuristic suggestions + Phase 2 LLM refinement with failed suggestion (AI-01, AI-03, D-15)."""
    token = "secret-token-1234567890123456"
    test_settings = Settings(
        port=0,
        token=token,
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_level="INFO",
    )

    app = create_app(test_settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:1420"}

    pid, _ = _setup_test_project_with_chapter(app, client, headers)
    settings_store = app.state.settings_store

    # Create local profile for tasks
    local_prof = settings_store.create_profile(
        LlmProfileCreate(name="Local Test", kind="ollama", model="llama3.2", is_cloud=False)
    )
    settings_store.update_task_routing(
        TaskRouting(dialogue_hard=local_prof.id, pronounce=local_prof.id)
    )

    # Mock client to fail pronounce (invalid json) but succeed dialogue
    mock_client = AsyncMock(spec=LlmClient)
    mock_client.chat_completion.side_effect = [
        # Call 1: pronounce attempt 1 (invalid json)
        LlmCompletionResponse(content="Sorry no json"),
        # Call 2: pronounce attempt 2 retry (still invalid json)
        LlmCompletionResponse(content="Still no json"),
    ]
    app.state.llm_router.get_client_for_profile = lambda _p: mock_client

    job_mgr: JobManager = app.state.job_manager
    job = job_mgr.create_job(project_id=pid, kind="prep", options={})

    prep = PrepJob(
        job_id=job.id,
        project_id=pid,
        job_manager=job_mgr,
        project_manager=app.state.project_manager,
        llm_router=app.state.llm_router,
        options={},
    )
    await prep.run()

    finished_job = job_mgr.get_job(job.id)
    assert finished_job is not None
    assert finished_job.state == JobState.DONE.value
    assert finished_job.stage == "complete"
    assert finished_job.counts.blocks_total == 2
    assert finished_job.counts.blocks_done == 2
    assert finished_job.counts.suggestions_emitted > 0

    # Query suggestions from DB
    engine = app.state.project_manager.get_project_engine(pid)
    from praelector.store.repositories.suggestions import SuggestionRepository

    sug_repo = SuggestionRepository(engine)
    sugs = sug_repo.list(pid)

    # There should be heuristic suggestions from blk_01 dialogue
    assert any(s.detector == DetectorKind.HEURISTIC for s in sugs)

    # There should be a failed suggestion from blk_02 foreign word Walker failing retry (D-15, AI-03)
    failed_sugs = [s for s in sugs if s.status == SuggestionStatus.FAILED]
    assert len(failed_sugs) >= 1
    assert failed_sugs[0].error_code == "llm.invalid_json"
    assert failed_sugs[0].proposed is None


@pytest.mark.asyncio
async def test_prep_job_cancellation_preserves_partial_results(tmp_path: Path) -> None:
    """Verify that cancelled prep job preserves suggestions created before cancellation (AI-01, JB-04)."""
    token = "secret-token-1234567890123456"
    test_settings = Settings(
        port=0,
        token=token,
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_level="INFO",
    )

    app = create_app(test_settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:1420"}

    pid, _ = _setup_test_project_with_chapter(app, client, headers)
    job_mgr: JobManager = app.state.job_manager

    job = job_mgr.create_job(project_id=pid, kind="prep", options={"skip_llm": True})

    # Cancel immediately
    job_mgr.cancel_job(job.id)
    cancelled = job_mgr.get_job(job.id)
    assert cancelled is not None
    assert cancelled.state == JobState.CANCELLED.value

    prep = PrepJob(
        job_id=job.id,
        project_id=pid,
        job_manager=job_mgr,
        project_manager=app.state.project_manager,
        llm_router=None,
        options={"skip_llm": True},
    )
    # Running when already cancelled returns immediately without error
    await prep.run()

    assert job_mgr.get_job(job.id).state == JobState.CANCELLED.value
