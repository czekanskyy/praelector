# SPDX-License-Identifier: Apache-2.0
"""TTS worker process dispatcher and backend coordinator."""

from __future__ import annotations

import time

from praelector_tts.backends.base import BaseBackend
from praelector_tts.backends.fake import FakeBackend
from praelector_tts.protocol import (
    ProbeResponse,
    SynthesizeRequest,
    SynthesizeResponse,
    WorkerResponse,
)


class TtsWorker:
    """Worker handling synthesis requests from engine over JSONL."""

    def __init__(self) -> None:
        self.backends: dict[str, BaseBackend] = {
            "fake": FakeBackend(),
        }

    def register_backend(self, backend: BaseBackend) -> None:
        self.backends[backend.backend_id] = backend

    def handle_request(self, raw_request: dict[str, object]) -> WorkerResponse:
        req_id = str(raw_request.get("id", ""))
        action = str(raw_request.get("action", ""))

        if action == "probe":
            return ProbeResponse(
                id=req_id,
                ok=True,
                backends=list(self.backends.keys()),
                cuda_available=False,
            )

        if action == "synthesize":
            try:
                req = SynthesizeRequest.model_validate(raw_request)
                backend = self.backends.get(req.backend_id)
                if not backend:
                    return SynthesizeResponse(
                        id=req.id,
                        ok=False,
                        error=f"Backend '{req.backend_id}' not found in worker",
                    )

                start_wall = time.perf_counter()
                duration_s, sample_rate = backend.synthesize(
                    text=req.text,
                    output_path=req.output_path,
                    reference_audio_path=req.reference_audio_path,
                    params=req.params,
                )
                wall_s = time.perf_counter() - start_wall

                return SynthesizeResponse(
                    id=req.id,
                    ok=True,
                    duration_s=round(duration_s, 3),
                    wall_s=round(wall_s, 3),
                    sample_rate=sample_rate,
                )
            except Exception as e:  # noqa: BLE001
                return SynthesizeResponse(
                    id=req_id,
                    ok=False,
                    error=f"Synthesis failed: {e}",
                )

        if action == "shutdown":
            return WorkerResponse(id=req_id, ok=True)

        return WorkerResponse(id=req_id, ok=False, error=f"Unknown action: {action}")
