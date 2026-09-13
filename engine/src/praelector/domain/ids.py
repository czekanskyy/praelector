# SPDX-License-Identifier: Apache-2.0
"""Prefixed ULID identifier generation and validation.

Generates sortable, collision-resistant, 26-character Crockford Base32 ULIDs
with semantic entity prefixes (e.g. prj_01J8XA..., chp_01J8XA...).
"""

from __future__ import annotations

import os
import time

CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Recognized domain prefixes per DATA_MODEL.md
PROJECT_PREFIX = "prj"
CHAPTER_PREFIX = "chp"
BLOCK_PREFIX = "blk"
SPAN_PREFIX = "spn"
SUGGESTION_PREFIX = "sug"
VOICE_PROFILE_PREFIX = "vpr"
JOB_PREFIX = "job"
LEXICON_PREFIX = "lex"
BATCH_PREFIX = "bat"

VALID_PREFIXES = frozenset(
    {
        PROJECT_PREFIX,
        CHAPTER_PREFIX,
        BLOCK_PREFIX,
        SPAN_PREFIX,
        SUGGESTION_PREFIX,
        VOICE_PROFILE_PREFIX,
        JOB_PREFIX,
        LEXICON_PREFIX,
        BATCH_PREFIX,
    }
)


def _encode_crockford(val: int, length: int) -> str:
    """Encode an integer into Crockford Base32 with fixed length."""
    chars: list[str] = []
    for _ in range(length):
        chars.append(CROCKFORD_BASE32[val & 0x1F])
        val >>= 5
    return "".join(reversed(chars))


def generate_raw_ulid(timestamp_ms: int | None = None) -> str:
    """Generate a standard 26-character Crockford Base32 ULID.

    48-bit timestamp (10 chars) + 80-bit randomness (16 chars).
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    time_part = _encode_crockford(timestamp_ms & 0xFFFFFFFFFFFF, 10)

    rand_bytes = os.urandom(10)
    rand_int = int.from_bytes(rand_bytes, byteorder="big")
    rand_part = _encode_crockford(rand_int, 16)

    return time_part + rand_part


def generate_id(prefix: str) -> str:
    """Generate a prefixed ULID (e.g. 'prj_01J8XA...')."""
    return f"{prefix}_{generate_raw_ulid()}"


def validate_id(id_str: str, expected_prefix: str | None = None) -> bool:
    """Validate a prefixed ULID format and optionally its prefix."""
    if not isinstance(id_str, str) or "_" not in id_str:
        return False

    prefix, ulid_part = id_str.split("_", 1)
    if expected_prefix is not None and prefix != expected_prefix:
        return False

    if prefix not in VALID_PREFIXES and expected_prefix is None:
        return False

    if len(ulid_part) != 26:
        return False

    return all(c in CROCKFORD_BASE32 for c in ulid_part)
