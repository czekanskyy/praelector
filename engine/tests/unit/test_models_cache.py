# SPDX-License-Identifier: Apache-2.0
"""Model cache checksum, resume, and the license gate. No network."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from praelector.errors import AppError, ErrorCode
from praelector.tts.models_cache import ModelAsset, ensure_asset

_BODY = b"model-bytes"
_ASSET = ModelAsset(
    name="model",
    sha256=hashlib.sha256(_BODY).hexdigest(),
    size_bytes=len(_BODY),
    relative_path="omnivoice/model.safetensors",
)


def test_an_unacknowledged_license_does_not_fetch(tmp_path: Path) -> None:
    def fetch(_dest: Path, _offset: int) -> int:
        raise AssertionError("fetch must not run")

    with pytest.raises(AppError) as excinfo:
        ensure_asset(tmp_path, _ASSET, acknowledged=False, fetch=fetch)
    assert excinfo.value.code is ErrorCode.TTS_LICENSE_NOT_ACKNOWLEDGED
    assert list(tmp_path.rglob("*")) == []


def test_a_download_is_hashed_and_renamed(tmp_path: Path) -> None:
    def fetch(dest: Path, offset: int) -> int:
        assert offset == 0
        dest.write_bytes(_BODY)
        return len(_BODY)

    path = ensure_asset(tmp_path, _ASSET, acknowledged=True, fetch=fetch)
    assert path.read_bytes() == _BODY
    assert not path.with_name(path.name + ".partial").exists()


def test_a_partial_file_resumes_from_its_length(tmp_path: Path) -> None:
    partial = tmp_path / "omnivoice" / "model.safetensors.partial"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(_BODY[:4])

    def fetch(dest: Path, offset: int) -> int:
        assert offset == 4
        with dest.open("ab") as handle:
            handle.write(_BODY[4:])
        return len(_BODY) - 4

    path = ensure_asset(tmp_path, _ASSET, acknowledged=True, fetch=fetch)
    assert path.read_bytes() == _BODY


def test_a_bad_checksum_is_deleted(tmp_path: Path) -> None:
    def fetch(dest: Path, _offset: int) -> int:
        dest.write_bytes(b"nope")
        return 4

    with pytest.raises(AppError) as excinfo:
        ensure_asset(tmp_path, _ASSET, acknowledged=True, fetch=fetch)
    assert excinfo.value.code is ErrorCode.TTS_MODEL_MISSING
    assert excinfo.value.detail["reason"] == "checksum_mismatch"
    assert list(tmp_path.rglob("*")) == [tmp_path / "omnivoice"]
