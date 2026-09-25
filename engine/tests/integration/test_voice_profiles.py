# SPDX-License-Identifier: Apache-2.0
"""Voice profiles: one assigned slot per project, ref text required."""

from __future__ import annotations

import pytest

from praelector.config import RuntimeEnv
from praelector.errors import AppError, ErrorCode
from praelector.store.db import session_scope
from praelector.store.projects import ProjectStore
from praelector.voices.profiles import (
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    set_slot,
)


def _create(session, project_id: str, *, name: str, slot: str | None) -> str:
    profile = create_profile(
        session,
        project_id=project_id,
        name=name,
        source_filename=f"{name}.wav",
        source_sha256="ab" * 32,
        ref_text="to jest próbka",
        processed_rel=f"voices/{name}.wav",
        sample_rate=24000,
        duration_s=1.5,
        content_hash="cd" * 16,
        chain_version="1",
        slot=slot,
    )
    return profile.id


def test_create_lists_and_keeps_one_narrator(runtime_env: RuntimeEnv) -> None:
    store = ProjectStore(runtime_env)
    detail = store.create(name="Voices")
    opened = store.open(detail.id)
    try:
        assert opened.db_revision == "0006_lexicon"
        with session_scope(opened.engine) as session:
            narrator = _create(session, detail.id, name="Ada", slot="narrator")
            spare = _create(session, detail.id, name="Ben", slot=None)
            assert [item.id for item in list_profiles(session, detail.id)] == [narrator, spare]
            assert get_profile(session, narrator).slot == "narrator"
            with pytest.raises(AppError) as caught:
                _create(session, detail.id, name="Cara", slot="narrator")
            assert caught.value.code is ErrorCode.VOICE_SLOT_CONFLICT
    finally:
        store.close_current()


def test_clearing_a_slot_lets_another_profile_take_it(runtime_env: RuntimeEnv) -> None:
    store = ProjectStore(runtime_env)
    detail = store.create(name="Swap")
    opened = store.open(detail.id)
    try:
        with session_scope(opened.engine) as session:
            first = _create(session, detail.id, name="Ada", slot="narrator")
            second = _create(session, detail.id, name="Ben", slot=None)
            set_slot(session, first, None)
            moved = set_slot(session, second, "narrator")
            assert moved.slot == "narrator"
            assert get_profile(session, first).slot is None
            delete_profile(session, first)
            with pytest.raises(AppError) as caught:
                get_profile(session, first)
            assert caught.value.code is ErrorCode.VOICE_NOT_FOUND
    finally:
        store.close_current()


def test_blank_ref_text_is_rejected(runtime_env: RuntimeEnv) -> None:
    store = ProjectStore(runtime_env)
    detail = store.create(name="Blank")
    opened = store.open(detail.id)
    try:
        with session_scope(opened.engine) as session:
            with pytest.raises(AppError) as caught:
                create_profile(
                    session,
                    project_id=detail.id,
                    name="Ada",
                    source_filename="a.wav",
                    source_sha256="ab" * 32,
                    ref_text="   ",
                    processed_rel="voices/a.wav",
                    sample_rate=24000,
                    duration_s=1.0,
                    content_hash="cd" * 16,
                    chain_version="1",
                )
            assert caught.value.code is ErrorCode.VOICE_REF_TEXT_REQUIRED
    finally:
        store.close_current()
