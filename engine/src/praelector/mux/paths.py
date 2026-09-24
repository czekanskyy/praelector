# SPDX-License-Identifier: Apache-2.0
"""Where a retained chapter WAV is stored (MX-05).

The file name is the original chapter number, so a partial mux that
skips chapter 2 still writes chapter 8 as ``008.wav``.
"""

from __future__ import annotations

from pathlib import Path


def retained_chapter_wav(chapters_dir: Path, number: int) -> Path:
    """``chapters/008.wav`` for chapter 8."""
    if number < 0:
        raise ValueError("chapter number must be non-negative")
    return chapters_dir / f"{number:03d}.wav"
