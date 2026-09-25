# SPDX-License-Identifier: Apache-2.0
"""Chapter WAVs are concat copies, and the book number is kept."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from praelector.audio.ffmpeg import ToolResult
from praelector.jobs.chunker import PlanItem
from praelector.mux.chapters import ChapterAudio, MuxPlan
from praelector.mux.encode_chapters import encode_chapters


class _Tool:
    def __init__(self) -> None:
        self.argv: list[Sequence[str]] = []

    def run(self, argv: Sequence[str]) -> ToolResult:
        self.argv.append(tuple(argv))
        return ToolResult(0, b"", b"")


def test_each_included_chapter_is_one_copy(tmp_path: Path) -> None:
    speech = PlanItem(0, "chp_8", "narrator", "a", "tts", "rk")
    plan = MuxPlan(
        included=(
            ChapterAudio("chp_8", 8, "Osmy", (speech,)),
            ChapterAudio("chp_10", 10, "Dziesiaty", (speech,)),
        ),
        omitted=(),
    )
    tool = _Tool()
    wav = tmp_path / "rk.wav"

    written = encode_chapters(
        plan,
        tool=tool,
        ffmpeg=tmp_path / "ffmpeg",
        work_dir=tmp_path / "chapters",
        wav_for=lambda _item: wav,
        silence_wav=tmp_path / "silence.wav",
        gap_ms=0,
    )

    assert [path.name for path in written] == ["008.wav", "010.wav"]
    assert tool.argv[0][0] == "ffmpeg"
    assert tool.argv[0][-3:-1] == ("-c", "copy")
    listing = (tmp_path / "chapters" / "008.txt").read_text(encoding="utf-8")
    assert listing == f"file '{wav.as_posix()}'\n"
