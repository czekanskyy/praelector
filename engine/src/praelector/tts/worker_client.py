# SPDX-License-Identifier: Apache-2.0
"""Spawn one TTS worker and talk to it (TTS-05, D-05).

The JSONL messages are :mod:`praelector.tts.protocol`. This module owns the
process: the ready handshake, one call at a time, and the kill when a
timeout expires. It does not load a model.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from contextlib import suppress
from queue import Empty, Queue
from typing import Final

from praelector.errors import AppError, ErrorCode
from praelector.tts.protocol import (
    WorkerEvent,
    WorkerFailure,
    WorkerOp,
    WorkerRequest,
    WorkerSuccess,
    encode_request,
    parse_worker_line,
)

_KILL_GRACE_S: Final = 2.0
_CREATE_NO_WINDOW: Final = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


class WorkerClient:
    """One worker process. ``close`` always leaves it dead."""

    def __init__(
        self,
        argv: Sequence[str],
        *,
        ready_timeout_s: float = 5.0,
        call_timeout_s: float = 30.0,
    ) -> None:
        self._ready_timeout_s = ready_timeout_s
        self._call_timeout_s = call_timeout_s
        self._queue: Queue[str | None] = Queue()
        self._proc = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=_CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self._reader = threading.Thread(
            target=self._read_stdout, name="tts-worker-stdout", daemon=True
        )
        self._reader.start()
        self._next_id = 1

    @property
    def pid(self) -> int | None:
        return self._proc.pid

    @property
    def alive(self) -> bool:
        return self._proc.poll() is None

    def wait_ready(self) -> WorkerEvent:
        """Block until ``{"event":"ready"}``. Kill the child if it does not arrive."""
        message = self._read_until(self._ready_timeout_s, reason="ready_timeout")
        if not isinstance(message, WorkerEvent) or message.event != "ready":
            self.kill()
            raise AppError(
                ErrorCode.TTS_WORKER_CRASHED,
                detail={"reason": "ready_missing"},
                message="the worker spoke before it was ready",
            )
        return message

    def call(self, op: WorkerOp, **body: object) -> WorkerSuccess | WorkerFailure:
        """Send one request and return the matching reply. A timeout kills the child."""
        request = WorkerRequest(id=self._next_id, op=op, body=dict(body))
        self._next_id += 1
        self._write(encode_request(request))
        deadline = time.monotonic() + self._call_timeout_s
        while True:
            remaining = deadline - time.monotonic()
            message = self._read_until(remaining, reason="call_timeout")
            if isinstance(message, WorkerEvent):
                continue
            if message.id == request.id:
                return message

    def close(self) -> None:
        """Ask the worker to shut down, then kill it if it is still running."""
        if self.alive and self._proc.stdin is not None:
            request = WorkerRequest(id=self._next_id, op="shutdown")
            with suppress(OSError):
                self._write(encode_request(request))
        self.kill()

    def kill(self) -> None:
        """Terminate the child and wait until it is gone."""
        if self._proc.poll() is None:
            self._proc.kill()
        try:
            self._proc.wait(timeout=_KILL_GRACE_S)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=_KILL_GRACE_S)
        if self._proc.stdin is not None:
            self._proc.stdin.close()
        self._reader.join(timeout=_KILL_GRACE_S)

    def _write(self, line: str) -> None:
        stdin = self._proc.stdin
        if stdin is None:
            raise AppError(
                ErrorCode.TTS_WORKER_CRASHED,
                detail={"reason": "stdin_closed"},
                message="the worker stdin is already closed",
            )
        stdin.write(line)
        stdin.flush()

    def _read_until(
        self, timeout_s: float, *, reason: str
    ) -> WorkerSuccess | WorkerFailure | WorkerEvent:
        if timeout_s <= 0:
            self.kill()
            raise AppError(
                ErrorCode.TTS_WORKER_CRASHED,
                detail={"reason": reason},
                message="the worker did not answer in time",
            )
        try:
            line = self._queue.get(timeout=timeout_s)
        except Empty:
            self.kill()
            raise AppError(
                ErrorCode.TTS_WORKER_CRASHED,
                detail={"reason": reason},
                message="the worker did not answer in time",
            ) from None
        if line is None:
            self.kill()
            raise AppError(
                ErrorCode.TTS_WORKER_CRASHED,
                detail={"reason": "worker_exited"},
                message="the worker exited before it answered",
            )
        return parse_worker_line(line)

    def _read_stdout(self) -> None:
        stdout = self._proc.stdout
        if stdout is None:
            self._queue.put(None)
            return
        try:
            for line in stdout:
                self._queue.put(line)
        finally:
            self._queue.put(None)
