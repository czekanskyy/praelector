# SPDX-License-Identifier: Apache-2.0
"""Unit and integration tests for Ebook Ingest API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from praelector.app import create_app
from praelector.config import Settings
from tests.fixtures.builders import (
    create_drm_encrypted_epub,
    create_epub3_polish_novel,
    create_no_text_layer_pdf,
    create_text_layer_pdf,
)


def _setup_client(tmp_path: Path) -> tuple[TestClient, dict[str, str], str]:
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

    # Create and open project
    create_res = client.post(
        "/v1/projects",
        json={"name": "Ingest Test Project", "spoken_language": "pl"},
        headers=headers,
    )
    assert create_res.status_code == 201
    pid = create_res.json()["id"]

    open_res = client.post(f"/v1/projects/{pid}/open", headers=headers)
    assert open_res.status_code == 200

    return client, headers, pid


def test_ingest_probe_api(tmp_path: Path) -> None:
    client, headers, pid = _setup_client(tmp_path)

    # 1. Probe valid EPUB3
    epub_path = tmp_path / "novel.epub"
    create_epub3_polish_novel(epub_path)

    probe_res = client.post(
        f"/v1/projects/{pid}/ingest/probe",
        json={"path": str(epub_path)},
        headers=headers,
    )
    assert probe_res.status_code == 200
    pdata = probe_res.json()
    assert pdata["format"] == "epub"
    assert pdata["drm"]["detected"] is False
    assert pdata["has_text_layer"] is True
    assert pdata["metadata_preview"] is not None
    assert pdata["metadata_preview"]["title"] == "Kroniki Wrzosowiska"
    assert "Jan Kowalski" in pdata["metadata_preview"]["authors"]
    assert pdata["metadata_preview"]["language"] == "pl"

    # 2. Probe DRM-encrypted EPUB
    drm_path = tmp_path / "drm.epub"
    create_drm_encrypted_epub(drm_path)

    probe_drm = client.post(
        f"/v1/projects/{pid}/ingest/probe",
        json={"path": str(drm_path)},
        headers=headers,
    )
    assert probe_drm.status_code == 200
    assert probe_drm.json()["drm"]["detected"] is True

    # 3. Probe PDF without text layer
    no_text_pdf = tmp_path / "scanned.pdf"
    create_no_text_layer_pdf(no_text_pdf)

    probe_pdf = client.post(
        f"/v1/projects/{pid}/ingest/probe",
        json={"path": str(no_text_pdf)},
        headers=headers,
    )
    assert probe_pdf.status_code == 200
    assert probe_pdf.json()["format"] == "pdf"
    assert probe_pdf.json()["has_text_layer"] is False

    # 4. Probe PDF with text layer
    text_pdf = tmp_path / "text.pdf"
    create_text_layer_pdf(text_pdf)

    probe_text_pdf = client.post(
        f"/v1/projects/{pid}/ingest/probe",
        json={"path": str(text_pdf)},
        headers=headers,
    )
    assert probe_text_pdf.status_code == 200
    assert probe_text_pdf.json()["has_text_layer"] is True

    # 5. Probe non-existent file -> 404
    probe_missing = client.post(
        f"/v1/projects/{pid}/ingest/probe",
        json={"path": str(tmp_path / "does_not_exist.epub")},
        headers=headers,
    )
    assert probe_missing.status_code == 404


def test_ingest_import_and_source_api(tmp_path: Path) -> None:
    client, headers, pid = _setup_client(tmp_path)

    epub_path = tmp_path / "polish_novel.epub"
    create_epub3_polish_novel(epub_path)

    # 1. Source status before ingest
    src_before = client.get(f"/v1/projects/{pid}/source", headers=headers)
    assert src_before.status_code == 200
    assert src_before.json()["original_path"] is None
    assert src_before.json()["working_epub_path"] is None

    # 2. Ingest valid EPUB
    ingest_res = client.post(
        f"/v1/projects/{pid}/ingest",
        json={"path": str(epub_path)},
        headers=headers,
    )
    assert ingest_res.status_code == 200
    idata = ingest_res.json()
    assert idata["chapter_count"] == 4  # front, ch1, ch2, back
    assert idata["total_chars"] > 100
    assert Path(idata["working_epub_path"]).is_file()

    # 3. Verify source status after ingest
    src_after = client.get(f"/v1/projects/{pid}/source", headers=headers)
    assert src_after.status_code == 200
    sdata = src_after.json()
    assert sdata["original_path"] == "source/original.epub"
    assert sdata["working_epub_path"] == "source/working.epub"

    # 4. Ingest DRM file raises 422
    drm_path = tmp_path / "encrypted.epub"
    create_drm_encrypted_epub(drm_path)
    ingest_drm = client.post(
        f"/v1/projects/{pid}/ingest",
        json={"path": str(drm_path)},
        headers=headers,
    )
    assert ingest_drm.status_code == 422
    assert ingest_drm.json()["error"]["code"] == "ebook.drm_detected"

    # 5. Ingest scanned PDF raises 422
    no_text_pdf = tmp_path / "scanned.pdf"
    create_no_text_layer_pdf(no_text_pdf)
    ingest_pdf = client.post(
        f"/v1/projects/{pid}/ingest",
        json={"path": str(no_text_pdf)},
        headers=headers,
    )
    assert ingest_pdf.status_code == 422
    assert ingest_pdf.json()["error"]["code"] == "ebook.no_text_layer"
