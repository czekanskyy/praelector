# SPDX-License-Identifier: Apache-2.0
"""Tests for prefixed ULID identifiers."""

from __future__ import annotations

import pytest

from praelector.domain.ids import IdPrefix, is_valid_id, new_id, prefix_of


def test_id_carries_its_prefix() -> None:
    assert new_id(IdPrefix.PROJECT).startswith("prj_")
    assert new_id(IdPrefix.JOB).startswith("job_")


def test_id_is_deterministic_for_fixed_inputs() -> None:
    first = new_id(IdPrefix.CHAPTER, timestamp_ms=1_700_000_000_000, entropy=0)
    second = new_id(IdPrefix.CHAPTER, timestamp_ms=1_700_000_000_000, entropy=0)
    assert first == second
    assert len(first) == len("chp_") + 26


def test_ids_sort_by_creation_time() -> None:
    older = new_id(IdPrefix.SPAN, timestamp_ms=1_700_000_000_000, entropy=1)
    newer = new_id(IdPrefix.SPAN, timestamp_ms=1_700_000_000_001, entropy=0)
    assert sorted([newer, older]) == [older, newer]


def test_random_ids_do_not_collide() -> None:
    ids = {new_id(IdPrefix.SUGGESTION) for _ in range(2000)}
    assert len(ids) == 2000


@pytest.mark.parametrize("prefix", list(IdPrefix))
def test_every_prefix_round_trips(prefix: IdPrefix) -> None:
    value = new_id(prefix)
    assert is_valid_id(value)
    assert prefix_of(value) == prefix.value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "prj_",
        "unknown_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "prj_01ARZ3NDEKTSV4RRFFQ69G5FA",  # one char short
        "prj_01ARZ3NDEKTSV4RRFFQ69G5FAVV",  # one char long
        "prj_01ARZ3NDEKTSV4RRFFQ69G5FAL",  # L is not in the Crockford alphabet
        "prj01ARZ3NDEKTSV4RRFFQ69G5FAV",  # no separator
    ],
)
def test_invalid_ids_are_rejected(value: str) -> None:
    assert not is_valid_id(value)


def test_out_of_range_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="ULID range"):
        new_id(IdPrefix.PROJECT, timestamp_ms=2**48)
    with pytest.raises(ValueError, match="entropy"):
        new_id(IdPrefix.PROJECT, entropy=-1)
