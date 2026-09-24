# SPDX-License-Identifier: Apache-2.0
"""A torn chunk is quarantined; a matching pair stays reusable."""

from __future__ import annotations

import json
from pathlib import Path

from praelector.audio.render_fake import render_chunk, wav_seconds
from praelector.store.reconcile import reconcile_chunks


def _publish(root: Path, key: str) -> None:
    shard = root / "chunks" / key[:2]
    wav = shard / f"{key}.wav"
    render_chunk("a" * 14, wav.with_name(wav.name + ".part"), wav, wav.with_suffix(".json"))


def test_a_matching_pair_stays_and_a_mismatch_is_moved_aside(tmp_path: Path) -> None:
    good = "ab" + "1" * 30
    bad = "cd" + "2" * 30
    _publish(tmp_path, good)
    _publish(tmp_path, bad)
    sidecar = tmp_path / "chunks" / bad[:2] / f"{bad}.json"
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    meta["size"] = 1
    sidecar.write_text(json.dumps(meta), encoding="utf-8")
    partial = tmp_path / "chunks" / good[:2] / "leftover.wav.part"
    partial.write_bytes(b"partial")

    result = reconcile_chunks(
        tmp_path / "chunks",
        tmp_path / "quarantine",
        probe=wav_seconds,
    )

    assert result.reusable == [good]
    assert (tmp_path / "chunks" / good[:2] / f"{good}.wav").is_file()
    assert partial.is_file()
    assert not (tmp_path / "chunks" / bad[:2] / f"{bad}.wav").exists()
    assert (tmp_path / "quarantine" / bad[:2] / f"{bad}.wav").is_file()
    assert (tmp_path / "quarantine" / bad[:2] / f"{bad}.json").is_file()
    assert sorted(result.quarantined) == [f"{bad}.json", f"{bad}.wav"]


def test_a_wav_without_a_sidecar_is_not_reusable(tmp_path: Path) -> None:
    key = "ee" + "3" * 30
    _publish(tmp_path, key)
    (tmp_path / "chunks" / key[:2] / f"{key}.json").unlink()

    result = reconcile_chunks(tmp_path / "chunks", tmp_path / "quarantine", probe=wav_seconds)

    assert result.reusable == []
    assert (tmp_path / "quarantine" / key[:2] / f"{key}.wav").is_file()


def test_a_missing_chunks_dir_reconciles_to_nothing(tmp_path: Path) -> None:
    result = reconcile_chunks(tmp_path / "missing", tmp_path / "quarantine", probe=wav_seconds)
    assert result.reusable == []
    assert result.quarantined == []
