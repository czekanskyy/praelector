# SPDX-License-Identifier: Apache-2.0
"""Opening a project rebuilds the chunk index from the files that still match."""

from __future__ import annotations

import json

from sqlalchemy import select

from praelector.audio.render_fake import render_chunk
from praelector.config import RuntimeEnv
from praelector.store.db import session_scope
from praelector.store.project_dir import layout_for
from praelector.store.projects import ProjectStore
from praelector.store.tables import ChunkRow


def test_open_keeps_a_matching_chunk_and_forgets_one_that_was_removed(
    runtime_env: RuntimeEnv,
) -> None:
    store = ProjectStore(runtime_env)
    detail = store.create(name="Index")
    root = runtime_env.paths.projects_dir / detail.id
    layout = layout_for(root)
    good = "ab" + "1" * 30
    wav = layout.chunk_wav(good)
    render_chunk("a" * 14, wav.with_name(wav.name + ".part"), wav, wav.with_suffix(".json"))

    opened = store.open(detail.id)
    try:
        assert opened.db_revision == "0005_voice_profiles"
        with session_scope(opened.engine) as session:
            row = session.get(ChunkRow, good)
            assert row is not None
            assert row.size > 0
            assert row.rel_path.endswith(f"{good}.wav")
    finally:
        store.close_current()

    wav.unlink()
    layout.chunk_sidecar(good).unlink()
    store.open(detail.id)
    try:
        with session_scope(store.require_open(detail.id).engine) as session:
            assert session.scalars(select(ChunkRow.render_key)).all() == []
    finally:
        store.close_current()


def test_open_does_not_index_a_sidecar_whose_size_was_changed(runtime_env: RuntimeEnv) -> None:
    store = ProjectStore(runtime_env)
    detail = store.create(name="Torn")
    layout = layout_for(runtime_env.paths.projects_dir / detail.id)
    key = "cd" + "2" * 30
    wav = layout.chunk_wav(key)
    sidecar = wav.with_suffix(".json")
    render_chunk("a" * 14, wav.with_name(wav.name + ".part"), wav, sidecar)
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    meta["size"] = 1
    sidecar.write_text(json.dumps(meta), encoding="utf-8")

    store.open(detail.id)
    try:
        with session_scope(store.require_open(detail.id).engine) as session:
            assert session.get(ChunkRow, key) is None
    finally:
        store.close_current()
    assert (layout.quarantine / key[:2] / f"{key}.wav").is_file()
