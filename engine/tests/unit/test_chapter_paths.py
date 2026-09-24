# SPDX-License-Identifier: Apache-2.0
"""Retained chapter files keep the book number."""

from __future__ import annotations

from pathlib import Path

import pytest

from praelector.mux.paths import retained_chapter_wav


def test_chapter_eight_is_named_008(tmp_path: Path) -> None:
    path = retained_chapter_wav(tmp_path / "chapters", 8)
    assert path == tmp_path / "chapters" / "008.wav"


def test_a_negative_chapter_number_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        retained_chapter_wav(tmp_path, -1)
