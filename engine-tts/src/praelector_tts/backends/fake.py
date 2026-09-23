# SPDX-License-Identifier: Apache-2.0
"""The deterministic stand-in backend.

No torch, no model, no network: a sine tone whose duration is ``chars / 14`` and
whose frequency is derived from a hash of the text, so the same input always
produces byte-identical audio. That is what makes the job engine's reuse,
pause/resume and mux paths testable in CI and on a laptop with no GPU
(PLAN.md §10.3).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from praelector_tts import audio, vram
from praelector_tts.protocol import (
    BackendDescriptor,
    Capabilities,
    LicenseInfo,
    LoadContext,
    LoadReport,
    ModelRef,
    SynthesisRequest,
    SynthesisResult,
    TtsBackend,
    TtsError,
    TtsErrorCode,
    VramProfileEntry,
    VramReport,
)

#: Polish narration averages about 14 characters per second of speech.
CHARS_PER_AUDIO_SECOND = 14.0
SAMPLE_RATE = 24000
PEAK_VRAM_MIB = 64


class FakeBackend(TtsBackend):
    id = "fake"
    adapter_version = "1.0.0"

    def __init__(self) -> None:
        self._loaded = False
        self._ctx: LoadContext | None = None

    @classmethod
    def describe(cls) -> BackendDescriptor:
        return BackendDescriptor(
            id=cls.id,
            display_name="Fake (deterministic sine)",
            adapter_version=cls.adapter_version,
            model=ModelRef(repo="local/fake", revision=cls.adapter_version, params="0B"),
            capabilities=Capabilities(
                clone=False,
                voice_design=False,
                emotion=False,
                languages=["pl", "en"],
                streaming=False,
                batching=False,
                deterministic_with_seed=True,
                watermark=False,
                native_sample_rate=SAMPLE_RATE,
                max_input_chars=400,
                reference_audio=None,
            ),
            params_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "speed": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 2.0,
                        "default": 1.0,
                        "title": "Speed",
                        "x-prl-ui": {
                            "widget": "slider",
                            "group": "output",
                            "order": 1,
                            "step": 0.05,
                        },
                    },
                    "amplitude": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.2,
                        "title": "Amplitude",
                        "x-prl-ui": {
                            "widget": "slider",
                            "group": "output",
                            "order": 2,
                            "step": 0.05,
                            "advanced": True,
                        },
                    },
                },
            },
            vram_profile={
                "fp16": VramProfileEntry(peak_mib=PEAK_VRAM_MIB, measured=True),
                "fp32": VramProfileEntry(peak_mib=PEAK_VRAM_MIB, measured=True),
            },
            # Even a fake backend carries complete license data: the descriptor
            # test asserts every backend does, so the gate cannot be forgotten
            # when a real one is added (NF-03).
            licenses=[
                LicenseInfo(
                    component="code",
                    spdx="Apache-2.0",
                    acknowledgement_required=False,
                    commercial_use=True,
                ),
            ],
            assets=[],
        )

    def load(self, ctx: LoadContext) -> LoadReport:
        started = time.perf_counter()
        self._ctx = ctx
        self._loaded = True
        return LoadReport(
            loaded=True,
            device=ctx.device,
            precision=ctx.precision,
            model_revision=self.adapter_version,
            vram_mib=PEAK_VRAM_MIB,
            load_ms=int((time.perf_counter() - started) * 1000),
        )

    def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        if not self._loaded:
            raise TtsError(TtsErrorCode.LOAD_FAILED, "backend is not loaded")

        descriptor = self.describe()
        if req.language not in descriptor.capabilities.languages:
            raise TtsError(
                TtsErrorCode.LANGUAGE_UNSUPPORTED,
                f"{self.id} cannot narrate {req.language!r}",
                retryable=False,
                detail={"language": req.language, "supported": descriptor.capabilities.languages},
            )
        limit = descriptor.capabilities.max_input_chars
        if len(req.text) > limit:
            raise TtsError(
                TtsErrorCode.INPUT_TOO_LONG,
                f"{len(req.text)} chars exceeds the {limit} char limit",
                detail={"chars": len(req.text), "limit": limit},
            )

        speed = _bounded(req.params.get("speed", 1.0), 0.5, 2.0, 1.0)
        amplitude = _bounded(req.params.get("amplitude", 0.2), 0.0, 1.0, 0.2)
        duration_s = len(req.text) / CHARS_PER_AUDIO_SECOND / speed

        started = time.perf_counter()
        samples = audio.sine(duration_s, SAMPLE_RATE, _frequency_for(req.text), amplitude)
        written = audio.write_wav_part(req.out_path, samples, SAMPLE_RATE)
        infer_ms = max(1, int((time.perf_counter() - started) * 1000))

        return SynthesisResult(
            duration_s=round(duration_s, 4),
            sample_rate=SAMPLE_RATE,
            peak_vram_mib=PEAK_VRAM_MIB,
            infer_ms=infer_ms,
            rtf=round((infer_ms / 1000) / duration_s, 4) if duration_s > 0 else 0.0,
            model_revision=self.adapter_version,
            watermarked=False,
            out_path=str(written),
        )

    def probe_vram(self) -> VramReport:
        report = vram.probe(self._ctx.device if self._ctx else None)
        if report.peak_mib is None:
            # No torch: report the table value so the engine still has a number.
            return VramReport(
                device=self._ctx.device if self._ctx else "cpu", peak_mib=PEAK_VRAM_MIB
            )
        return report

    def unload(self) -> None:
        self._loaded = False
        self._ctx = None


def _bounded(value: Any, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _frequency_for(text: str) -> float:
    """Stable per-text pitch in a musical range, so chunks sound different."""
    digest = hashlib.blake2s(text.encode("utf-8"), digest_size=8).digest()
    return 110.0 + (int.from_bytes(digest, "big") % 700)
