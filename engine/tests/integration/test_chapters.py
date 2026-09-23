# SPDX-License-Identifier: Apache-2.0
"""Chapter ingest, tree operations, plain-text commit and find/replace."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.ebook_factory import encryption_xml, spine_epub, tiny_epub3, with_meta

AES_128_CBC = "http://www.w3.org/2001/04/xmlenc#aes128-cbc"


def _open_project(
    client: TestClient, auth: dict[str, str], name: str = "Lector"
) -> tuple[str, Path]:
    created = client.post("/v1/projects", json={"name": name}, headers=auth)
    assert created.status_code == 201, created.text
    body = created.json()
    project_id = body["id"]
    opened = client.post(f"/v1/projects/{project_id}/open", headers=auth)
    assert opened.status_code == 200, opened.text
    return project_id, Path(body["path"])


def _ingest(
    client: TestClient, auth: dict[str, str], project_id: str, epub: Path
) -> dict[str, object]:
    response = client.post(
        f"/v1/projects/{project_id}/ingest",
        json={"path": str(epub)},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def _chapters(client: TestClient, auth: dict[str, str], project_id: str) -> dict[str, object]:
    response = client.get(f"/v1/projects/{project_id}/chapters", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _text(
    client: TestClient, auth: dict[str, str], chapter_id: str, view: str = "display"
) -> dict[str, object]:
    response = client.get(f"/v1/chapters/{chapter_id}/text", params={"view": view}, headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


def _two_chapter_epub() -> bytes:
    return spine_epub(
        [
            "<h1>Alpha</h1><p>Shared token lives in the alpha chapter.</p>",
            "<h1>Beta</h1><p>Shared token lives in the beta chapter too.</p>",
        ]
    )


def _three_chapter_epub() -> bytes:
    return spine_epub(
        [
            "<h1>One</h1><p>First chapter text is long enough to keep.</p>",
            "<h1>Two</h1><p>Second chapter text is long enough to keep.</p>",
            "<h1>Three</h1><p>Third chapter text is long enough to keep.</p>",
        ]
    )


def test_commit_copies_the_epub_and_does_not_mutate_the_upload(
    client: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    project_id, root = _open_project(client, auth)
    source = _write(tmp_path / "book.epub", tiny_epub3())
    digest = source.read_bytes()
    body = _ingest(client, auth, project_id, source)
    assert source.read_bytes() == digest
    assert body["chapter_count"] == 1
    assert body["original_rel"] == "source/original.epub"
    assert body["working_epub_rel"] == "source/working.epub"
    assert (root / "source" / "original.epub").read_bytes() == digest
    working = root / "source" / "working.epub"
    assert working.is_file()
    assert working.read_bytes().startswith(b"PK")
    assert working.resolve() != source.resolve()

    tree = _chapters(client, auth, project_id)
    chapters = tree["chapters"]
    assert isinstance(chapters, list)
    assert len(chapters) == 1
    assert chapters[0]["title"] == "Chapter One"
    assert chapters[0]["included"] is True
    assert chapters[0]["ordinal"] == 0
    loaded = _text(client, auth, chapters[0]["id"])
    assert loaded["text"] == "Chapter One\n\nIt was a bright cold day in April."
    spoken = _text(client, auth, chapters[0]["id"], view="spoken")
    assert spoken["text"] == loaded["text"]
    assert spoken["view"] == "spoken"


def test_commit_refuses_drm_empty_text_and_a_closed_project(
    client: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    created = client.post("/v1/projects", json={"name": "Closed"}, headers=auth)
    assert created.status_code == 201
    closed_id = created.json()["id"]
    closed_root = Path(created.json()["path"])
    source = _write(tmp_path / "book.epub", tiny_epub3())
    refused = client.post(
        f"/v1/projects/{closed_id}/ingest",
        json={"path": str(source)},
        headers=auth,
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "project.not_open"
    assert not (closed_root / "source" / "original.epub").exists()
    assert source.read_bytes() == tiny_epub3()

    project_id, root = _open_project(client, auth, name="Guards")
    locked = _write(
        tmp_path / "locked.epub",
        with_meta((("META-INF/encryption.xml", encryption_xml(AES_128_CBC, "OEBPS/ch01.xhtml")),)),
    )
    drm = client.post(
        f"/v1/projects/{project_id}/ingest",
        json={"path": str(locked)},
        headers=auth,
    )
    assert drm.status_code == 422
    assert drm.json()["error"]["code"] == "ebook.drm_detected"
    assert not (root / "source" / "original.epub").exists()

    empty = _write(tmp_path / "empty.epub", spine_epub(["a", "b", "c", "d"]))
    blank = client.post(
        f"/v1/projects/{project_id}/ingest",
        json={"path": str(empty)},
        headers=auth,
    )
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "ebook.empty_text"
    assert not (root / "source" / "original.epub").exists()

    mobi = _write(tmp_path / "book.mobi", b"\x00" * 60 + b"BOOKMOBI" + b"\x00" * 8)
    other = client.post(
        f"/v1/projects/{project_id}/ingest",
        json={"path": str(mobi)},
        headers=auth,
    )
    assert other.status_code == 415
    assert other.json()["error"]["code"] == "ebook.unsupported_format"


def test_put_keeps_a_block_id_when_its_text_changes_by_a_few_characters(
    client: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    project_id, _root = _open_project(client, auth)
    _ingest(client, auth, project_id, _write(tmp_path / "book.epub", tiny_epub3()))
    chapter_id = _chapters(client, auth, project_id)["chapters"][0]["id"]
    before = _text(client, auth, chapter_id)
    blocks = before["blocks"]
    assert isinstance(blocks, list)
    paragraph = blocks[-1]
    assert isinstance(paragraph, dict)
    tweaked = str(paragraph["text"])[:-3] + "xyz"
    parts = [tweaked if block["id"] == paragraph["id"] else str(block["text"]) for block in blocks]
    saved = client.put(
        f"/v1/chapters/{chapter_id}/text",
        json={"text": "\n\n".join(parts), "base_revision": before["revision"]},
        headers=auth,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["revision"] == 1
    assert body["orphaned_span_ids"] == []
    by_text = {block["text"]: block["id"] for block in body["blocks"]}
    assert by_text[tweaked] == paragraph["id"]
    for block in blocks:
        if block["id"] != paragraph["id"]:
            assert block["id"] in {item["id"] for item in body["blocks"]}

    conflict = client.put(
        f"/v1/chapters/{chapter_id}/text",
        json={"text": "A completely different paragraph.", "base_revision": 0},
        headers=auth,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "text.revision_conflict"

    same = client.put(
        f"/v1/chapters/{chapter_id}/text",
        json={"text": body["text"], "base_revision": body["revision"]},
        headers=auth,
    )
    assert same.status_code == 200
    assert same.json()["revision"] == body["revision"]


def test_rename_reorder_and_include_do_not_rewrite_block_text(
    client: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    project_id, _root = _open_project(client, auth)
    _ingest(client, auth, project_id, _write(tmp_path / "book.epub", _two_chapter_epub()))
    tree = _chapters(client, auth, project_id)
    assert tree["revision"] == 0
    chapters = tree["chapters"]
    assert isinstance(chapters, list)
    assert [chapter["title"] for chapter in chapters] == ["Alpha", "Beta"]
    before = [_text(client, auth, chapter["id"]) for chapter in chapters]

    renamed = client.patch(
        f"/v1/chapters/{chapters[0]['id']}",
        json={"title": "Alpha renamed"},
        headers=auth,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Alpha renamed"

    excluded = client.patch(
        f"/v1/chapters/{chapters[1]['id']}",
        json={"included": False},
        headers=auth,
    )
    assert excluded.status_code == 200
    assert excluded.json()["included"] is False

    order = [chapters[1]["id"], chapters[0]["id"]]
    reordered = client.post(
        f"/v1/projects/{project_id}/chapters/reorder",
        json={"order": order},
        headers=auth,
    )
    assert reordered.status_code == 200, reordered.text
    assert [chapter["id"] for chapter in reordered.json()["chapters"]] == order
    assert reordered.json()["revision"] == 0
    project = client.get(f"/v1/projects/{project_id}", headers=auth)
    assert project.json()["current_revision"] == 0

    after = [_text(client, auth, chapter["id"]) for chapter in chapters]
    assert [item["blocks"] for item in after] == [item["blocks"] for item in before]
    assert [item["text"] for item in after] == [item["text"] for item in before]


def test_merge_adjacent_chapters_and_refuse_a_gap(
    client: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    project_id, _root = _open_project(client, auth)
    _ingest(client, auth, project_id, _write(tmp_path / "book.epub", _three_chapter_epub()))
    chapters = _chapters(client, auth, project_id)["chapters"]
    assert isinstance(chapters, list)
    texts = [_text(client, auth, chapter["id"]) for chapter in chapters]
    gap = client.post(
        f"/v1/projects/{project_id}/chapters/merge",
        json={"ids": [chapters[0]["id"], chapters[2]["id"]]},
        headers=auth,
    )
    assert gap.status_code == 422
    assert gap.json()["error"]["code"] == "internal.validation_failed"

    merged = client.post(
        f"/v1/projects/{project_id}/chapters/merge",
        json={"ids": [chapters[1]["id"], chapters[0]["id"]]},
        headers=auth,
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["revision"] == 1
    survivor = merged.json()["chapter"]["id"]
    combined = _text(client, auth, survivor)
    assert combined["text"] == f"{texts[0]['text']}\n\n{texts[1]['text']}"
    old_ids = [block["id"] for text in texts[:2] for block in text["blocks"]]
    assert old_ids == [block["id"] for block in combined["blocks"]]
    remaining = _chapters(client, auth, project_id)["chapters"]
    assert isinstance(remaining, list)
    assert [chapter["id"] for chapter in remaining] == [survivor, chapters[2]["id"]]


def test_split_moves_whole_blocks_or_divides_one(
    client: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    project_id, _root = _open_project(client, auth)
    _ingest(client, auth, project_id, _write(tmp_path / "book.epub", tiny_epub3()))
    chapter_id = _chapters(client, auth, project_id)["chapters"][0]["id"]
    loaded = _text(client, auth, chapter_id)
    blocks = loaded["blocks"]
    assert isinstance(blocks, list)
    assert len(blocks) >= 2
    heading, paragraph = blocks[0], blocks[1]

    empty = client.post(
        f"/v1/chapters/{chapter_id}/split",
        json={"block_id": heading["id"], "offset": 0},
        headers=auth,
    )
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "internal.validation_failed"

    divided = client.post(
        f"/v1/chapters/{chapter_id}/split",
        json={"block_id": paragraph["id"], "offset": 0},
        headers=auth,
    )
    assert divided.status_code == 200, divided.text
    created = divided.json()["chapters"]
    assert created[0]["id"] == chapter_id
    left = _text(client, auth, created[0]["id"])
    right = _text(client, auth, created[1]["id"])
    assert left["text"] == heading["text"]
    assert [block["id"] for block in left["blocks"]] == [heading["id"]]
    assert right["text"] == paragraph["text"]
    assert [block["id"] for block in right["blocks"]] == [paragraph["id"]]

    midpoint = len(str(paragraph["text"])) // 2
    again = client.post(
        f"/v1/chapters/{created[1]['id']}/split",
        json={"block_id": paragraph["id"], "offset": midpoint},
        headers=auth,
    )
    assert again.status_code == 200, again.text
    pieces = again.json()["chapters"]
    head = _text(client, auth, pieces[0]["id"])
    tail = _text(client, auth, pieces[1]["id"])
    assert head["blocks"][0]["id"] == paragraph["id"]
    assert head["text"] + tail["text"] == paragraph["text"]
    assert tail["blocks"][0]["id"] != paragraph["id"]


def test_replace_dry_run_writes_nothing_and_stays_inside_the_chapter(
    client: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    project_id, _root = _open_project(client, auth)
    _ingest(client, auth, project_id, _write(tmp_path / "book.epub", _two_chapter_epub()))
    chapters = _chapters(client, auth, project_id)["chapters"]
    assert isinstance(chapters, list)
    alpha, beta = chapters
    before_alpha = _text(client, auth, alpha["id"])
    before_beta = _text(client, auth, beta["id"])

    missed = client.post(
        f"/v1/projects/{project_id}/replace",
        json={
            "query": "shared",
            "replacement": "kept",
            "dry_run": True,
            "chapter_id": alpha["id"],
        },
        headers=auth,
    )
    assert missed.status_code == 200, missed.text
    assert missed.json()["count"] == 0
    assert missed.json()["revision"] is None

    counted = client.post(
        f"/v1/projects/{project_id}/replace",
        json={
            "query": "Shared",
            "replacement": "Kept",
            "dry_run": True,
            "chapter_id": alpha["id"],
        },
        headers=auth,
    )
    assert counted.status_code == 200, counted.text
    assert counted.json()["count"] == 1
    assert counted.json()["dry_run"] is True
    assert counted.json()["revision"] is None
    assert _text(client, auth, alpha["id"])["text"] == before_alpha["text"]
    assert _chapters(client, auth, project_id)["revision"] == 0

    applied = client.post(
        f"/v1/projects/{project_id}/replace",
        json={
            "query": "Shared",
            "replacement": "Kept",
            "dry_run": False,
            "chapter_id": alpha["id"],
        },
        headers=auth,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["count"] == 1
    assert applied.json()["revision"] == 1
    assert "Kept token" in _text(client, auth, alpha["id"])["text"]
    assert _text(client, auth, beta["id"])["text"] == before_beta["text"]

    whole = client.post(
        f"/v1/projects/{project_id}/replace",
        json={
            "query": "Shared",
            "replacement": "Book",
            "dry_run": False,
            "all_chapters": True,
        },
        headers=auth,
    )
    assert whole.status_code == 200, whole.text
    assert whole.json()["count"] == 1
    assert "Book token" in _text(client, auth, beta["id"])["text"]
    assert "Kept token" in _text(client, auth, alpha["id"])["text"]
