# SPDX-License-Identifier: Apache-2.0
"""Base interface for TTS backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseBackend(ABC):
    """Abstract base class for TTS synthesis backends."""

    backend_id: str

    @abstractmethod
    def synthesize(
        self,
        text: str,
        output_path: str,
        reference_audio_path: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[float, int]:
        """Synthesize text into a WAV file.

        Returns:
            Tuple of (audio_duration_seconds, sample_rate).
        """
        raise NotImplementedError
