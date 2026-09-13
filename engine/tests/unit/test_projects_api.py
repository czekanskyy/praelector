# SPDX-License-Identifier: Apache-2.0
"""Unit and integration tests for Projects and Capabilities API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from praelector.app import create_app
from praelector.config import Settings


def test_projects_lifecycle_api(tmp_path: Path) -> None:
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

    # 1. Initially empty project list
    res = client.get("/v1/projects", headers=headers)
    assert res.status_code == 200
    assert res.json() == []

    # 2. Create project
    create_payload = {
        "name": "Pan Tadeusz",
        "voice_mode": "narrator_male_female",
        "spoken_language": "pl",
        "backend_id": "omnivoice",
    }
    create_res = client.post("/v1/projects", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    prj = create_res.json()
    pid = prj["id"]
    assert pid.startswith("prj_")
    assert prj["name"] == "Pan Tadeusz"
    assert prj["voice_mode"] == "narrator_male_female"

    # 3. List projects
    list_res = client.get("/v1/projects", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 1
    assert items[0]["id"] == pid

    # 4. Get single project
    get_res = client.get(f"/v1/projects/{pid}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Pan Tadeusz"

    # 5. Patch project
    patch_res = client.patch(
        f"/v1/projects/{pid}",
        json={"name": "Pan Tadeusz (Edycja Lektorska)", "cloud_llm_enabled": True},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Pan Tadeusz (Edycja Lektorska)"
    assert patch_res.json()["cloud_llm_enabled"] is True

    # 6. Health check before opening: project_open is False
    health_before = client.get("/v1/health", headers=headers).json()
    assert health_before["project_open"] is False

    # 7. Open project
    open_res = client.post(f"/v1/projects/{pid}/open", headers=headers)
    assert open_res.status_code == 200
    assert open_res.json()["status"] == "opened"
    assert open_res.json()["project"]["is_open"] is True

    # 8. Health check after opening: project_open is True
    health_after = client.get("/v1/health", headers=headers).json()
    assert health_after["project_open"] is True

    # 9. Get project stats
    stats_res = client.get(f"/v1/projects/{pid}/stats", headers=headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["project_id"] == pid
    assert stats["chapter_count"] == 0

    # 10. Close project
    close_res = client.post(f"/v1/projects/{pid}/close", headers=headers)
    assert close_res.status_code == 200
    assert close_res.json()["status"] == "closed"

    health_closed = client.get("/v1/health", headers=headers).json()
    assert health_closed["project_open"] is False

    # 11. Delete project with files
    del_res = client.delete(f"/v1/projects/{pid}?delete_files=true", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify project list is empty again
    empty_list = client.get("/v1/projects", headers=headers).json()
    assert len(empty_list) == 0


def test_capabilities_api(tmp_path: Path) -> None:
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

    res = client.get("/v1/capabilities", headers=headers)
    assert res.status_code == 200
    caps = res.json()
    assert "ffmpeg" in caps
    assert "calibre" in caps
    assert "keyring" in caps
    assert "runtime" in caps
    assert "system_info" in caps
