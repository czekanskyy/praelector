# SPDX-License-Identifier: Apache-2.0
"""Chunk packing and render keys (TTS-07, JB-05)."""

from __future__ import annotations

from praelector.domain.hashing import render_key
from praelector.jobs.chunker import SpokenRun, plan_runs

_PROFILE = "voice-1"
_HASH = "abc"


def _run(text: str, *, kind: str = "narration", slot: str = "narrator") -> SpokenRun:
    return SpokenRun("ch-1", slot, kind, text, _PROFILE, _HASH)


def _plan(runs: list[SpokenRun], limit: int = 40) -> list[str]:
    items = plan_runs(
        runs,
        max_input_chars=limit,
        backend_id="fake",
        adapter_version="1",
        model_revision="rev",
    )
    return [item.spoken_text for item in items]


def test_short_sentences_pack_until_the_limit() -> None:
    text = "Ala ma kota. Kot ma Ale."
    assert _plan([_run(text)], limit=40) == [text]


def test_a_sentence_past_the_limit_starts_a_new_chunk() -> None:
    pieces = _plan([_run("Ala ma kota. Kot ma Ale.")], limit=14)
    assert pieces == ["Ala ma kota.", "Kot ma Ale."]


def test_a_short_dialogue_span_stays_one_chunk() -> None:
    text = "Nie zdążymy. Deadline mamy o osiemnastej."
    items = plan_runs(
        [_run(text, kind="dialogue", slot="female")],
        max_input_chars=80,
        backend_id="fake",
        adapter_version="1",
        model_revision="rev",
    )
    assert [item.spoken_text for item in items] == [text]
    assert items[0].voice_slot == "female"
    assert items[0].kind == "tts"


def test_narration_and_dialogue_do_not_share_a_chunk() -> None:
    pieces = _plan(
        [_run("Anna milczała.", slot="narrator"), _run("Chodź.", kind="dialogue", slot="female")],
        limit=80,
    )
    assert pieces == ["Anna milczała.", "Chodź."]


def test_an_oversized_sentence_splits_on_a_comma_not_inside_a_word() -> None:
    text = "abcdefghij, klmnopqrst"
    pieces = _plan([_run(text)], limit=12)
    assert pieces == ["abcdefghij", "klmnopqrst"]


def test_a_word_longer_than_the_limit_is_not_split() -> None:
    word = "Nadzwyczajnie"
    pieces = _plan([_run(word)], limit=4)
    assert pieces == [word]


def test_silence_is_not_a_tts_call() -> None:
    items = plan_runs(
        [_run("", kind="silence")],
        max_input_chars=20,
        backend_id="fake",
        adapter_version="1",
        model_revision="rev",
    )
    assert [(item.kind, item.spoken_text) for item in items] == [("silence", "")]


def test_render_key_ignores_param_order_and_includes_a_seed_only_when_set() -> None:
    common = {
        "spoken_text": "Ala",
        "voice_slot": "narrator",
        "voice_profile_id": _PROFILE,
        "voice_profile_content_hash": _HASH,
        "backend_id": "fake",
        "adapter_version": "1",
        "model_revision": "rev",
    }
    first = render_key(**common, params={"b": 1, "a": 2})
    second = render_key(**common, params={"a": 2, "b": 1})
    seeded = render_key(**common, params={"a": 2, "b": 1}, seed=7)
    assert first == second
    assert seeded != first


def test_ordinals_follow_plan_order() -> None:
    items = plan_runs(
        [_run("Pierwsze zdanie."), _run("Drugie.", kind="dialogue", slot="dialogue")],
        max_input_chars=40,
        backend_id="fake",
        adapter_version="1",
        model_revision="rev",
    )
    assert [item.ordinal for item in items] == [0, 1]
