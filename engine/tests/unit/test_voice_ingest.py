# SPDX-License-Identifier: Apache-2.0
"""Voice ingest driven by a fake ffmpeg. No binary is spawned."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from praelector.audio.ffmpeg import SubprocessMediaTool, ToolResult
from praelector.errors import AppError, ErrorCode
from praelector.voices.ingest import ingest_sample


class FakeMedia:
    def __init__(self, duration: str = "8.0") -> None:
        self.calls: list[list[str]] = []
        self._duration = duration

    def run(self, argv: Sequence[str]) -> ToolResult:
        recorded = list(argv)
        self.calls.append(recorded)
        if argv[0] == "ffprobe":
            body = json.dumps({"format": {"duration": self._duration}}).encode()
            return ToolResult(0, body, b"")
        dest = argv[-1]
        if dest != "-":
            path = Path(dest)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"RIFF-canned")
        if "print_format=json" in " ".join(argv):
            stats = (
                '{"input_i":"-20.1","input_tp":"-1.5","input_lra":"7.0",'
                '"input_thresh":"-30.0","target_offset":"0.4"}'
            )
            return ToolResult(0, b"", stats.encode())
        return ToolResult(0, b"", b"")


def test_the_chain_order_and_the_written_profile(tmp_path: Path) -> None:
    source = tmp_path / "upload.wav"
    source.write_bytes(b"raw")
    fake = FakeMedia()
    profile = ingest_sample(
        source,
        tmp_path / "voices",
        profile_id="narrator",
        ref_text="To jest próbka.",
        tool=fake,
        sample_rate=24000,
    )
    filters = [" ".join(call) for call in fake.calls]
    assert filters[0].startswith("ffmpeg") and "-sample_fmt s16" in filters[0]
    assert "silenceremove=" in filters[1]
    assert "print_format=json" in filters[2]
    assert "measured_I=-20.1" in filters[3]
    assert "-ar 24000" in filters[4]
    assert filters[5].startswith("ffprobe")
    assert profile.processed_path == tmp_path / "voices" / "narrator.wav"
    assert profile.processed_path.read_bytes() == b"RIFF-canned"
    assert profile.peaks_path.is_file()
    assert profile.sample_rate == 24000
    assert profile.duration_s == 8.0
    assert profile.ref_text == "To jest próbka."
    assert profile.content_hash


def test_a_sample_longer_than_the_maximum_is_trimmed(tmp_path: Path) -> None:
    source = tmp_path / "upload.wav"
    source.write_bytes(b"raw")
    fake = FakeMedia(duration="30.0")
    ingest_sample(
        source,
        tmp_path / "voices",
        profile_id="narrator",
        ref_text="Długa próbka.",
        tool=fake,
        sample_rate=24000,
        max_seconds=20,
    )
    joined = [" ".join(call) for call in fake.calls]
    assert any("atrim=start=0:end=20" in line for line in joined)


def test_a_missing_ffmpeg_is_the_project_error() -> None:
    tool = SubprocessMediaTool(ffmpeg=None, ffprobe=None)
    with pytest.raises(AppError) as excinfo:
        tool.run(["ffmpeg", "-version"])
    assert excinfo.value.code is ErrorCode.AUDIO_FFMPEG_MISSING
    assert excinfo.value.detail["reason"] == "not_found"
