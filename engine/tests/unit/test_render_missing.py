# SPDX-License-Identifier: Apache-2.0
"""Only a missing speech chunk is rendered again."""

from __future__ import annotations

from pathlib import Path

from praelector.audio.render_fake import wav_seconds
from praelector.audio.render_missing import render_missing
from praelector.jobs.chunker import PlanItem
from praelector.jobs.reuse import chunk_reusable


def _item(ordinal: int, kind: str = "tts", text: str = "abcd") -> PlanItem:
    return PlanItem(ordinal, "chp_1", "narrator", text, kind, f"k{ordinal}")


def test_a_reusable_chunk_and_a_pause_are_skipped(tmp_path: Path) -> None:
    ready = _item(0, text="a" * 14)
    fresh = _item(1, text="b" * 14)
    pause = _item(2, "silence", text="")

    def paths(item: PlanItem) -> tuple[Path, Path, Path]:
        wav = tmp_path / f"{item.render_key}.wav"
        return wav.with_name(wav.name + ".part"), wav, wav.with_suffix(".json")

    first = render_missing([ready], paths_for=paths, reusable=lambda _item: False)
    assert first == [0]

    def already(item: PlanItem) -> bool:
        _part, wav, sidecar = paths(item)
        return chunk_reusable(wav, sidecar, probe=wav_seconds)

    again = render_missing([ready, pause, fresh], paths_for=paths, reusable=already)
    assert again == [1]
    _part, wav, sidecar = paths(fresh)
    assert chunk_reusable(wav, sidecar, probe=wav_seconds)
