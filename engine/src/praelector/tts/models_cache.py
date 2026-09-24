# SPDX-License-Identifier: Apache-2.0
"""Shared model cache (TTS-02, NF-03).

A fetcher is injected, so a test never contacts Hugging Face. The file is
written beside the target as ``.partial``, hashed, and renamed only when
the sha256 matches. A license that has not been acknowledged refuses
before any byte is fetched.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from praelector.errors import AppError, ErrorCode

#: ``fetch(dest, offset)`` appends bytes starting at ``offset`` and returns
#: the number of new bytes it wrote.
Fetcher = Callable[[Path, int], int]


@dataclass(frozen=True, slots=True)
class ModelAsset:
    """One file in the shared cache. ``sha256`` is hex."""

    name: str
    sha256: str
    size_bytes: int
    relative_path: str


def ensure_asset(
    cache_dir: Path,
    asset: ModelAsset,
    *,
    acknowledged: bool,
    fetch: Fetcher,
) -> Path:
    """Return the cached file. Download only when it is missing or short."""
    if not acknowledged:
        raise AppError(
            ErrorCode.TTS_LICENSE_NOT_ACKNOWLEDGED,
            detail={"asset": asset.name},
            message="the model license has not been acknowledged",
        )
    target = cache_dir / asset.relative_path
    if target.is_file() and _sha256(target) == asset.sha256:
        return target
    partial = target.with_name(target.name + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    offset = partial.stat().st_size if partial.is_file() else 0
    fetch(partial, offset)
    digest = _sha256(partial)
    if digest != asset.sha256:
        partial.unlink(missing_ok=True)
        raise AppError(
            ErrorCode.TTS_MODEL_MISSING,
            detail={"asset": asset.name, "reason": "checksum_mismatch", "sha256": digest},
            message="the downloaded model did not match its checksum",
        )
    partial.replace(target)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
