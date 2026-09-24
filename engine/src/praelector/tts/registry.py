# SPDX-License-Identifier: Apache-2.0
"""Backend lookup (TTS-01, TTS-05).

Descriptors are the engine-side records from :mod:`praelector.tts.protocol`.
The language check is :func:`praelector.tts.protocol.assert_language`. This
module only stores them and finds them by id.
"""

from __future__ import annotations

from praelector.errors import AppError, ErrorCode
from praelector.tts.protocol import (
    BackendDescriptor,
    Capabilities,
    ReferenceAudio,
    assert_language,
)


class BackendRegistry:
    """Descriptors registered for this process. Later registrations replace an id."""

    def __init__(self) -> None:
        self._by_id: dict[str, BackendDescriptor] = {}

    def register(self, descriptor: BackendDescriptor) -> None:
        self._by_id[descriptor.id] = descriptor

    def get(self, backend_id: str) -> BackendDescriptor:
        try:
            return self._by_id[backend_id]
        except KeyError:
            raise AppError(
                ErrorCode.TTS_BACKEND_NOT_FOUND,
                detail={"backend_id": backend_id},
                message="no TTS backend is registered under that id",
            ) from None

    def require_language(self, backend_id: str, language: str) -> BackendDescriptor:
        """Return the descriptor, or raise when it does not list ``language``."""
        descriptor = self.get(backend_id)
        assert_language(descriptor, language)
        return descriptor


def fake_descriptor() -> BackendDescriptor:
    """The CI stand-in. It speaks Polish and needs no reference audio."""
    return BackendDescriptor(
        id="fake",
        adapter_version="1.0.0",
        capabilities=Capabilities(
            languages=("pl", "en"),
            native_sample_rate=24000,
            reference_audio=ReferenceAudio(
                required=False,
                min_seconds=0,
                max_seconds=0,
                needs_ref_text=False,
                target_sample_rate=24000,
            ),
            deterministic_with_seed=True,
        ),
    )


def builtin_registry() -> BackendRegistry:
    """The backends the engine knows before a plugin is added. Fake is always there."""
    registry = BackendRegistry()
    registry.register(fake_descriptor())
    return registry
