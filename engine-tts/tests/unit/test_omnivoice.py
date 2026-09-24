# SPDX-License-Identifier: Apache-2.0
"""OmniVoice descriptor and request checks. No weights are downloaded."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from praelector_tts.backends import describe
from praelector_tts.backends.omnivoice import (
    PEAK_VRAM_MIB,
    POLISH_LANGUAGE_ID,
    PRECISION,
    OmniVoiceBackend,
)
from praelector_tts.protocol import LoadContext, SynthesisRequest, TtsError, TtsErrorCode, VoiceRef

_PROBE = """
import json, sys
from praelector_tts.backends import describe
describe("omnivoice")
print(json.dumps({"torch_imported": "torch" in sys.modules}))
"""


def test_importing_the_adapter_does_not_import_torch() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        env=os.environ.copy(),
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1])["torch_imported"] is False


def test_descriptor_is_polish_fp16_and_apache() -> None:
    descriptor = describe("omnivoice")
    assert descriptor.id == "omnivoice"
    assert descriptor.capabilities.languages[0] == POLISH_LANGUAGE_ID == "pl"
    assert descriptor.capabilities.voice_design is False
    audio = descriptor.capabilities.reference_audio
    assert audio is not None
    assert audio.needs_ref_text is True
    assert descriptor.vram_profile[PRECISION].peak_mib == PEAK_VRAM_MIB
    assert descriptor.vram_profile[PRECISION].measured is False
    assert descriptor.licenses
    for entry in descriptor.licenses:
        assert entry.spdx == "Apache-2.0"
        assert entry.acknowledgement_required is False


def test_missing_ref_text_is_refused_before_any_model() -> None:
    backend = _loaded()
    with pytest.raises(TtsError) as excinfo:
        backend.synthesize(
            SynthesisRequest(text="Cześć.", language="pl", out_path="out.wav", voice=None)
        )
    assert excinfo.value.detail["reason"] == "ref_text_required"


def test_a_non_polish_language_is_refused() -> None:
    backend = _loaded()
    with pytest.raises(TtsError) as excinfo:
        backend.synthesize(
            SynthesisRequest(
                text="Hello.",
                language="en",
                out_path="out.wav",
                voice=VoiceRef(profile_id="v", ref_text="Hello."),
            )
        )
    assert excinfo.value.code is TtsErrorCode.LANGUAGE_UNSUPPORTED
    assert excinfo.value.detail["language_id"] == "pl"


def test_fp16_is_the_only_load_precision() -> None:
    backend = OmniVoiceBackend()
    with pytest.raises(TtsError) as excinfo:
        backend.load(LoadContext(models_dir="/tmp/models", precision="fp32"))
    assert excinfo.value.detail["reason"] == "precision"


def _loaded() -> OmniVoiceBackend:
    backend = OmniVoiceBackend()
    backend.load(LoadContext(models_dir="/tmp/models", precision=PRECISION))
    return backend
