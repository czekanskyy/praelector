# SPDX-License-Identifier: Apache-2.0
"""Wire-protocol encode and parse, with no worker process."""

from __future__ import annotations

import pytest

from praelector.errors import AppError, ErrorCode
from praelector.tts.protocol import (
    BackendDescriptor,
    WorkerEvent,
    WorkerFailure,
    WorkerRequest,
    WorkerSuccess,
    assert_language,
    encode_request,
    parse_descriptor,
    parse_worker_line,
)

_DESCRIBE = {
    "id": "omnivoice",
    "adapter_version": "1.0.0",
    "capabilities": {
        "languages": ["pl", "en"],
        "native_sample_rate": 24000,
        "reference_audio": {
            "required": True,
            "min_seconds": 3,
            "max_seconds": 20,
            "needs_ref_text": True,
            "target_sample_rate": 24000,
        },
    },
}


def test_describe_request_is_one_json_line() -> None:
    line = encode_request(WorkerRequest(id=1, op="describe"))
    assert line == '{"id":1,"op":"describe"}\n'
    loaded = encode_request(
        WorkerRequest(id=2, op="load", body={"params": {"device": "cuda:0", "precision": "fp16"}})
    )
    assert loaded.endswith("\n")
    assert '"op":"load"' in loaded


def test_ready_success_and_oom_lines_parse() -> None:
    ready = parse_worker_line(
        '{"event":"ready","pid":4242,"device":"cuda:0","torch":"2.13.0+cu130"}'
    )
    assert isinstance(ready, WorkerEvent)
    assert ready.event == "ready"
    assert ready.payload["pid"] == 4242
    success = parse_worker_line(
        '{"id":3,"ok":true,"result":{"duration_s":4.12,"sample_rate":24000}}'
    )
    assert isinstance(success, WorkerSuccess)
    assert success.result["duration_s"] == 4.12
    failure = parse_worker_line(
        '{"id":3,"ok":false,"error":{"code":"tts.oom","message":"out of memory","retryable":true}}'
    )
    assert isinstance(failure, WorkerFailure)
    assert failure.code == "tts.oom"
    assert failure.retryable is True


def test_a_broken_line_is_an_internal_error() -> None:
    with pytest.raises(AppError) as excinfo:
        parse_worker_line("not-json")
    assert excinfo.value.code is ErrorCode.TTS_INTERNAL
    assert excinfo.value.detail["reason"] == "malformed_line"


def test_descriptor_gates_polish_and_rejects_an_empty_language_list() -> None:
    descriptor = parse_descriptor(_DESCRIBE)
    assert isinstance(descriptor, BackendDescriptor)
    assert_language(descriptor, "pl")
    with pytest.raises(AppError) as excinfo:
        assert_language(descriptor, "zh")
    assert excinfo.value.code is ErrorCode.TTS_LANGUAGE_UNSUPPORTED
    broken = {**_DESCRIBE, "capabilities": {**_DESCRIBE["capabilities"], "languages": []}}
    with pytest.raises(AppError) as empty:
        parse_descriptor(broken)
    assert empty.value.detail["reason"] == "invalid_descriptor"
