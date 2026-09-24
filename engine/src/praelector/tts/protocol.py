# SPDX-License-Identifier: Apache-2.0
"""TTS worker wire protocol (TTS-01, D-05).

Newline-delimited JSON. This module encodes requests and parses replies.
:mod:`praelector.tts.worker_client` owns the process.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from praelector.errors import AppError, ErrorCode

WorkerOp = Literal["describe", "load", "synthesize", "probe_vram", "unload", "shutdown"]


class ReferenceAudio(BaseModel):
    model_config = ConfigDict(frozen=True)

    required: bool
    min_seconds: float
    max_seconds: float
    needs_ref_text: bool
    target_sample_rate: int


class Capabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    languages: tuple[str, ...] = Field(min_length=1)
    native_sample_rate: int = Field(gt=0)
    reference_audio: ReferenceAudio
    clone: bool = False
    voice_design: bool = False
    emotion: bool = False
    streaming: bool = False
    batching: bool = False
    deterministic_with_seed: bool = False
    watermark: bool = False
    max_input_chars: int = Field(default=400, gt=0)


class BackendDescriptor(BaseModel):
    """The ``describe`` payload. ``languages`` is the TTS-01 gate."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    capabilities: Capabilities


class WorkerRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1)
    op: WorkerOp
    body: dict[str, Any] = Field(default_factory=dict)


class WorkerSuccess(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    ok: Literal[True] = True
    result: dict[str, Any]


class WorkerFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    ok: Literal[False] = False
    code: str
    message: str
    retryable: bool


class WorkerEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: Literal["ready", "log", "progress"]
    payload: dict[str, Any]


WorkerMessage = WorkerSuccess | WorkerFailure | WorkerEvent


def encode_request(request: WorkerRequest) -> str:
    """One JSON line, as the worker reads it from stdin."""
    payload: dict[str, Any] = {"id": request.id, "op": request.op}
    payload.update(request.body)
    return json.dumps(payload, separators=(",", ":")) + "\n"


def parse_worker_line(line: str) -> WorkerMessage:
    """Parse one stdout line. A blank line or broken JSON is ``tts.internal``."""
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        raise AppError(
            ErrorCode.TTS_INTERNAL,
            detail={"reason": "malformed_line"},
            message="the worker wrote a line that is not JSON",
        ) from exc
    if not isinstance(raw, dict):
        raise AppError(
            ErrorCode.TTS_INTERNAL,
            detail={"reason": "malformed_line"},
            message="the worker wrote a JSON value that is not an object",
        )
    try:
        if "event" in raw:
            event = str(raw["event"])
            payload = {key: value for key, value in raw.items() if key != "event"}
            return WorkerEvent.model_validate({"event": event, "payload": payload})
        if raw.get("ok") is True:
            return WorkerSuccess.model_validate(raw)
        if raw.get("ok") is False:
            error = raw.get("error")
            if not isinstance(error, dict) or "code" not in error:
                raise ValueError("error object")
            return WorkerFailure(
                id=raw["id"],
                code=str(error["code"]),
                message=str(error.get("message", "")),
                retryable=bool(error.get("retryable", False)),
            )
    except (ValidationError, KeyError, TypeError) as exc:
        raise AppError(
            ErrorCode.TTS_INTERNAL,
            detail={"reason": "malformed_line"},
            message="the worker wrote a line this engine does not understand",
        ) from exc
    raise AppError(
        ErrorCode.TTS_INTERNAL,
        detail={"reason": "unknown_message"},
        message="the worker wrote a line with no event and no ok flag",
    )


def parse_descriptor(raw: dict[str, Any]) -> BackendDescriptor:
    try:
        return BackendDescriptor.model_validate(raw)
    except ValidationError as exc:
        raise AppError(
            ErrorCode.TTS_INTERNAL,
            detail={"reason": "invalid_descriptor"},
            message="the backend descriptor failed validation",
        ) from exc


def assert_language(descriptor: BackendDescriptor, language: str) -> None:
    """Refuse a job whose language the backend did not list (D-17)."""
    if language not in descriptor.capabilities.languages:
        raise AppError(
            ErrorCode.TTS_LANGUAGE_UNSUPPORTED,
            detail={"backend_id": descriptor.id, "language": language},
            message="this backend does not speak the project language",
        )
