# SPDX-License-Identifier: Apache-2.0
"""Prefixed ULID identifiers (DATA_MODEL.md preamble).

Ids are sortable without coordination and self-describing, so a stray id in a log
line or a bug report says what it refers to: ``prj_``, ``chp_``, ``blk_``,
``spn_``, ``sug_``, ``vpr_``, ``job_``, ``lex_``, ``bat_``.
"""

from __future__ import annotations

import secrets
import time
from enum import StrEnum

# Crockford base32: no I, L, O or U, so an id read aloud over the phone survives.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_BODY_LENGTH = 26
_TIMESTAMP_CHARS = 10
_ENTROPY_CHARS = _BODY_LENGTH - _TIMESTAMP_CHARS
_ENTROPY_BITS = _ENTROPY_CHARS * 5


class IdPrefix(StrEnum):
    PROJECT = "prj"
    CHAPTER = "chp"
    BLOCK = "blk"
    SPAN = "spn"
    SUGGESTION = "sug"
    VOICE_PROFILE = "vpr"
    JOB = "job"
    LEXICON_ENTRY = "lex"
    BATCH = "bat"


def _encode(value: int, length: int) -> str:
    digits = []
    for _ in range(length):
        digits.append(_ALPHABET[value & 0x1F])
        value >>= 5
    digits.reverse()
    return "".join(digits)


def new_id(
    prefix: IdPrefix,
    *,
    timestamp_ms: int | None = None,
    entropy: int | None = None,
) -> str:
    """Mint an id. Both inputs are injectable so tests can be deterministic."""
    if timestamp_ms is None:
        timestamp_ms = time.time_ns() // 1_000_000
    if entropy is None:
        entropy = secrets.randbits(_ENTROPY_BITS)
    if not 0 <= timestamp_ms < 2**48:
        raise ValueError(f"timestamp_ms out of ULID range: {timestamp_ms}")
    if not 0 <= entropy < 2**_ENTROPY_BITS:
        raise ValueError("entropy out of range")
    return f"{prefix}_{_encode(timestamp_ms, _TIMESTAMP_CHARS)}{_encode(entropy, _ENTROPY_CHARS)}"


def is_valid_id(value: str) -> bool:
    """True when ``value`` is a well-formed id of any known prefix."""
    head, sep, body = value.partition("_")
    if not sep or head not in set(IdPrefix) or len(body) != _BODY_LENGTH:
        return False
    return all(char in _ALPHABET for char in body)


def prefix_of(value: str) -> str | None:
    """The prefix of an id, or None when it is not one of ours."""
    head, sep, _ = value.partition("_")
    return head if sep and head in set(IdPrefix) else None
