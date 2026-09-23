# SPDX-License-Identifier: Apache-2.0
"""POST /v1/projects/{id}/ingest/probe. Read-only: no project schema changes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.ebook_factory import (
    AES_128_CBC,
    encryption_xml,
    pdf_bytes,
    tiny_epub3,
    with_meta,
)

from praelector.config import BinaryProbe
from praelector.domain.enums import SourceFormat


def _project(client: TestClient, auth: dict[str, str]) -> str:
    response = client.post("/v1/projects", json={"name": "Probe"}, headers=auth)
    assert response.status_code == 201
    project_id = response.json()["id"]
    assert isinstance(project_id, str)
    return project_id


def test_probe_reads_an_epub_without_calling_calibre(
    client: TestClient,
    auth: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_settings: object) -> BinaryProbe:
        raise AssertionError("calibre must not be probed for an epub")

    monkeypatch.setattr("praelector.api.v1.ingest.probe_calibre", boom)
    project_id = _project(client, auth)
    epub = tmp_path / "book.epub"
    epub.write_bytes(tiny_epub3(isbn=True))
    response = client.post(
        f"/v1/projects/{project_id}/ingest/probe",
        json={"path": str(epub)},
        headers=auth,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "epub"
    assert body["needs_conversion"] is False
    assert body["drm"] == {"detected": False, "reason": None}
    assert body["has_text_layer"] is True
    assert body["metadata_preview"]["title"] == "Tiny Book"
    assert body["metadata_preview"]["authors"] == ["Ada Lovelace"]
    assert body["metadata_preview"]["chapter_count"] == 1
    assert body["converter"] is None
    reasons = [span["reason"] for span in body["skip_spans"]]
    assert "isbn" in reasons
    assert not (tmp_path / "source").exists()


def test_probe_refuses_drm(client: TestClient, auth: dict[str, str], tmp_path: Path) -> None:
    project_id = _project(client, auth)
    locked = tmp_path / "locked.epub"
    locked.write_bytes(
        with_meta((("META-INF/encryption.xml", encryption_xml(AES_128_CBC, "OEBPS/ch01.xhtml")),))
    )
    response = client.post(
        f"/v1/projects/{project_id}/ingest/probe",
        json={"path": str(locked)},
        headers=auth,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ebook.drm_detected"


def test_probe_pdf_and_mobi_report_calibre_without_running_it(
    client: TestClient,
    auth: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "praelector.api.v1.ingest.probe_calibre",
        lambda _settings: BinaryProbe(present=False, reason="not_found"),
    )
    project_id = _project(client, auth)
    pdf = tmp_path / "layer.pdf"
    pdf.write_bytes(pdf_bytes("This page has a real text layer. " * 12))
    response = client.post(
        f"/v1/projects/{project_id}/ingest/probe",
        json={"path": str(pdf)},
        headers=auth,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == SourceFormat.PDF.value
    assert body["needs_conversion"] is True
    assert body["has_text_layer"] is True
    assert body["converter"] == "calibre"
    assert body["calibre_available"] is False

    blank = tmp_path / "blank.pdf"
    blank.write_bytes(pdf_bytes(""))
    refused = client.post(
        f"/v1/projects/{project_id}/ingest/probe",
        json={"path": str(blank)},
        headers=auth,
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "ebook.no_text_layer"

    mobi = tmp_path / "book.mobi"
    mobi.write_bytes(b"\x00" * 60 + b"BOOKMOBI" + b"\x00" * 8)
    converted = client.post(
        f"/v1/projects/{project_id}/ingest/probe",
        json={"path": str(mobi)},
        headers=auth,
    )
    assert converted.status_code == 200
    assert converted.json()["format"] == "mobi"
    assert converted.json()["needs_conversion"] is True
    assert converted.json()["calibre_available"] is False
    assert converted.json()["has_text_layer"] is None
