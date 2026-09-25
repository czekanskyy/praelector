# SPDX-License-Identifier: Apache-2.0
"""The M4B invocation carries the tags file and the AAC settings."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from praelector.audio.ffmpeg import ToolResult
from praelector.mux.encode_m4b import encode_m4b
from praelector.mux.metadata import AudiobookTags, ChapterMark


class _Tool:
    def __init__(self) -> None:
        self.argv: list[Sequence[str]] = []

    def run(self, argv: Sequence[str]) -> ToolResult:
        self.argv.append(tuple(argv))
        return ToolResult(0, b"", b"")


def test_encode_writes_metadata_and_asks_for_aac(tmp_path: Path) -> None:
    tool = _Tool()
    encode_m4b(
        tool=tool,
        ffmpeg=tmp_path / "ffmpeg",
        work_dir=tmp_path / "mux",
        concat_text="file '008.wav'\n",
        tags=AudiobookTags(
            title="Tytul",
            authors=("Anna",),
            narrator="Lektor",
            album="Tytul",
            date="2026",
        ),
        chapters=[ChapterMark("Osmy", 0, 1000)],
        output=tmp_path / "book.m4b",
    )

    meta = (tmp_path / "mux" / "ffmetadata.txt").read_text(encoding="utf-8")
    assert meta.startswith(";FFMETADATA1\n")
    assert "composer=Lektor\n" in meta
    assert tool.argv[0][0] == "ffmpeg"
    assert "aac" in tool.argv[0]
    assert tool.argv[0][-1].endswith("book.m4b")
