# SPDX-License-Identifier: Apache-2.0
"""OmniVoice adapter (TTS-02, D-21, D-25).

The descriptor, the Polish language id and the ``ref_text`` check live here
and do not import torch. Weight download and the real ``omnivoice`` package
are not required to refuse a bad request. Inference itself stays behind a
lazy import and reports ``tts.model_missing`` until that package is present.
"""

from __future__ import annotations

import importlib
from typing import ClassVar

from praelector_tts.protocol import (
    BackendDescriptor,
    Capabilities,
    LicenseInfo,
    LoadContext,
    LoadReport,
    ModelRef,
    ReferenceAudioSpec,
    SynthesisRequest,
    SynthesisResult,
    TtsBackend,
    TtsError,
    TtsErrorCode,
    VramProfileEntry,
    VramReport,
)

#: PLAN.md §7.2 conservative default for OmniVoice fp16.
PEAK_VRAM_MIB = 3500
PRECISION = "fp16"
#: The language id OmniVoice uses for Polish.
POLISH_LANGUAGE_ID = "pl"
SAMPLE_RATE = 24000
_REPO = "k2-fsa/OmniVoice"


class OmniVoiceBackend(TtsBackend):
    id: ClassVar[str] = "omnivoice"
    adapter_version: ClassVar[str] = "1.0.0"

    def __init__(self) -> None:
        self._ctx: LoadContext | None = None

    @classmethod
    def describe(cls) -> BackendDescriptor:
        return BackendDescriptor(
            id=cls.id,
            display_name="OmniVoice",
            adapter_version=cls.adapter_version,
            model=ModelRef(repo=_REPO, params="0.6B"),
            capabilities=Capabilities(
                clone=True,
                voice_design=False,
                languages=[POLISH_LANGUAGE_ID],
                native_sample_rate=SAMPLE_RATE,
                reference_audio=ReferenceAudioSpec(
                    required=True,
                    min_seconds=3,
                    max_seconds=20,
                    needs_ref_text=True,
                    target_sample_rate=SAMPLE_RATE,
                ),
            ),
            params_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "properties": {},
            },
            vram_profile={PRECISION: VramProfileEntry(peak_mib=PEAK_VRAM_MIB, measured=False)},
            licenses=[
                LicenseInfo(
                    component="code",
                    spdx="Apache-2.0",
                    url="https://huggingface.co/k2-fsa/OmniVoice",
                    acknowledgement_required=False,
                    commercial_use=True,
                ),
                LicenseInfo(
                    component="weights",
                    spdx="Apache-2.0",
                    url="https://huggingface.co/k2-fsa/OmniVoice",
                    acknowledgement_required=False,
                    commercial_use=True,
                ),
            ],
        )

    def load(self, ctx: LoadContext) -> LoadReport:
        if ctx.precision != PRECISION:
            raise TtsError(
                TtsErrorCode.LOAD_FAILED,
                "omnivoice runs at fp16",
                detail={"reason": "precision", "precision": ctx.precision},
            )
        self._ctx = ctx
        return LoadReport(
            loaded=True,
            device=ctx.device,
            precision=ctx.precision,
            model_revision=self.adapter_version,
            vram_mib=PEAK_VRAM_MIB,
            load_ms=0,
        )

    def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        self._check(req)
        try:
            importlib.import_module("omnivoice")
        except ImportError as exc:
            raise TtsError(
                TtsErrorCode.MODEL_MISSING,
                "the omnivoice package is not installed",
                detail={"reason": "package_missing"},
            ) from exc
        raise TtsError(
            TtsErrorCode.MODEL_MISSING,
            "omnivoice weights are not loaded",
            detail={"reason": "weights_not_downloaded"},
        )

    def probe_vram(self) -> VramReport:
        device = self._ctx.device if self._ctx is not None else "cpu"
        return VramReport(device=device, peak_mib=PEAK_VRAM_MIB)

    def unload(self) -> None:
        self._ctx = None

    def _check(self, req: SynthesisRequest) -> None:
        if self._ctx is None:
            raise TtsError(TtsErrorCode.LOAD_FAILED, "backend is not loaded")
        if req.language != POLISH_LANGUAGE_ID:
            raise TtsError(
                TtsErrorCode.LANGUAGE_UNSUPPORTED,
                "omnivoice is registered for Polish",
                detail={"language": req.language, "language_id": POLISH_LANGUAGE_ID},
            )
        ref_text = req.voice.ref_text if req.voice is not None else None
        if ref_text is None or not ref_text.strip():
            raise TtsError(
                TtsErrorCode.INTERNAL,
                "omnivoice requires ref_text",
                detail={"reason": "ref_text_required"},
            )
