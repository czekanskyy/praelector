# SPDX-License-Identifier: Apache-2.0
"""Lookup of registered TTS backends. No model is loaded."""

from __future__ import annotations

import pytest

from praelector.errors import AppError, ErrorCode
from praelector.tts.protocol import BackendDescriptor, Capabilities, ReferenceAudio
from praelector.tts.registry import BackendRegistry, builtin_registry, fake_descriptor


def test_fake_and_another_backend_are_found_by_id() -> None:
    registry = builtin_registry()
    registry.register(_qwen())
    assert registry.get("fake").id == "fake"
    assert "pl" in registry.get("fake").capabilities.languages
    assert registry.get("qwen3_tts").id == "qwen3_tts"


def test_an_unknown_id_is_a_clean_error() -> None:
    with pytest.raises(AppError) as excinfo:
        builtin_registry().get("missing")
    assert excinfo.value.code is ErrorCode.TTS_BACKEND_NOT_FOUND
    assert excinfo.value.detail["backend_id"] == "missing"


def test_a_language_outside_the_list_is_unsupported() -> None:
    registry = BackendRegistry()
    registry.register(_qwen())
    with pytest.raises(AppError) as excinfo:
        registry.require_language("qwen3_tts", "pl")
    assert excinfo.value.code is ErrorCode.TTS_LANGUAGE_UNSUPPORTED
    assert excinfo.value.detail["language"] == "pl"


def test_fake_advertises_polish() -> None:
    descriptor = fake_descriptor()
    assert isinstance(descriptor, BackendDescriptor)
    builtin_registry().require_language("fake", "pl")


def _qwen() -> BackendDescriptor:
    return BackendDescriptor(
        id="qwen3_tts",
        adapter_version="1.0.0",
        capabilities=Capabilities(
            languages=("en", "de"),
            native_sample_rate=24000,
            reference_audio=ReferenceAudio(
                required=True,
                min_seconds=3,
                max_seconds=20,
                needs_ref_text=True,
                target_sample_rate=24000,
            ),
        ),
    )
