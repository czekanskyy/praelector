# SPDX-License-Identifier: Apache-2.0
"""Unit and integration tests for Chapter management and editor API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from praelector.app import create_app
from praelector.config import Settings
from tests.fixtures.builders import create_epub3_polish_novel


def _setup_ingested_client(tmp_path: Path) -> tuple[TestClient, dict[str, str], str]:
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

    create_res = client.post(
        "/v1/projects",
        json={"name": "Chapters Test Project", "spoken_language": "pl"},
        headers=headers,
    )
    assert create_res.status_code == 201
    pid = create_res.json()["id"]

    open_res = client.post(f"/v1/projects/{pid}/open", headers=headers)
    assert open_res.status_code == 200

    epub_path = tmp_path / "novel.epub"
    create_epub3_polish_novel(epub_path)
    ingest_res = client.post(
        f"/v1/projects/{pid}/ingest",
        json={"path": str(epub_path)},
        headers=headers,
    )
    assert ingest_res.status_code == 200

    return client, headers, pid


def test_chapters_tree_and_metadata_api(tmp_path: Path) -> None:
    client, headers, pid = _setup_ingested_client(tmp_path)

    # 1. List chapters
    res = client.get(f"/v1/projects/{pid}/chapters", headers=headers)
    assert res.status_code == 200
    chapters = res.json()
    assert len(chapters) == 4
    assert [c["ordinal"] for c in chapters] == [1, 2, 3, 4]

    ch0_id = chapters[0]["id"]
    ch1_id = chapters[1]["id"]
    ch2_id = chapters[2]["id"]
    ch3_id = chapters[3]["id"]

    # 2. Update chapter metadata
    patch_res = client.patch(
        f"/v1/chapters/{ch1_id}",
        json={"title": "Początek wielkiej podróży", "included": False},
        headers=headers,
    )
    assert patch_res.status_code == 200
    updated_ch = patch_res.json()
    assert updated_ch["title"] == "Początek wielkiej podróży"
    assert updated_ch["included"] is False

    # 3. Reorder chapters (reverse ch1 and ch2)
    reorder_res = client.post(
        f"/v1/projects/{pid}/chapters/reorder",
        json={"order": [ch0_id, ch2_id, ch1_id, ch3_id]},
        headers=headers,
    )
    assert reorder_res.status_code == 200
    new_order = [c["id"] for c in reorder_res.json()]
    assert new_order == [ch0_id, ch2_id, ch1_id, ch3_id]


def test_chapter_blocks_and_text_api(tmp_path: Path) -> None:
    client, headers, pid = _setup_ingested_client(tmp_path)

    chapters = client.get(f"/v1/projects/{pid}/chapters", headers=headers).json()
    ch1 = [c for c in chapters if "Rozdział 1" in c["title"]][0]
    ch1_id = ch1["id"]

    # 1. Get blocks
    blocks_res = client.get(f"/v1/chapters/{ch1_id}/blocks", headers=headers)
    assert blocks_res.status_code == 200
    blocks = blocks_res.json()
    assert len(blocks) >= 4
    first_block = blocks[0]
    assert first_block["kind"] == "heading"
    assert first_block["heading_level"] == 1

    # 2. Get text in display mode
    text_disp_res = client.get(
        f"/v1/chapters/{ch1_id}/text",
        params={"view": "display"},
        headers=headers,
    )
    assert text_disp_res.status_code == 200
    text_disp = text_disp_res.json()
    assert "Rozdział 1 — Początek podróży" in text_disp["text"]
    assert "Wiosenny poranek" in text_disp["text"]

    # 3. Update text (edit one sentence)
    original_text = text_disp["text"]
    modified_text = original_text.replace("Wiosenny poranek", "Cichy poranek")
    update_res = client.put(
        f"/v1/chapters/{ch1_id}/text",
        json={"text": modified_text, "base_revision": 1},
        headers=headers,
    )
    assert update_res.status_code == 200
    upd_data = update_res.json()
    assert upd_data["revision"] >= 2

    # Check updated text persists
    re_text = client.get(
        f"/v1/chapters/{ch1_id}/text",
        params={"view": "display"},
        headers=headers,
    ).json()
    assert "Cichy poranek" in re_text["text"]


def test_chapter_split_and_merge_api(tmp_path: Path) -> None:
    client, headers, pid = _setup_ingested_client(tmp_path)

    chapters = client.get(f"/v1/projects/{pid}/chapters", headers=headers).json()
    ch1 = [c for c in chapters if "Rozdział 1" in c["title"]][0]
    ch1_id = ch1["id"]

    blocks = client.get(f"/v1/chapters/{ch1_id}/blocks", headers=headers).json()
    split_block_id = blocks[2]["id"]

    # Split ch1 at block 2
    split_res = client.post(
        f"/v1/chapters/{ch1_id}/split",
        json={"block_id": split_block_id, "offset": 0},
        headers=headers,
    )
    assert split_res.status_code == 200
    split_parts = split_res.json()
    assert len(split_parts) == 2
    new_ch = split_parts[1]
    new_ch_id = new_ch["id"]

    # Verify chapters count increased to 5
    chapters_after_split = client.get(f"/v1/projects/{pid}/chapters", headers=headers).json()
    assert len(chapters_after_split) == 5

    # Merge newly created chapter back into ch1
    merge_res = client.post(
        f"/v1/projects/{pid}/chapters/merge",
        json={"ids": [ch1_id, new_ch_id]},
        headers=headers,
    )
    assert merge_res.status_code == 200
    merged_ch = merge_res.json()
    assert merged_ch["id"] == ch1_id

    # Verify chapters count is back to 4
    chapters_after_merge = client.get(f"/v1/projects/{pid}/chapters", headers=headers).json()
    assert len(chapters_after_merge) == 4


def test_spans_crud_and_spoken_view_api(tmp_path: Path) -> None:
    client, headers, pid = _setup_ingested_client(tmp_path)

    chapters = client.get(f"/v1/projects/{pid}/chapters", headers=headers).json()
    ch1 = [c for c in chapters if "Rozdział 1" in c["title"]][0]
    ch1_id = ch1["id"]
    blocks = client.get(f"/v1/chapters/{ch1_id}/blocks", headers=headers).json()
    target_block = blocks[1]
    b_id = target_block["id"]

    # 1. Create a span on target_block (e.g. skip first 8 chars)
    create_span_res = client.post(
        f"/v1/chapters/{ch1_id}/spans",
        json={
            "block_id": b_id,
            "start": 0,
            "end": 8,
            "kind": "skip",
            "spoken": None,
        },
        headers=headers,
    )
    assert create_span_res.status_code == 201
    span = create_span_res.json()
    span_id = span["id"]
    assert span["kind"] == "skip"
    assert span["start"] == 0
    assert span["end"] == 8

    # 2. List spans for chapter
    spans_res = client.get(f"/v1/chapters/{ch1_id}/spans", headers=headers)
    assert spans_res.status_code == 200
    span_ids = [s["id"] for s in spans_res.json()]
    assert span_id in span_ids

    # 3. Test spoken view: the skipped 8 characters should be omitted
    spoken_text = client.get(
        f"/v1/chapters/{ch1_id}/text",
        params={"view": "spoken"},
        headers=headers,
    ).json()["text"]
    skipped_substr = target_block["text"][0:8]
    assert skipped_substr not in spoken_text

    # 4. Update span
    patch_span_res = client.patch(
        f"/v1/spans/{span_id}",
        json={"kind": "dialogue", "gender": "male", "pause_ms": 150},
        headers=headers,
    )
    assert patch_span_res.status_code == 200
    updated_span = patch_span_res.json()
    assert updated_span["kind"] == "dialogue"
    assert updated_span["gender"] == "male"
    assert updated_span["pause_ms"] == 150

    # 5. Delete span
    del_res = client.delete(f"/v1/spans/{span_id}", headers=headers)
    assert del_res.status_code == 204

    # Confirm deleted
    spans_after = client.get(f"/v1/chapters/{ch1_id}/spans", headers=headers).json()
    assert span_id not in [s["id"] for s in spans_after]


def test_search_and_replace_api(tmp_path: Path) -> None:
    client, headers, pid = _setup_ingested_client(tmp_path)

    # 1. Search text
    search_res = client.post(
        f"/v1/projects/{pid}/search",
        json={"query": "Michał", "case_sensitive": True},
        headers=headers,
    )
    assert search_res.status_code == 200
    sdata = search_res.json()
    assert sdata["count"] >= 1
    assert all("Michał" in h["context"] for h in sdata["hits"])

    # 2. Replace preview (dry_run=True)
    replace_preview_res = client.post(
        f"/v1/projects/{pid}/replace",
        json={
            "query": "Michał",
            "replacement": "Piotr",
            "case_sensitive": True,
            "dry_run": True,
        },
        headers=headers,
    )
    assert replace_preview_res.status_code == 200
    pdata = replace_preview_res.json()
    assert pdata["count"] >= 1
    assert pdata["previews"] is not None
    assert len(pdata["previews"]) >= 1

    # 3. Apply replace (dry_run=False)
    replace_res = client.post(
        f"/v1/projects/{pid}/replace",
        json={
            "query": "Michał",
            "replacement": "Piotr",
            "case_sensitive": True,
            "dry_run": False,
        },
        headers=headers,
    )
    assert replace_res.status_code == 200
    assert replace_res.json()["count"] >= 1

    # 4. Search for original term should now return 0 hits
    search_old = client.post(
        f"/v1/projects/{pid}/search",
        json={"query": "Michał", "case_sensitive": True},
        headers=headers,
    ).json()
    assert search_old["count"] == 0

    # Search for new term should return the hits
    search_new = client.post(
        f"/v1/projects/{pid}/search",
        json={"query": "Piotr", "case_sensitive": True},
        headers=headers,
    ).json()
    assert search_new["count"] >= 1
