# SPDX-License-Identifier: Apache-2.0
"""Guided fetch of an LGPL ffmpeg into the data directory (MX-04, D-06).

The installer is not allowed to ship the binary. A fetcher is injected,
so a test never downloads anything. Nothing is fetched until the LGPL
build has been acknowledged, and a bad sha256 never replaces the target.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from praelector.errors import AppError, ErrorCode
from praelector.store.atomic import write_json_atomic

#: The build the UI asks the user to accept before the fetch.
FFMPEG_SPDX = "LGPL-2.1-or-later"

Fetcher = Callable[[Path], None]


def install_ffmpeg(
    bin_dir: Path,
    *,
    acknowledged: bool,
    ffmpeg_sha256: str,
    ffprobe_sha256: str,
    fetch_ffmpeg: Fetcher,
    fetch_ffprobe: Fetcher,
    suffix: str = "",
) -> tuple[Path, Path]:
    """Place ``ffmpeg`` and ``ffprobe`` under ``bin_dir``. ``suffix`` is ``.exe`` on Windows."""
    if not acknowledged:
        raise AppError(
            ErrorCode.AUDIO_FFMPEG_MISSING,
            detail={"reason": "license_not_acknowledged", "spdx": FFMPEG_SPDX},
        )
    ffmpeg = _place(bin_dir / f"ffmpeg{suffix}", ffmpeg_sha256, fetch_ffmpeg)
    ffprobe = _place(bin_dir / f"ffprobe{suffix}", ffprobe_sha256, fetch_ffprobe)
    write_json_atomic(
        bin_dir / "ffmpeg.json",
        {
            "spdx": FFMPEG_SPDX,
            "ffmpeg_sha256": ffmpeg_sha256,
            "ffprobe_sha256": ffprobe_sha256,
        },
    )
    return ffmpeg, ffprobe


def _place(target: Path, expected: str, fetch: Fetcher) -> Path:
    if target.is_file() and _sha256(target) == expected:
        return target
    partial = target.with_name(target.name + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.unlink(missing_ok=True)
    fetch(partial)
    digest = _sha256(partial)
    if digest != expected:
        partial.unlink(missing_ok=True)
        raise AppError(
            ErrorCode.AUDIO_FFMPEG_MISSING,
            detail={"reason": "checksum_mismatch", "tool": target.name, "sha256": digest},
        )
    partial.replace(target)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read())
    return digest.hexdigest()
