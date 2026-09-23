# SPDX-License-Identifier: Apache-2.0
"""Plain-text split/join and block-id re-association (D-08)."""

from __future__ import annotations

from praelector.text.plain import (
    SIMILARITY_THRESHOLD,
    associate_block_ids,
    join_plain_text,
    replacement_count,
    split_plain_text,
)


def test_plain_text_round_trips_across_blank_lines() -> None:
    parts = ["Chapter One", "It was a bright cold day in April.", "The clocks struck."]
    assert split_plain_text(join_plain_text(parts)) == parts
    assert split_plain_text("alpha\r\n\r\nbeta\n\n") == ["alpha", "beta"]
    assert split_plain_text("keeps\na single break") == ["keeps\na single break"]


def test_a_few_changed_characters_keep_the_block_id() -> None:
    existing = [
        ("blk_heading", "Chapter One"),
        ("blk_body", "It was a bright cold day in April."),
    ]
    assigned = associate_block_ids(
        existing,
        ["Chapter One", "It was a bright cold day in Aprl."],
    )
    assert assigned == ["blk_heading", "blk_body"]
    assert SIMILARITY_THRESHOLD == 0.6


def test_unrelated_text_does_not_reuse_a_block_id() -> None:
    assigned = associate_block_ids(
        [("blk_body", "It was a bright cold day in April.")],
        ["Zupełnie inny akapit, który nie przypomina poprzedniego."],
    )
    assert assigned == [None]


def test_replacement_count_is_case_sensitive_and_non_overlapping() -> None:
    assert replacement_count("April april April", "April") == 2
    assert replacement_count("April", "april") == 0
    assert replacement_count("aaaa", "aa") == 2
    assert replacement_count("April", "") == 0
