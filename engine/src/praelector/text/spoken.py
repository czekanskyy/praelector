# SPDX-License-Identifier: Apache-2.0
"""Render the spoken form of one block from its spans (ED-06)."""

from __future__ import annotations

from collections.abc import Sequence

from praelector.text.apply import AppliedSpan


def spoken_form(text: str, spans: Sequence[AppliedSpan]) -> str:
    """Replace pronunciation spans and drop skip spans. Narration is the print."""
    edits = sorted(
        (span for span in spans if span.kind in {"pronunciation", "skip"}),
        key=lambda span: span.start,
        reverse=True,
    )
    spoken = text
    for span in edits:
        if not 0 <= span.start <= span.end <= len(spoken):
            continue
        replacement = "" if span.kind == "skip" else span.spoken
        spoken = spoken[: span.start] + replacement + spoken[span.end :]
    return spoken
