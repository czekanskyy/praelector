# SPDX-License-Identifier: Apache-2.0
"""Unit and integration tests for Lexicon and Suggestions API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from praelector.app import create_app
from praelector.config import Settings
from praelector.store.schema import chapter_table


def test_lexicon_and_suggestions_api(tmp_path: Path) -> None:
    token = "test-secret-token-1234567890123456"
    test_settings = Settings(
        port=0,
        token=token,
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_level="INFO",
    )

    app = create_app(test_settings)
    client = TestClient(app)
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "http://localhost:1420",
    }

    # 1. Global Lexicon CRUD
    lex_res = client.get("/v1/lexicon", headers=headers)
    assert lex_res.status_code == 200
    assert lex_res.json() == []

    add_lex_res = client.post(
        "/v1/lexicon",
        json={
            "pattern": "AI",
            "spoken": "sztuczna inteligencja",
            "is_regex": False,
            "auto_apply": True,
        },
        headers=headers,
    )
    assert add_lex_res.status_code == 201
    lex_entry = add_lex_res.json()
    assert lex_entry["pattern"] == "AI"
    assert lex_entry["spoken"] == "sztuczna inteligencja"
    assert lex_entry["auto_apply"] is True
    lex_id = lex_entry["id"]

    # 2. Project creation and opening
    create_prj_res = client.post(
        "/v1/projects",
        json={"name": "Test Project", "voice_mode": "narrator_male_female"},
        headers=headers,
    )
    assert create_prj_res.status_code == 201
    pid = create_prj_res.json()["id"]

    open_res = client.post(f"/v1/projects/{pid}/open", headers=headers)
    assert open_res.status_code == 200

    # 3. Project Lexicon (initially inherits global entry)
    proj_lex_res = client.get(f"/v1/projects/{pid}/lexicon", headers=headers)
    assert proj_lex_res.status_code == 200
    entries = proj_lex_res.json()
    assert len(entries) == 1
    assert entries[0]["pattern"] == "AI"

    # Add project-specific override
    add_proj_lex_res = client.post(
        f"/v1/projects/{pid}/lexicon",
        json={"pattern": "AI", "spoken": "ej aj", "priority": 10},
        headers=headers,
    )
    assert add_proj_lex_res.status_code == 201

    effective_res = client.get(f"/v1/projects/{pid}/lexicon?effective=true", headers=headers)
    assert effective_res.status_code == 200
    eff_entries = effective_res.json()
    assert len(eff_entries) == 1
    assert eff_entries[0]["spoken"] == "ej aj"  # Overridden!

    # 4. Ingest/create chapter and blocks to test prepass
    # Create a chapter and add blocks by plain text update
    pm = app.state.project_manager
    chap_repo, _ = pm.get_open_chapter_repo(pid)

    with Session(chap_repo.engine) as s:
        s.execute(
            chapter_table.insert().values(
                id="chp_01",
                project_id=pid,
                ordinal=1,
                title="Rozdział 1",
                included=1,
                char_count=100,
            )
        )
        s.commit()

    sample_text = "Rozdział 8\n\nWalker wzruszył ramionami. — Deadline mamy o 18:00.\n\nReszta poszła do Washington DC. Mamy 238 sztuk."
    text_update_res = client.put(
        "/v1/chapters/chp_01/text",
        json={"text": sample_text, "base_revision": 0},
        headers=headers,
    )
    assert text_update_res.status_code == 200

    # 5. Run deterministic prepass on project
    prepass_res = client.post(f"/v1/projects/{pid}/suggestions/prepass", headers=headers)
    assert prepass_res.status_code == 200
    sugs = prepass_res.json()
    assert len(sugs) >= 4

    origs = [s["original"] for s in sugs]
    assert "Rozdział 8" in origs
    assert "Deadline" in origs
    assert "18:00" in origs
    assert "238" in origs

    # 6. List suggestions with filters
    list_sugs_res = client.get(
        f"/v1/projects/{pid}/suggestions?category=ordinal_heading",
        headers=headers,
    )
    assert list_sugs_res.status_code == 200
    filtered_sugs = list_sugs_res.json()
    assert len(filtered_sugs) == 1
    assert filtered_sugs[0]["original"] == "Rozdział 8"
    assert filtered_sugs[0]["proposed"] == "Rozdział ósmy"
    sug_id = filtered_sugs[0]["id"]

    # 7. Patch suggestion status (accept)
    patch_res = client.patch(
        f"/v1/suggestions/{sug_id}",
        json={"status": "accepted"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "accepted"

    # 8. Bulk accept
    bulk_res = client.post(
        f"/v1/projects/{pid}/suggestions/bulk",
        json={"action": "accept", "category": "numeral"},
        headers=headers,
    )
    assert bulk_res.status_code == 200
    bulk_data = bulk_res.json()
    assert bulk_data["affected"] >= 1
    assert bulk_data["batch_id"].startswith("bat_")

    # Clean up global lexicon entry
    del_res = client.delete(f"/v1/lexicon/{lex_id}", headers=headers)
    assert del_res.status_code == 204
