# SPDX-License-Identifier: Apache-2.0
"""Voice-sample ingest (TTS-04, PLAN.md §6.4).

Decode, trim, two-pass loudnorm, resample, then clamp. Each step is one
call on the injected media tool. The profile points at ``voices/<id>.wav``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from praelector.audio.ffmpeg import MediaTool, ToolResult
from praelector.errors import AppError, ErrorCode
from praelector.voices.waveform import write_peaks

CHAIN_VERSION = "1"
_DEFAULT_TARGET_LUFS = -23.0


@dataclass(frozen=True, slots=True)
class IngestedVoice:
    """The row a store would persist. ``processed_path`` is the sample on disk."""

    profile_id: str
    processed_path: Path
    peaks_path: Path
    sample_rate: int
    duration_s: float
    target_lufs: float
    content_hash: str
    ref_text: str
    chain_version: str = CHAIN_VERSION


def ingest_sample(
    source: Path,
    voices_dir: Path,
    *,
    profile_id: str,
    ref_text: str,
    tool: MediaTool,
    sample_rate: int,
    target_lufs: float = _DEFAULT_TARGET_LUFS,
    min_seconds: float = 3.0,
    max_seconds: float = 20.0,
) -> IngestedVoice:
    """Run the chain and write the processed sample next to its peaks."""
    voices_dir.mkdir(parents=True, exist_ok=True)
    work = voices_dir / f".{profile_id}.work"
    work.mkdir(parents=True, exist_ok=True)
    decoded = work / "decoded.wav"
    trimmed = work / "trimmed.wav"
    normalised = work / "normalised.wav"
    _ffmpeg(
        tool,
        ["-i", str(source), "-ac", "1", "-sample_fmt", "s16", "-y", str(decoded)],
    )
    _ffmpeg(
        tool,
        [
            "-i",
            str(decoded),
            "-af",
            "silenceremove=start_periods=1:start_silence=0.1:stop_periods=1",
            "-y",
            str(trimmed),
        ],
    )
    measured = _ffmpeg(
        tool,
        [
            "-i",
            str(trimmed),
            "-af",
            f"loudnorm=I={target_lufs}:print_format=json",
            "-f",
            "null",
            "-",
        ],
    )
    stats = _loudnorm_stats(measured.stderr)
    applied = (
        f"loudnorm=I={target_lufs}:measured_I={stats['input_i']}:"
        f"measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}:"
        f"measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}"
    )
    _ffmpeg(tool, ["-i", str(trimmed), "-af", applied, "-y", str(normalised)])
    processed = voices_dir / f"{profile_id}.wav"
    _ffmpeg(
        tool, ["-i", str(normalised), "-ar", str(sample_rate), "-ac", "1", "-y", str(processed)]
    )
    duration = _duration(tool, processed)
    if duration > max_seconds:
        clamped = work / "clamped.wav"
        _ffmpeg(
            tool,
            ["-i", str(processed), "-af", f"atrim=start=0:end={max_seconds}", "-y", str(clamped)],
        )
        clamped.replace(processed)
        duration = _duration(tool, processed)
    peaks = voices_dir / f"{profile_id}.peaks.json"
    write_peaks(processed, peaks)
    digest = hashlib.blake2s(
        processed.read_bytes() + f"{target_lufs}|{sample_rate}|{CHAIN_VERSION}".encode(),
        digest_size=16,
    ).hexdigest()
    return IngestedVoice(
        profile_id=profile_id,
        processed_path=processed,
        peaks_path=peaks,
        sample_rate=sample_rate,
        duration_s=duration,
        target_lufs=target_lufs,
        content_hash=digest,
        ref_text=ref_text,
    )


def _ffmpeg(tool: MediaTool, args: Sequence[str]) -> ToolResult:
    result = tool.run(["ffmpeg", *args])
    if result.returncode != 0:
        raise AppError(
            ErrorCode.AUDIO_FFMPEG_MISSING,
            detail={"tool": "ffmpeg", "reason": "exit", "returncode": result.returncode},
            message="ffmpeg failed",
        )
    return result


def _duration(tool: MediaTool, path: Path) -> float:
    result = tool.run(["ffprobe", "-print_format", "json", "-show_format", str(path)])
    if result.returncode != 0:
        raise AppError(
            ErrorCode.AUDIO_FFMPEG_MISSING,
            detail={"tool": "ffprobe", "reason": "exit", "returncode": result.returncode},
            message="ffprobe failed",
        )
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def _loudnorm_stats(stderr: bytes) -> dict[str, str]:
    text = stderr.decode("utf-8", errors="replace")
    start = text.rfind("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise AppError(
            ErrorCode.AUDIO_FFMPEG_MISSING,
            detail={"tool": "ffmpeg", "reason": "loudnorm"},
            message="loudnorm did not report a measurement",
        )
    raw = json.loads(text[start : end + 1])
    return {
        key: str(raw[key])
        for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    }
