# SPDX-License-Identifier: Apache-2.0
"""Worker spawn, handshake, and kill. The child is a JSONL script, not a model."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from praelector.errors import AppError, ErrorCode
from praelector.tts.worker_client import WorkerClient

_SCRIPT = Path(__file__).resolve().parents[1] / "fake_tts_worker.py"


def test_ready_handshake_and_a_describe_call() -> None:
    client = WorkerClient(_argv("ok"), ready_timeout_s=2, call_timeout_s=2)
    try:
        ready = client.wait_ready()
        assert ready.event == "ready"
        assert ready.payload["device"] == "cpu"
        reply = client.call("describe")
        assert reply.ok is True
        assert reply.result["echo"] == "describe"
    finally:
        client.close()
    assert client.alive is False


def test_a_late_ready_is_killed() -> None:
    client = WorkerClient(_argv("hang-ready"), ready_timeout_s=0.2)
    with pytest.raises(AppError) as excinfo:
        client.wait_ready()
    assert excinfo.value.code is ErrorCode.TTS_WORKER_CRASHED
    assert excinfo.value.detail["reason"] == "ready_timeout"
    assert client.alive is False


def test_a_call_that_stalls_is_killed() -> None:
    client = WorkerClient(_argv("hang-call"), ready_timeout_s=2, call_timeout_s=0.2)
    client.wait_ready()
    with pytest.raises(AppError) as excinfo:
        client.call("describe")
    assert excinfo.value.detail["reason"] == "call_timeout"
    assert client.alive is False


def _argv(mode: str) -> list[str]:
    return [sys.executable, str(_SCRIPT), mode]
