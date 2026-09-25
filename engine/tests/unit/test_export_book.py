# SPDX-License-Identifier: Apache-2.0
"""A partial export drops an incomplete chapter and still writes the M4B."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from praelector.audio.ffmpeg import ToolResult
from praelector.jobs.chunker import PlanItem
from praelector.mux.chapters import ChapterAudio
from praelector.mux.export_book import export_book
from praelector.mux.metadata import AudiobookTags


class _Tool:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, argv: Sequence[str]) -> ToolResult:
        self.calls += 1
        return ToolResult(0, b"", b"")


def test_partial_export_omits_the_incomplete_chapter(tmp_path: Path) -> None:
    ready = PlanItem(0, "chp_1", "narrator", "a", "tts", "rk1")
    missing = PlanItem(1, "chp_2", "narrator", "b", "tts", "rk2")
    chapters = (
        ChapterAudio("chp_1", 1, "Pierwszy", (ready,)),
        ChapterAudio("chp_2", 2, "Drugi", (missing,)),
    )
    tool = _Tool()

    plan = export_book(
        chapters,
        mode="partial",
        present=lambda item: item.render_key == "rk1",
        tool=tool,
        ffmpeg=tmp_path / "ffmpeg",
        work_dir=tmp_path / "out",
        output=tmp_path / "book.m4b",
        wav_for=lambda item: tmp_path / f"{item.render_key}.wav",
        silence_wav=tmp_path / "silence.wav",
        gap_ms=0,
        tags=AudiobookTags("T", ("A",), "L", "T", "2026"),
        duration_of=lambda _path: 1.0,
    )

    assert [chapter.number for chapter in plan.included] == [1]
    assert plan.omitted[0]["number"] == 2
    assert tool.calls == 2
    report = json.loads((tmp_path / "out" / "partial_report.json").read_text(encoding="utf-8"))
    assert report["omitted"][0]["number"] == 2
    meta = (tmp_path / "out" / "ffmetadata.txt").read_text(encoding="utf-8")
    assert "END=1000\n" in meta
