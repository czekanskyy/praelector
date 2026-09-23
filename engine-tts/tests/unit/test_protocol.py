# SPDX-License-Identifier: Apache-2.0
"""Tests for the wire protocol models (PLAN.md §6.2)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from praelector_tts.protocol import (
    PART_SUFFIX,
    PROTOCOL_VERSION,
    TtsError,
    TtsErrorCode,
    WorkerOp,
    WorkerRequest,
    WorkerResponse,
)


def test_describe_request() -> None:
    request = WorkerRequest.model_validate_json('{"id":1,"op":"describe"}')
    assert request.id == 1
    assert request.op is WorkerOp.DESCRIBE


def test_load_request_carries_the_load_context() -> None:
    line = json.dumps(
        {
            "id": 2,
            "op": "load",
            "params": {
                "device": "cuda:0",
                "precision": "fp16",
                "models_dir": "C:/data/models",
                "backend_params": {"speed": 1.0},
            },
        }
    )
    ctx = WorkerRequest.model_validate_json(line).load_context()
    assert ctx.device == "cuda:0"
    assert ctx.precision == "fp16"
    assert ctx.models_dir == "C:/data/models"
    assert ctx.backend_params == {"speed": 1.0}


def test_synthesize_request_is_flat() -> None:
    line = json.dumps(
        {
            "id": 3,
            "op": "synthesize",
            "text": "Nie zdążymy.",
            "language": "pl",
            "voice": {
                "profile_id": "vpr_a",
                "ref_audio": "C:/proj/voices/vpr_a.wav",
                "ref_text": "Witam.",
            },
            "params": {"speed": 1.1},
            "seed": 1234,
            "out_path": "C:/proj/audio/chunks/ab/abcd.wav",
        }
    )
    req = WorkerRequest.model_validate_json(line).synthesis()
    assert req.text == "Nie zdążymy."
    assert req.language == "pl"
    assert req.voice is not None and req.voice.profile_id == "vpr_a"
    assert req.seed == 1234
    assert req.params == {"speed": 1.1}


def test_language_defaults_to_polish() -> None:
    request = WorkerRequest.model_validate(
        {"id": 1, "op": "synthesize", "text": "Ala ma kota.", "out_path": "/tmp/a.wav"}
    )
    assert request.synthesis().language == "pl"


@pytest.mark.parametrize("op", ["probe_vram", "unload", "shutdown"])
def test_control_ops(op: str) -> None:
    assert WorkerRequest.model_validate_json(f'{{"op":"{op}"}}').op == op


def test_unknown_fields_are_ignored_so_the_protocol_can_grow() -> None:
    request = WorkerRequest.model_validate_json('{"id":9,"op":"describe","future_field":{"x":1}}')
    assert request.op is WorkerOp.DESCRIBE


def test_a_synthesize_without_text_is_an_internal_error() -> None:
    request = WorkerRequest.model_validate({"id": 1, "op": "synthesize", "out_path": "/tmp/a.wav"})
    with pytest.raises(TtsError) as excinfo:
        request.synthesis()
    assert excinfo.value.code is TtsErrorCode.INTERNAL


def test_a_synthesize_without_out_path_is_an_internal_error() -> None:
    request = WorkerRequest.model_validate({"id": 1, "op": "synthesize", "text": "Ala."})
    with pytest.raises(TtsError, match="out_path"):
        request.synthesis()


def test_bad_load_params_are_reported_not_raised_as_validation_errors() -> None:
    request = WorkerRequest.model_validate({"id": 1, "op": "load", "params": {"device": 42}})
    with pytest.raises(TtsError) as excinfo:
        request.load_context()
    assert excinfo.value.code is TtsErrorCode.INTERNAL


def test_an_unknown_op_is_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        WorkerRequest.model_validate_json('{"id":1,"op":"teleport"}')


def test_success_response_shape() -> None:
    body = WorkerResponse.success(3, {"duration_s": 4.12, "sample_rate": 24000})
    assert json.loads(body.model_dump_json(exclude_none=True)) == {
        "id": 3,
        "ok": True,
        "result": {"duration_s": 4.12, "sample_rate": 24000},
    }


def test_failure_response_shape() -> None:
    body = WorkerResponse.from_exception(3, TtsError(TtsErrorCode.OOM, "cuda out of memory"))
    dumped = json.loads(body.model_dump_json(exclude_none=True))
    assert dumped["id"] == 3
    assert dumped["ok"] is False
    assert dumped["error"] == {
        "code": "tts.oom",
        "message": "cuda out of memory",
        "retryable": True,
        "detail": {},
    }


def test_an_unexpected_exception_becomes_an_internal_error() -> None:
    body = WorkerResponse.from_exception(7, RuntimeError("model exploded"))
    assert body.error is not None
    assert body.error.code is TtsErrorCode.INTERNAL
    assert body.error.retryable is False
    assert "RuntimeError" in body.error.message


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        (TtsErrorCode.OOM, True),
        (TtsErrorCode.INTERNAL, True),
        (TtsErrorCode.MODEL_MISSING, False),
        (TtsErrorCode.LOAD_FAILED, False),
        (TtsErrorCode.INPUT_TOO_LONG, False),
        (TtsErrorCode.LANGUAGE_UNSUPPORTED, False),
    ],
)
def test_retryable_defaults(code: TtsErrorCode, retryable: bool) -> None:
    assert TtsError(code, "x").retryable is retryable


def test_ready_event_carries_the_documented_fields() -> None:
    body = WorkerResponse.ready(pid=4242, device="cuda:0", torch="2.13.0+cu130")
    dumped = json.loads(body.model_dump_json(exclude_none=True))
    assert dumped["event"] == "ready"
    assert dumped["pid"] == 4242
    assert dumped["device"] == "cuda:0"


def test_protocol_constants() -> None:
    assert PART_SUFFIX == ".part"
    assert PROTOCOL_VERSION == 1
