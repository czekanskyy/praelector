# SPDX-License-Identifier: Apache-2.0
"""Backend registry.

Backends are imported **lazily by id**: a real backend imports torch, and this
package must stay importable with no extra installed so the ``fake`` backend can
drive CI. Adding a backend means adding one line to :data:`_REGISTRY` and one
module under ``praelector_tts.backends``.
"""

from __future__ import annotations

import importlib
from typing import cast

from praelector_tts.protocol import BackendDescriptor, TtsBackend

#: backend id -> "module:ClassName". Real backends land in M3/M4.
_REGISTRY: dict[str, str] = {
    "fake": "praelector_tts.backends.fake:FakeBackend",
}


class UnknownBackendError(KeyError):
    """Raised for an id that is not registered."""

    def __init__(self, backend_id: str) -> None:
        super().__init__(backend_id)
        self.backend_id = backend_id
        self.known = sorted(_REGISTRY)


def available_backend_ids() -> list[str]:
    return sorted(_REGISTRY)


def backend_class(backend_id: str) -> type[TtsBackend]:
    """Resolve the class without importing any backend other than the one asked for."""
    target = _REGISTRY.get(backend_id)
    if target is None:
        raise UnknownBackendError(backend_id)
    module_name, _, class_name = target.partition(":")
    module = importlib.import_module(module_name)
    return cast(type[TtsBackend], module.__dict__[class_name])


def create_backend(backend_id: str) -> TtsBackend:
    return backend_class(backend_id)()


def describe(backend_id: str) -> BackendDescriptor:
    """A descriptor without instantiating or loading anything heavy."""
    return backend_class(backend_id).describe()


def describe_all() -> list[BackendDescriptor]:
    return [describe(backend_id) for backend_id in available_backend_ids()]
