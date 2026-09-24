# SPDX-License-Identifier: Apache-2.0
"""In-memory suggestion produced by a deterministic detector.

Nothing here is written to SQLite. The suggestion table arrives with the
review milestone; until then every producer stays a pure function of the
block text (product principle 1, AI-02).
"""

from __future__ import annotations

from dataclasses import dataclass

from praelector.domain.enums import Detector


@dataclass(frozen=True, slots=True)
class SegmentMark:
    """One narration or dialogue piece inside a ``dialogue_split`` payload."""

    kind: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Suggestion:
    """One proposed change. ``original`` is ``text[start:end]`` of that block.

    ``kind`` is a suggestion category, or ``skip`` for a front-matter span.
    ``reason`` is a short stable code, not a sentence. ``block_index`` is the
    position in the sequence passed to the pre-pass; single-block producers
    leave it at 0.
    """

    kind: str
    start: int
    end: int
    original: str
    replacement: str
    reason: str
    confidence: float
    detector: Detector = Detector.HEURISTIC
    block_index: int = 0
    #: A lexicon rule marked ``auto`` may be pre-accepted. Heuristics leave this false.
    auto: bool = False
    #: Structural payload for ``dialogue_split``. Empty for every other kind.
    segments: tuple[SegmentMark, ...] = ()
    #: Set on ``speaker_gender`` when a name is explicit (DG-06). Empty otherwise.
    speaker_id: str = ""

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("suggestion span is empty or inverted")
        if self.block_index < 0:
            raise ValueError("block index is negative")
        if not self.reason:
            raise ValueError("suggestion reason is empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.detector not in Detector:
            raise ValueError("unknown detector")


def make_suggestion(
    *,
    text: str,
    start: int,
    end: int,
    replacement: str,
    kind: str,
    reason: str,
    confidence: float,
    block_index: int = 0,
    detector: Detector = Detector.HEURISTIC,
    auto: bool = False,
    segments: tuple[SegmentMark, ...] = (),
    speaker_id: str = "",
) -> Suggestion:
    """Build a suggestion whose ``original`` is taken from ``text``."""
    if not 0 <= start <= end <= len(text):
        raise ValueError("suggestion span is outside the text")
    return Suggestion(
        kind=kind,
        start=start,
        end=end,
        original=text[start:end],
        replacement=replacement,
        reason=reason,
        confidence=confidence,
        detector=detector,
        block_index=block_index,
        auto=auto,
        segments=segments,
        speaker_id=speaker_id,
    )
