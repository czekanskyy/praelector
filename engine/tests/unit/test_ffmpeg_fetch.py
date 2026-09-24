# SPDX-License-Identifier: Apache-2.0
"""ffmpeg is fetched only after the LGPL acknowledgement, and only if the hash matches."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from praelector.audio.fetch import FFMPEG_SPDX, install_ffmpeg
from praelector.errors import AppError, ErrorCode


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_a_missing_acknowledgement_fetches_nothing(tmp_path: Path) -> None:
    called = False

    def fetch(_dest: Path) -> None:
        nonlocal called
        called = True

    with pytest.raises(AppError) as caught:
        install_ffmpeg(
            tmp_path,
            acknowledged=False,
            ffmpeg_sha256="ab",
            ffprobe_sha256="cd",
            fetch_ffmpeg=fetch,
            fetch_ffprobe=fetch,
        )
    assert caught.value.code is ErrorCode.AUDIO_FFMPEG_MISSING
    assert caught.value.detail["reason"] == "license_not_acknowledged"
    assert caught.value.detail["spdx"] == FFMPEG_SPDX
    assert called is False
    assert list(tmp_path.iterdir()) == []


def test_matching_bytes_land_in_bin_and_are_not_fetched_again(tmp_path: Path) -> None:
    ffmpeg_bytes = b"ffmpeg-bytes"
    ffprobe_bytes = b"ffprobe-bytes"
    fetches = {"ffmpeg": 0, "ffprobe": 0}

    def fetch_ffmpeg(dest: Path) -> None:
        fetches["ffmpeg"] += 1
        dest.write_bytes(ffmpeg_bytes)

    def fetch_ffprobe(dest: Path) -> None:
        fetches["ffprobe"] += 1
        dest.write_bytes(ffprobe_bytes)

    kwargs = {
        "acknowledged": True,
        "ffmpeg_sha256": _sha(ffmpeg_bytes),
        "ffprobe_sha256": _sha(ffprobe_bytes),
        "fetch_ffmpeg": fetch_ffmpeg,
        "fetch_ffprobe": fetch_ffprobe,
        "suffix": ".exe",
    }
    first, _probe = install_ffmpeg(tmp_path, **kwargs)
    install_ffmpeg(tmp_path, **kwargs)
    assert first.read_bytes() == ffmpeg_bytes
    assert (tmp_path / "ffprobe.exe").read_bytes() == ffprobe_bytes
    assert fetches == {"ffmpeg": 1, "ffprobe": 1}
    saved = json.loads((tmp_path / "ffmpeg.json").read_text(encoding="utf-8"))
    assert saved["spdx"] == FFMPEG_SPDX


def test_a_bad_checksum_drops_the_partial(tmp_path: Path) -> None:
    def fetch(dest: Path) -> None:
        dest.write_bytes(b"nope")

    with pytest.raises(AppError) as caught:
        install_ffmpeg(
            tmp_path,
            acknowledged=True,
            ffmpeg_sha256="0" * 64,
            ffprobe_sha256="0" * 64,
            fetch_ffmpeg=fetch,
            fetch_ffprobe=fetch,
        )
    assert caught.value.detail["reason"] == "checksum_mismatch"
    assert not (tmp_path / "ffmpeg").exists()
    assert not (tmp_path / "ffmpeg.partial").exists()
    assert not (tmp_path / "ffmpeg.json").exists()
