# SPDX-License-Identifier: Apache-2.0
"""Chunk identity (JB-05, PLAN.md §8.3).

``render_key`` changes when the spoken text, the voice, or an audio-affecting
parameter changes. Chapter order is not part of it.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

CHUNKER_VERSION = "1"
AUDIO_FORMAT_VERSION = "1"


def text_hash(spoken_text: str) -> bytes:
    """blake2s of the NFC-normalised, stripped spoken text."""
    normalised = unicodedata.normalize("NFC", spoken_text).strip().encode()
    return hashlib.blake2s(normalised, digest_size=16).digest()


def render_key(
    *,
    spoken_text: str,
    voice_slot: str,
    voice_profile_id: str,
    voice_profile_content_hash: str,
    backend_id: str,
    adapter_version: str,
    model_revision: str,
    params: dict[str, Any],
    seed: int | None = None,
    chunker_version: str = CHUNKER_VERSION,
    audio_format_version: str = AUDIO_FORMAT_VERSION,
) -> str:
    """32-char hex key. ``seed`` is mixed in only when it is set."""
    payload: dict[str, Any] = {"params": params}
    if seed is not None:
        payload["seed"] = seed
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    params_hash = hashlib.blake2s(canonical.encode(), digest_size=16).digest()
    material = b"".join(
        (
            b"prl1|",
            text_hash(spoken_text),
            voice_slot.encode(),
            voice_profile_id.encode(),
            voice_profile_content_hash.encode(),
            backend_id.encode(),
            adapter_version.encode(),
            model_revision.encode(),
            params_hash,
            chunker_version.encode(),
            audio_format_version.encode(),
        )
    )
    return hashlib.blake2s(material, digest_size=16).hexdigest()
