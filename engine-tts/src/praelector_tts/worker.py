# SPDX-License-Identifier: Apache-2.0
"""The JSONL stdio loop: one request in flight, audio on disk (PLAN.md §6.2).

stdout carries protocol lines only. Everything else — logs, tracebacks, warnings
from a backend's own library — goes to stderr, because a stray line on stdout
would be parsed as a response and desynchronise the engine.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TextIO

from pydantic import ValidationError

from praelector_tts import device as device_mod
from praelector_tts.protocol import (
    PROTOCOL_VERSION,
    TtsBackend,
    TtsError,
    TtsErrorCode,
    WorkerErrorBody,
    WorkerOp,
    WorkerRequest,
    WorkerResponse,
)

logger = logging.getLogger(__name__)


def torch_version() -> str | None:
    """The installed torch version, or None when no extra is present."""
    if not device_mod.torch_available():
        return None
    import torch

    return str(torch.__version__)


class Worker:
    """Serves one backend over stdin/stdout until ``shutdown`` or EOF."""

    def __init__(self, backend: TtsBackend, *, stdin: TextIO, stdout: TextIO) -> None:
        self.backend = backend
        self._stdin = stdin
        self._stdout = stdout
        self._loaded = False
        self._shutdown = False

    def serve(self) -> int:
        self._emit(
            WorkerResponse.ready(
                pid=os.getpid(),
                backend=self.backend.id,
                protocol=PROTOCOL_VERSION,
                device=device_mod.select_device(),
                torch=torch_version(),
            )
        )
        for line in self._stdin:
            stripped = line.strip()
            if not stripped:
                continue
            response = self.handle_line(stripped)
            if response is not None:
                self._emit(response)
            if self._shutdown:
                break
        # EOF means the engine died; exit rather than linger as an orphan.
        self._safe_unload()
        return 0

    def handle_line(self, line: str) -> WorkerResponse | None:
        try:
            request = WorkerRequest.model_validate_json(line)
        except ValidationError as exc:
            logger.warning("malformed request", extra={"errors": exc.error_count()})
            return WorkerResponse.failure(
                None,
                WorkerErrorBody(
                    code=TtsErrorCode.INTERNAL,
                    message=f"malformed request: {exc.error_count()} field errors",
                ),
            )
        try:
            return self.dispatch(request)
        except TtsError as exc:
            # Not `extra={"message": …}`: `message` is reserved on LogRecord and
            # logging raises KeyError rather than emitting the line.
            logger.warning(
                "backend error", extra={"error_code": str(exc.code), "error_message": exc.message}
            )
            return WorkerResponse.from_exception(request.id, exc)
        except Exception as exc:
            # A backend fault kills one chunk, not the worker (PLAN.md §1.2).
            logger.exception("unhandled backend error")
            return WorkerResponse.from_exception(request.id, exc)

    def dispatch(self, request: WorkerRequest) -> WorkerResponse:
        match request.op:
            case WorkerOp.DESCRIBE:
                return WorkerResponse.success(request.id, self.backend.describe())
            case WorkerOp.LOAD:
                report = self.backend.load(request.load_context())
                self._loaded = report.loaded
                return WorkerResponse.success(request.id, report)
            case WorkerOp.SYNTHESIZE:
                return WorkerResponse.success(
                    request.id, self.backend.synthesize(request.synthesis())
                )
            case WorkerOp.PROBE_VRAM:
                return WorkerResponse.success(request.id, self.backend.probe_vram())
            case WorkerOp.UNLOAD:
                self._safe_unload()
                return WorkerResponse.success(request.id, {"unloaded": True})
            case WorkerOp.SHUTDOWN:
                self._safe_unload()
                self._shutdown = True
                return WorkerResponse.success(request.id, {"shutdown": True})

    def _safe_unload(self) -> None:
        if not self._loaded:
            return
        self._loaded = False
        try:
            self.backend.unload()
        except Exception:
            # Unloading is best effort; raising here would mask the real error.
            logger.exception("unload failed")

    def _emit(self, response: WorkerResponse) -> None:
        payload = response.model_dump(mode="json", exclude_none=True)
        self._stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        # Without a flush the engine blocks waiting for a buffered line.
        self._stdout.flush()
