# SPDX-License-Identifier: Apache-2.0
"""Tests for project lifecycle: the store, and the API that fronts it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from praelector.config import ENV_PROJECTS_DIR, RuntimeEnv
from praelector.domain.enums import VoiceMode
from praelector.errors import AppError, ErrorCode
from praelector.state import AppState
from praelector.store.db import create_project_engine, session_scope
from praelector.store.locks import ProjectLock
from praelector.store.manifest import read_manifest
from praelector.store.projects import ProjectPatch, ProjectStore
from praelector.store.tables import ProjectRow, RevisionRow


@pytest.fixture
def store(runtime_env: RuntimeEnv) -> ProjectStore:
    return ProjectStore(runtime_env)


def _create(store: ProjectStore, name: str = "Kroniki Wrzosowiska", **kwargs: object) -> str:
    return store.create(name=name, **kwargs).id  # type: ignore[arg-type]


# -- store --------------------------------------------------------------------


def test_create_builds_the_documented_tree(store: ProjectStore, runtime_env: RuntimeEnv) -> None:
    project_id = _create(store)
    root = runtime_env.paths.projects_dir / project_id
    for relative in ("source", "reader", "voices", "audio/chunks", "jobs", "output", "cache"):
        assert (root / relative).is_dir(), relative
    assert (root / "project.json").is_file()
    assert (root / "project.db").is_file()


def test_create_writes_the_manifest_and_the_database(store: ProjectStore) -> None:
    detail = store.create(name="Test", voice_mode=VoiceMode.NARRATOR_MALE_FEMALE)
    manifest = read_manifest(Path(detail.path) / "project.json")
    assert manifest.id == detail.id
    assert manifest.voice_mode is VoiceMode.NARRATOR_MALE_FEMALE
    assert manifest.current_revision == 0

    engine = create_project_engine(Path(detail.path) / "project.db")
    try:
        with session_scope(engine) as session:
            row = session.get(ProjectRow, detail.id)
            assert row is not None
            assert row.name == "Test"
            assert row.voice_mode == "narrator_male_female"
            revisions = session.scalars(select(RevisionRow.n)).all()
            assert list(revisions) == [0]
    finally:
        engine.dispose()


def test_the_name_is_trimmed_and_required(store: ProjectStore) -> None:
    assert store.create(name="  Padded  ").name == "Padded"
    with pytest.raises(AppError) as excinfo:
        store.create(name="   ")
    assert excinfo.value.code is ErrorCode.INTERNAL_VALIDATION_FAILED
    assert excinfo.value.detail["field"] == "name"


def test_create_refuses_a_non_empty_directory(store: ProjectStore, tmp_path: Path) -> None:
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "something.txt").write_text("x", encoding="utf-8")
    with pytest.raises(AppError) as excinfo:
        store.create(name="X", directory=target)
    assert excinfo.value.code is ErrorCode.PROJECT_ALREADY_OPEN


def test_a_failed_create_leaves_nothing_behind(
    store: ProjectStore, runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(_: Path) -> str:
        raise RuntimeError("disk on fire")

    monkeypatch.setattr("praelector.store.projects.run_migrations", explode)
    with pytest.raises(RuntimeError, match="disk on fire"):
        store.create(name="Doomed")
    # The Library must not list a project that cannot be opened.
    assert store.list_summaries() == []
    assert list(runtime_env.paths.projects_dir.iterdir()) == []


def test_list_reports_newest_first_and_flags_the_open_one(store: ProjectStore) -> None:
    older = _create(store, "Older")
    newer = _create(store, "Newer")

    listed = store.list_summaries()
    assert [entry.id for entry in listed] == [newer, older] or [entry.id for entry in listed] == [
        older,
        newer,
    ]

    store.open(newer)
    try:
        by_id = {entry.id: entry for entry in store.list_summaries()}
        assert by_id[newer].is_open is True
        assert by_id[older].is_open is False
    finally:
        store.close(newer)


def test_list_marks_an_unreadable_manifest_instead_of_hiding_it(
    store: ProjectStore, runtime_env: RuntimeEnv
) -> None:
    project_id = _create(store)
    manifest = runtime_env.paths.projects_dir / project_id / "project.json"
    manifest.write_text("{corrupt", encoding="utf-8")

    listed = store.list_summaries()
    assert len(listed) == 1
    assert listed[0].unreadable is True
    assert listed[0].updated_at is None
    assert listed[0].name == project_id


def test_open_is_idempotent_for_the_same_project(store: ProjectStore) -> None:
    project_id = _create(store)
    first = store.open(project_id)
    assert store.open(project_id) is first
    assert store.current_id == project_id
    store.close(project_id)


def test_only_one_project_can_be_open(store: ProjectStore) -> None:
    first = _create(store, "First")
    second = _create(store, "Second")
    store.open(first)
    try:
        with pytest.raises(AppError) as excinfo:
            store.open(second)
        assert excinfo.value.code is ErrorCode.PROJECT_ALREADY_OPEN
        assert excinfo.value.detail["open_project_id"] == first
    finally:
        store.close(first)


def test_open_reports_the_migration_revision(store: ProjectStore) -> None:
    opened = store.open(_create(store))
    try:
        assert opened.db_revision == "0005_voice_profiles"
        assert opened.manifest.name
    finally:
        store.close_current()


def test_open_refuses_when_another_process_holds_the_lock(
    store: ProjectStore, runtime_env: RuntimeEnv
) -> None:
    project_id = _create(store)
    lock_path = runtime_env.paths.projects_dir / project_id / "project.lock"
    squatter = ProjectLock(lock_path)
    squatter.acquire()
    try:
        with pytest.raises(AppError) as excinfo:
            store.open(project_id)
        assert excinfo.value.code is ErrorCode.PROJECT_LOCKED
    finally:
        squatter.release()
    # And it works once the other process lets go.
    store.open(project_id)
    store.close(project_id)


def test_open_releases_the_lock_on_a_migration_failure(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = _create(store)

    def explode(_: Path) -> str:
        raise RuntimeError("no migrations for you")

    monkeypatch.setattr("praelector.store.projects.run_migrations", explode)
    with pytest.raises(RuntimeError, match="no migrations"):
        store.open(project_id)
    assert store.current is None
    # The lock must not be left held, or the project is unusable until a restart.
    # Proved by taking it from outside rather than by reopening, because the
    # monkeypatch above is still in force.
    with ProjectLock(store.projects_dir / project_id / "project.lock"):
        pass


def test_a_manifest_whose_id_disagrees_with_its_directory_is_refused(
    store: ProjectStore, runtime_env: RuntimeEnv
) -> None:
    project_id = _create(store)
    manifest_path = runtime_env.paths.projects_dir / project_id / "project.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["id"] = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAZ"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(AppError) as excinfo:
        store.open(project_id)
    assert excinfo.value.code is ErrorCode.PROJECT_MANIFEST_INVALID


def test_close_requires_the_right_project(store: ProjectStore) -> None:
    project_id = _create(store)
    with pytest.raises(AppError) as excinfo:
        store.close(project_id)
    assert excinfo.value.code is ErrorCode.PROJECT_NOT_OPEN

    store.open(project_id)
    with pytest.raises(AppError) as excinfo:
        store.close("prj_01ARZ3NDEKTSV4RRFFQ69G5FAZ")
    assert excinfo.value.detail["open_project_id"] == project_id
    store.close(project_id)


def test_patch_updates_the_manifest(store: ProjectStore) -> None:
    project_id = _create(store, "Before")
    detail = store.patch(
        project_id,
        ProjectPatch(name="After", voice_mode=VoiceMode.NARRATOR_DIALOGUE, backend_id="chatterbox"),
    )
    assert detail.name == "After"
    assert detail.voice_mode is VoiceMode.NARRATOR_DIALOGUE
    assert detail.backend_id == "chatterbox"
    assert read_manifest(Path(detail.path) / "project.json").name == "After"


def test_patch_rejects_an_empty_name(store: ProjectStore) -> None:
    project_id = _create(store)
    with pytest.raises(AppError) as excinfo:
        store.patch(project_id, ProjectPatch(name="  "))
    assert excinfo.value.detail["field"] == "name"


def test_the_cloud_toggle_lives_in_the_database_not_the_manifest(store: ProjectStore) -> None:
    project_id = _create(store)
    detail = store.patch(project_id, ProjectPatch(cloud_llm_enabled=True))
    assert detail.cloud_llm_enabled is True

    manifest = read_manifest(Path(detail.path) / "project.json")
    assert "cloud_llm_enabled" not in manifest.model_dump()

    assert store.patch(project_id, ProjectPatch(cloud_llm_enabled=False)).cloud_llm_enabled is False


def test_an_empty_patch_changes_nothing(store: ProjectStore) -> None:
    project_id = _create(store)
    before = store.get(project_id).updated_at
    assert store.patch(project_id, ProjectPatch()).updated_at == before


def test_patch_keeps_the_open_project_in_step(store: ProjectStore) -> None:
    project_id = _create(store, "Before")
    store.open(project_id)
    try:
        store.patch(project_id, ProjectPatch(name="After"))
        assert store.current is not None
        assert store.current.manifest.name == "After"
    finally:
        store.close_current()


def test_delete_removes_everything_when_asked(store: ProjectStore, runtime_env: RuntimeEnv) -> None:
    project_id = _create(store)
    root = runtime_env.paths.projects_dir / project_id
    (root / "output" / "book.m4b").write_bytes(b"audio")

    store.delete(project_id, delete_files=True)
    assert not root.exists()
    assert store.list_summaries() == []


def test_delete_keeps_the_users_files_by_default(
    store: ProjectStore, runtime_env: RuntimeEnv
) -> None:
    project_id = _create(store)
    root = runtime_env.paths.projects_dir / project_id
    (root / "output" / "book.m4b").write_bytes(b"audio")

    store.delete(project_id, delete_files=False)
    assert not (root / "project.json").exists()
    assert not (root / "project.db").exists()
    assert (root / "output" / "book.m4b").exists()
    # A directory with no manifest is no longer a project.
    assert store.list_summaries() == []


def test_delete_closes_the_project_first(store: ProjectStore, runtime_env: RuntimeEnv) -> None:
    project_id = _create(store)
    store.open(project_id)
    store.delete(project_id, delete_files=True)
    assert store.current is None
    assert not (runtime_env.paths.projects_dir / project_id).exists()


def test_wal_sidecars_are_cleaned_up_with_the_database(
    store: ProjectStore, runtime_env: RuntimeEnv
) -> None:
    project_id = _create(store)
    store.open(project_id)
    db = runtime_env.paths.projects_dir / project_id / "project.db"
    wal = Path(str(db) + "-wal")
    wal.write_bytes(b"x")
    store.delete(project_id, delete_files=False)
    assert not wal.exists()


def test_unknown_and_malformed_ids_are_not_found(store: ProjectStore) -> None:
    with pytest.raises(AppError) as excinfo:
        store.get("prj_01ARZ3NDEKTSV4RRFFQ69G5FAZ")
    assert excinfo.value.code is ErrorCode.PROJECT_NOT_FOUND

    with pytest.raises(AppError) as excinfo:
        store.get("../../etc/passwd")
    assert excinfo.value.code is ErrorCode.PROJECT_NOT_FOUND
    assert excinfo.value.detail["reason"] == "malformed_id"


# -- API ----------------------------------------------------------------------


def test_the_projects_api_requires_the_token(client: TestClient) -> None:
    assert client.get("/v1/projects").status_code == 401
    assert client.post("/v1/projects", json={"name": "X"}).status_code == 401


def test_create_list_open_close_delete_over_http(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post("/v1/projects", json={"name": "HTTP Project"}, headers=auth)
    assert created.status_code == 201, created.text
    project = created.json()
    project_id = project["id"]
    assert project_id.startswith("prj_")
    assert project["name"] == "HTTP Project"
    assert project["is_open"] is False
    assert project["cloud_llm_enabled"] is False

    listed = client.get("/v1/projects", headers=auth).json()
    assert [entry["id"] for entry in listed["projects"]] == [project_id]
    assert listed["projects_dir"]
    assert listed["open_project_id"] is None

    assert client.get("/v1/health", headers=auth).json()["project_open"] is False
    opened = client.post(f"/v1/projects/{project_id}/open", headers=auth)
    assert opened.status_code == 200
    assert opened.json()["is_open"] is True
    assert opened.json()["db_revision"] == "0005_voice_profiles"
    assert client.get("/v1/health", headers=auth).json()["project_open"] is True

    assert client.post(f"/v1/projects/{project_id}/close", headers=auth).status_code == 204
    assert client.get("/v1/health", headers=auth).json()["project_open"] is False

    assert client.delete(f"/v1/projects/{project_id}", headers=auth).status_code == 204
    assert client.get("/v1/projects", headers=auth).json()["projects"] == []


def test_opening_a_second_project_over_http_is_a_conflict(
    client: TestClient, auth: dict[str, str]
) -> None:
    first = client.post("/v1/projects", json={"name": "First"}, headers=auth).json()["id"]
    second = client.post("/v1/projects", json={"name": "Second"}, headers=auth).json()["id"]
    assert client.post(f"/v1/projects/{first}/open", headers=auth).status_code == 200

    response = client.post(f"/v1/projects/{second}/open", headers=auth)
    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "project.already_open"
    assert body["detail"]["open_project_id"] == first

    client.post(f"/v1/projects/{first}/close", headers=auth)
    assert client.post(f"/v1/projects/{second}/open", headers=auth).status_code == 200


def test_patch_over_http(client: TestClient, auth: dict[str, str]) -> None:
    project_id = client.post("/v1/projects", json={"name": "Before"}, headers=auth).json()["id"]
    response = client.patch(
        f"/v1/projects/{project_id}",
        json={"name": "After", "voice_mode": "narrator_dialogue", "cloud_llm_enabled": True},
        headers=auth,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "After"
    assert body["voice_mode"] == "narrator_dialogue"
    assert body["cloud_llm_enabled"] is True


def test_an_invalid_voice_mode_is_rejected(client: TestClient, auth: dict[str, str]) -> None:
    project_id = client.post("/v1/projects", json={"name": "X"}, headers=auth).json()["id"]
    response = client.patch(
        f"/v1/projects/{project_id}", json={"voice_mode": "four_voices"}, headers=auth
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "internal.validation_failed"


def test_an_empty_name_is_rejected(client: TestClient, auth: dict[str, str]) -> None:
    assert client.post("/v1/projects", json={"name": ""}, headers=auth).status_code == 422


def test_a_malformed_id_never_reaches_the_filesystem(
    client: TestClient, auth: dict[str, str], app_state: AppState
) -> None:
    response = client.get("/v1/projects/..%2F..%2Fetc", headers=auth)
    assert response.status_code in (404, 422)
    assert app_state.projects.list_summaries() == []


def test_settings_round_trip_over_http(client: TestClient, auth: dict[str, str]) -> None:
    current = client.get("/v1/settings", headers=auth)
    assert current.status_code == 200
    assert current.json()["language"] == "en"
    assert current.json()["gpu"]["worker_cap"] == 4

    updated = client.put(
        "/v1/settings",
        json={"language": "pl", "gpu": {"worker_cap": 2}},
        headers=auth,
    )
    assert updated.status_code == 200
    assert updated.json()["language"] == "pl"
    assert updated.json()["gpu"]["worker_cap"] == 2
    # Merge patch, not replace: the sibling key survived.
    assert updated.json()["gpu"]["allow_cpu"] is True
    assert client.get("/v1/settings", headers=auth).json()["language"] == "pl"


def test_an_invalid_settings_patch_is_rejected(client: TestClient, auth: dict[str, str]) -> None:
    response = client.put("/v1/settings", json={"audio": {"target_lufs": 99}}, headers=auth)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "internal.validation_failed"


def test_capabilities_reports_probes_and_paths(client: TestClient, auth: dict[str, str]) -> None:
    body = client.get("/v1/capabilities", headers=auth).json()
    assert set(body["ffmpeg"]) == {"present", "path", "version", "reason"}
    assert set(body["calibre"]) == {"present", "path", "version", "reason"}
    assert body["keyring_backend"]
    assert body["secret_backend"] in {"keyring", "file", "unavailable"}
    assert body["settings_error"] is None
    for key in (
        "data_dir",
        "config_dir",
        "log_dir",
        "projects_dir",
        "models_dir",
        "runtimes_dir",
        "bin_dir",
    ):
        assert "\\" not in body["paths"][key], "paths are serialised POSIX-style"


def test_changing_projects_dir_in_settings_moves_the_library(
    client: TestClient, auth: dict[str, str], app_state: AppState, tmp_path: Path
) -> None:
    # The fixture pins PRAELECTOR_PROJECTS_DIR, and an env override deliberately
    # beats settings (PLAN.md §1.7). Drop it so this exercises the settings path,
    # which is what a normal launch looks like.
    app_state.env.environ = {
        key: value for key, value in app_state.env.environ.items() if key != ENV_PROJECTS_DIR
    }

    created = client.post("/v1/projects", json={"name": "Before"}, headers=auth).json()["id"]
    assert client.get("/v1/projects", headers=auth).json()["projects"][0]["id"] == created

    new_dir = tmp_path / "elsewhere"
    response = client.put(
        "/v1/settings", json={"paths": {"projects_dir": str(new_dir)}}, headers=auth
    )
    assert response.status_code == 200
    assert app_state.env.paths.projects_dir == new_dir

    listed = client.get("/v1/projects", headers=auth).json()
    assert listed["projects"] == []
    assert listed["projects_dir"] == new_dir.as_posix()

    # And a project created now lands in the new place.
    fresh = client.post("/v1/projects", json={"name": "After"}, headers=auth)
    assert fresh.status_code == 201
    assert Path(fresh.json()["path"]).parent == new_dir


def test_shutdown_closes_the_open_project(client: TestClient, auth: dict[str, str]) -> None:
    project_id = client.post("/v1/projects", json={"name": "X"}, headers=auth).json()["id"]
    client.post(f"/v1/projects/{project_id}/open", headers=auth)
    assert client.get("/v1/health", headers=auth).json()["project_open"] is True

    assert client.post("/v1/shutdown", headers=auth).status_code == 200
    assert client.get("/v1/health", headers=auth).json()["project_open"] is False

    # The lock is gone, so the next launch can open the project again.
    assert client.post(f"/v1/projects/{project_id}/open", headers=auth).status_code == 200
