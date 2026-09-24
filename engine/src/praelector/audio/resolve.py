# SPDX-License-Identifier: Apache-2.0
"""Find ffmpeg the way a release build does (PLAN.md §1.7).

Order: an explicit path, then ``PATH``, then ``<dataDir>/bin``. A miss
is ``audio.ffmpeg_missing``. ``which`` is injected, so the test does not
search the real path.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from praelector.errors import AppError, ErrorCode

Which = Callable[[str], str | None]


def resolve_tool(
    name: str,
    *,
    configured: str | None,
    bin_dir: Path,
    which: Which,
    suffix: str = "",
) -> Path:
    """Return the binary for ``ffmpeg`` or ``ffprobe``."""
    if configured:
        chosen = Path(configured)
        if chosen.is_file():
            return chosen
    found = which(name)
    if found:
        return Path(found)
    bundled = bin_dir / f"{name}{suffix}"
    if bundled.is_file():
        return bundled
    raise AppError(
        ErrorCode.AUDIO_FFMPEG_MISSING,
        detail={"tool": name, "reason": "not_found"},
    )
