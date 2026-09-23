# SPDX-License-Identifier: Apache-2.0
"""TTS worker protocol: the wire format and the backend contract.

Wire format is newline-delimited JSON on stdin/stdout with one request in flight
per worker (PLAN.md §6.2). Audio never crosses the pipe: the worker writes
``<out_path>.part`` and the engine validates it, performs the atomic rename and
writes the sidecar (JB-02).

``BackendDescriptor`` is exported to the UI verbatim, which is what lets the
Voices screen render a per-backend parameter panel with no backend-specific code
(TTS-05). The protocol is frozen at the end of M3.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

#: Suffix the worker writes to; the engine renames it into place.
PART_SUFFIX = ".part"

PROTOCOL_VERSION = 1


class WorkerOp(StrEnum):
    DESCRIBE = "describe"
    LOAD = "load"
    SYNTHESIZE = "synthesize"
    PROBE_VRAM = "probe_vram"
    UNLOAD = "unload"
    SHUTDOWN = "shutdown"


class TtsErrorCode(StrEnum):
    OOM = "tts.oom"
    MODEL_MISSING = "tts.model_missing"
    LOAD_FAILED = "tts.load_failed"
    INPUT_TOO_LONG = "tts.input_too_long"
    LANGUAGE_UNSUPPORTED = "tts.language_unsupported"
    INTERNAL = "tts.internal"


_RETRYABLE: frozenset[TtsErrorCode] = frozenset({TtsErrorCode.OOM, TtsErrorCode.INTERNAL})


class WorkerEvent(StrEnum):
    READY = "ready"
    LOG = "log"
    PROGRESS = "progress"


class TtsError(Exception):
    """A failure the engine can act on. Carries a stable code, never prose."""

    def __init__(
        self,
        code: TtsErrorCode,
        message: str,
        *,
        retryable: bool | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.retryable = code in _RETRYABLE if retryable is None else retryable


class ReferenceAudioSpec(BaseModel):
    """What a backend needs from a voice sample (TTS-04)."""

    required: bool = False
    min_seconds: float = 3.0
    max_seconds: float = 20.0
    #: True when the backend cannot transcribe the clip itself. OmniVoice would
    #: otherwise silently pull in Whisper, so ``ref_text`` is mandatory (D-21).
    needs_ref_text: bool = False
    target_sample_rate: int = 24000


class Capabilities(BaseModel):
    """Feature flags the scheduler and the UI gate on (TTS-01)."""

    clone: bool = False
    voice_design: bool = False
    emotion: bool = False
    #: The language gate. A backend that cannot narrate Polish is still shipped
    #: but refuses the job with ``tts.language_unsupported`` (D-17).
    languages: list[str] = Field(default_factory=list)
    streaming: bool = False
    batching: bool = False
    deterministic_with_seed: bool = False
    #: True for Chatterbox, which embeds a PerTh watermark in every clip (D-22).
    watermark: bool = False
    native_sample_rate: int = 24000
    max_input_chars: int = 400
    reference_audio: ReferenceAudioSpec | None = None


class ModelRef(BaseModel):
    repo: str
    revision: str | None = None
    params: str | None = None


class LicenseInfo(BaseModel):
    """Per-asset licensing. Shown before any download (TTS-02, NF-03)."""

    component: str
    spdx: str
    url: str | None = None
    acknowledgement_required: bool = False
    commercial_use: bool = True


class AssetSpec(BaseModel):
    name: str
    uri: str
    allow: list[str] = Field(default_factory=list)
    sha256: str | None = None
    size_bytes: int | None = None
    target: str | None = None


class VramProfileEntry(BaseModel):
    """Peak VRAM per precision. ``measured`` flips true after a real run (GPU-03)."""

    peak_mib: int
    measured: bool = False


class BackendDescriptor(BaseModel):
    """Everything the engine and the UI need to know about a backend."""

    id: str
    display_name: str
    adapter_version: str
    model: ModelRef | None = None
    capabilities: Capabilities
    #: JSON Schema with ``x-prl-ui`` hints (widget, group, order, step, advanced)
    #: so the Voices screen can render parameters generically (TTS-05).
    params_schema: dict[str, Any] = Field(default_factory=dict)
    vram_profile: dict[str, VramProfileEntry] = Field(default_factory=dict)
    licenses: list[LicenseInfo] = Field(default_factory=list)
    assets: list[AssetSpec] = Field(default_factory=list)


class VoiceRef(BaseModel):
    profile_id: str
    #: POSIX-style path to the processed reference clip.
    ref_audio: str | None = None
    ref_text: str | None = None


class LoadContext(BaseModel):
    device: str = "cpu"
    precision: str = "fp16"
    models_dir: str
    backend_params: dict[str, Any] = Field(default_factory=dict)


class LoadReport(BaseModel):
    loaded: bool
    device: str
    precision: str
    model_revision: str | None = None
    vram_mib: int | None = None
    load_ms: int = 0


class SynthesisRequest(BaseModel):
    text: str
    language: str = "pl"
    voice: VoiceRef | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    seed: int | None = None
    out_path: str


class SynthesisResult(BaseModel):
    duration_s: float
    sample_rate: int
    peak_vram_mib: int | None = None
    infer_ms: int
    rtf: float
    model_revision: str | None = None
    watermarked: bool = False
    #: Path actually written, including ``.part``. The engine renames it.
    out_path: str


class VramReport(BaseModel):
    device: str | None = None
    allocated_mib: int | None = None
    reserved_mib: int | None = None
    peak_mib: int | None = None


class WorkerRequest(BaseModel):
    """One line from the engine.

    ``params`` carries the load context for ``load`` and the backend parameters
    for ``synthesize``; the two shapes are unrelated, so they are validated by
    :meth:`load_context` and :meth:`synthesis` at the point of use.
    """

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    op: WorkerOp
    params: dict[str, Any] | None = None
    text: str | None = None
    language: str | None = None
    voice: VoiceRef | None = None
    seed: int | None = None
    out_path: str | None = None

    def load_context(self) -> LoadContext:
        try:
            return LoadContext.model_validate(self.params or {})
        except ValidationError as exc:
            raise TtsError(
                TtsErrorCode.INTERNAL,
                f"invalid load params: {exc.error_count()} field errors",
            ) from exc

    def synthesis(self) -> SynthesisRequest:
        if not self.text:
            raise TtsError(TtsErrorCode.INTERNAL, "synthesize requires a non-empty 'text'")
        if not self.out_path:
            raise TtsError(TtsErrorCode.INTERNAL, "synthesize requires 'out_path'")
        return SynthesisRequest(
            text=self.text,
            language=self.language or "pl",
            voice=self.voice,
            params=self.params or {},
            seed=self.seed,
            out_path=self.out_path,
        )


class WorkerErrorBody(BaseModel):
    code: TtsErrorCode
    message: str
    retryable: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)


class WorkerResponse(BaseModel):
    """One line back to the engine: either a reply to a request or an event."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    ok: bool | None = None
    result: dict[str, Any] | None = None
    error: WorkerErrorBody | None = None
    event: WorkerEvent | None = None

    @classmethod
    def success(cls, request_id: int | None, result: BaseModel | dict[str, Any]) -> WorkerResponse:
        payload = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        return cls(id=request_id, ok=True, result=payload)

    @classmethod
    def failure(cls, request_id: int | None, error: WorkerErrorBody) -> WorkerResponse:
        return cls(id=request_id, ok=False, error=error)

    @classmethod
    def from_exception(cls, request_id: int | None, exc: BaseException) -> WorkerResponse:
        if isinstance(exc, TtsError):
            body = WorkerErrorBody(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                detail=exc.detail,
            )
        else:
            body = WorkerErrorBody(
                code=TtsErrorCode.INTERNAL,
                message=f"{type(exc).__name__}: {exc}",
                retryable=False,
            )
        return cls.failure(request_id, body)

    @classmethod
    def ready(cls, **fields: Any) -> WorkerResponse:
        return cls(event=WorkerEvent.READY, **fields)


class TtsBackend:
    """The plugin contract. Real backends subclass it; ``fake`` needs no torch.

    Matches the ``TtsBackend`` shape in PLAN.md §6.1, with one change: ``describe``
    is a ``classmethod`` rather than a ``staticmethod`` so a backend can build its
    descriptor from its own ``id`` and ``adapter_version``. The engine never calls
    it in-process — it asks a worker over the wire (``{"op": "describe"}``) — so
    the difference is invisible outside this package.

    Subclasses must set :attr:`id` and :attr:`adapter_version`. The adapter
    version is part of the chunk ``render_key``, so bumping it invalidates cached
    audio — do it only when the output actually changes (DATA_MODEL.md §9.1).
    """

    id: ClassVar[str] = ""
    adapter_version: ClassVar[str] = "0.0.0"

    @classmethod
    def describe(cls) -> BackendDescriptor:
        raise NotImplementedError

    def load(self, ctx: LoadContext) -> LoadReport:
        raise NotImplementedError

    def synthesize(self, req: SynthesisRequest) -> SynthesisResult:
        raise NotImplementedError

    def probe_vram(self) -> VramReport:
        return VramReport()

    def unload(self) -> None:
        return None
