# SPDX-License-Identifier: Apache-2.0
"""Unit tests for prefixed ULID generation and validation."""

from __future__ import annotations

import time

from praelector.domain.ids import (
    CHAPTER_PREFIX,
    PROJECT_PREFIX,
    generate_id,
    generate_raw_ulid,
    validate_id,
)


def test_generate_raw_ulid_format() -> None:
    ulid = generate_raw_ulid()
    assert len(ulid) == 26
    assert ulid.isalnum()


def test_generate_prefixed_id() -> None:
    prj_id = generate_id(PROJECT_PREFIX)
    assert prj_id.startswith("prj_")
    assert len(prj_id) == 30
    assert validate_id(prj_id, expected_prefix=PROJECT_PREFIX)


def test_validate_id_mismatch_prefix() -> None:
    prj_id = generate_id(PROJECT_PREFIX)
    assert not validate_id(prj_id, expected_prefix=CHAPTER_PREFIX)


def test_validate_id_invalid_string() -> None:
    assert not validate_id("invalid")
    assert not validate_id("prj_too_short")
    assert not validate_id("unknown_01J8XA23456789ABCDEFGHJKMN")


def test_ulid_monotonic_time_ordering() -> None:
    ulid1 = generate_raw_ulid(timestamp_ms=1000)
    time.sleep(0.002)
    ulid2 = generate_raw_ulid(timestamp_ms=2000)
    assert ulid1 < ulid2
