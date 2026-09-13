# SPDX-License-Identifier: Apache-2.0
"""TTS worker IPC protocol models (JSONL over stdio)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkerRequest(BaseModel):
    """Base worker command."""

    id: str = Field(..., description="Unique request identifier")
    action: Literal["probe", "synthesize", "shutdown"] = Field(..., description="Worker action")


class SynthesizeRequest(WorkerRequest):
    """Synthesis request sent to TTS worker."""

    action: Literal["synthesize"] = "synthesize"
    backend_id: str = Field(..., description="Backend identifier (e.g. fake, omnivoice)")
    text: str = Field(..., description="Spoken text to synthesize")
    reference_audio_path: str | None = Field(default=None, description="Reference audio path")
    output_path: str = Field(..., description="Target WAV file path (.part)")
    params: dict[str, Any] = Field(default_factory=dict, description="Backend-specific parameters")


class WorkerResponse(BaseModel):
    """Base worker response."""

    id: str = Field(..., description="Matching request identifier")
    ok: bool = Field(..., description="Whether operation succeeded")
    error: str | None = Field(default=None, description="Error message or code if failed")


class SynthesizeResponse(WorkerResponse):
    """Synthesis completion response."""

    duration_s: float = Field(default=0.0, description="Synthesized audio duration in seconds")
    wall_s: float = Field(default=0.0, description="Wall clock synthesis time in seconds")
    sample_rate: int = Field(default=24000, description="Generated audio sample rate")
    peak_vram_mib: int | None = Field(
        default=None, description="Peak VRAM allocated during synthesis"
    )


class ProbeResponse(WorkerResponse):
    """Worker capability and backend probe response."""

    backends: list[str] = Field(default_factory=list, description="Available backend IDs")
    cuda_available: bool = False
    device_name: str | None = None
