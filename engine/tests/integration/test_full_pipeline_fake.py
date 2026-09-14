# SPDX-License-Identifier: Apache-2.0
"""Nightly headless fixture pipeline test using fake LLM/TTS backend (PLAN §10, §11).

Runs full book headless integration pipeline on `epub3_polish_novel.epub`:
ingest -> chapter extraction -> deterministic pre-pass -> LLM prep job -> review suggestions.
Full audio synthesis and reader EPUB muxing stages are extended in Milestones 3 & 4.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from praelector.app import create_app
from praelector.config import Settings
from praelector.domain.enums import JobState
from praelector.jobs.manager import JobManager
from praelector.jobs.prep_job import PrepJob
from praelector.llm.protocol import LlmClient, LlmCompletionResponse
from praelector.store.schema import block_table, chapter_table
from tests.fixtures.builders import create_epub3_polish_novel


@pytest.mark.asyncio
async def test_full_pipeline_fake_headless(tmp_path: Path) -> None:
    """Full-book fixture job with fake backend on Polish novel EPUB 3 fixture."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    fixtures_dir = tmp_path / "fixtures"
    data_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    fixtures_dir.mkdir(parents=True)

    # 1. Generate realistic Polish novel EPUB 3 fixture
    epub_path = fixtures_dir / "epub3_polish_novel.epub"
    create_epub3_polish_novel(epub_path)
    assert epub_path.exists()

    # 2. Spin up app test environment
    token = "test-secret-token-1234567890123456"
    test_settings = Settings(
        port=0,
        token=token,
        config_dir=config_dir,
        data_dir=data_dir,
        log_level="INFO",
    )
    app = create_app(test_settings)
    client = TestClient(app)
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "http://localhost:1420",
    }

    # 3. Create and open project
    create_res = client.post(
        "/v1/projects",
        json={"name": "Kroniki Wrzosowiska", "spoken_language": "pl"},
        headers=headers,
    )
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    open_res = client.post(f"/v1/projects/{project_id}/open", headers=headers)
    assert open_res.status_code == 200

    # 4. Ingest EPUB file
    ingest_res = client.post(
        f"/v1/projects/{project_id}/ingest",
        json={"path": str(epub_path)},
        headers=headers,
    )
    assert ingest_res.status_code == 200, ingest_res.text
    idata = ingest_res.json()
    assert idata["chapter_count"] == 4

    # 5. Assert chapters and blocks were extracted
    ch_res = client.get(f"/v1/projects/{project_id}/chapters", headers=headers)
    assert ch_res.status_code == 200
    chapters = ch_res.json()
    assert len(chapters) == 4  # front, ch1, ch2, back

    # Check database records
    project_manager = app.state.project_manager
    engine = project_manager.active_engine
    assert engine is not None
    with engine.connect() as conn:
        db_chapters = conn.execute(select(chapter_table)).fetchall()
        db_blocks = conn.execute(select(block_table)).fetchall()
    assert len(db_chapters) == 4
    assert len(db_blocks) >= 4

    # 6. Run PrepJob pipeline with Mock/Fake LLM client
    mock_client = AsyncMock(spec=LlmClient)
    mock_client.chat_completion.return_value = LlmCompletionResponse(
        content='{"items": []}',
        raw_json={"items": []},
    )
    app.state.llm_router.get_client_for_profile = lambda _p: mock_client

    job_mgr: JobManager = app.state.job_manager
    job = job_mgr.create_job(project_id=project_id, kind="prep", options={})

    prep_job = PrepJob(
        job_id=job.id,
        project_id=project_id,
        job_manager=job_mgr,
        project_manager=app.state.project_manager,
        llm_router=app.state.llm_router,
        options={},
    )
    await prep_job.run()

    updated_job = job_mgr.get_job(job.id)
    assert updated_job is not None
    assert updated_job.state == JobState.DONE.value
    assert updated_job.stage == "complete"
    assert updated_job.finished_at is not None

    # 7. Verify suggestions and blocks after prep pass
    sug_res = client.get(f"/v1/projects/{project_id}/suggestions", headers=headers)
    assert sug_res.status_code == 200
    sug_data = sug_res.json()
    assert "items" in sug_data or isinstance(sug_data, list)
