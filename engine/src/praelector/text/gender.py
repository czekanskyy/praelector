# SPDX-License-Identifier: Apache-2.0
"""Speaker gender for dialogue spans (DG-03..DG-06, PLAN.md §5.3).

The speech-verb suffix wins. A given name, including the ``-a`` male
exceptions, never overrides it. Pronouns in the neighbouring blocks and a
chapter speaker map fill in only when that suffix is missing. Nothing here
calls a model, and block text is not rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from praelector.domain.enums import Gender, SuggestionCategory
from praelector.text.dialogue import Segment, segment_block, speech_verbs
from praelector.text.suggestion import Suggestion, make_suggestion

_VERBS = speech_verbs()
_KIND = SuggestionCategory.SPEAKER_GENDER
_VERB_CONFIDENCE = 0.95
_NAME_CONFIDENCE = 0.85
_PRONOUN_CONFIDENCE = 0.65
_MAP_CONFIDENCE = 0.60
_UNKNOWN_CONFIDENCE = 0.40
_CONTESTED = 0.69

_FEMALE_WORDS = frozenset({"ona", "jej", "nią", "sama", "zrobiła"})
_MALE_WORDS = frozenset({"on", "jego", "niego", "sam", "zrobił"})


@dataclass(frozen=True, slots=True)
class _Reading:
    gender: str
    confidence: float
    reason: str
    speaker_id: str


def given_names() -> dict[str, str]:
    """``name.casefold()`` → ``male`` or ``female`` from the curated TSV."""
    path = Path(__file__).with_name("data") / "given_names_pl.tsv"
    names: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        body = line.split("#", 1)[0].strip()
        if not body or "\t" not in body:
            continue
        name, gender = body.split("\t", 1)
        names[name.strip().casefold()] = gender.strip()
    return names


_NAMES = given_names()


def gender_suggestions(blocks: list[str]) -> list[Suggestion]:
    """One ``speaker_gender`` suggestion per dialogue span, in reading order."""
    snapshot = tuple(blocks)
    found: list[Suggestion] = []
    speakers: dict[str, str] = {}
    for index, text in enumerate(blocks):
        for reading, segment in _block_readings(blocks, index, speakers):
            found.append(
                make_suggestion(
                    text=text,
                    start=segment.start,
                    end=segment.end,
                    replacement=reading.gender,
                    kind=_KIND,
                    reason=reading.reason,
                    confidence=reading.confidence,
                    block_index=index,
                    speaker_id=reading.speaker_id,
                )
            )
            if reading.speaker_id and reading.confidence >= _NAME_CONFIDENCE:
                speakers[reading.speaker_id.casefold()] = reading.gender
    if tuple(blocks) != snapshot:
        raise RuntimeError("gender pass rewrote a block")
    return found


def _block_readings(
    blocks: list[str], index: int, speakers: dict[str, str]
) -> list[tuple[_Reading, Segment]]:
    text = blocks[index]
    segments = segment_block(text)
    readings: list[tuple[_Reading, Segment]] = []
    carried: _Reading | None = None
    for position, segment in enumerate(segments):
        if segment.kind != "dialogue":
            continue
        tag = _attached_tag(text, segments, position)
        reading = _from_tag(tag, _name_beside(text, segments, position, tag)) if tag else None
        if reading is None:
            tail = _tail_name(text[segment.start : segment.end])
            if tail:
                reading = _from_tag(tail)
        if reading is None and carried is not None:
            reading = _Reading(carried.gender, _MAP_CONFIDENCE, "continuation", carried.speaker_id)
        if reading is None:
            reading = _from_pronouns(blocks, index) or _unknown()
        mapped = speakers.get(reading.speaker_id.casefold()) if reading.speaker_id else None
        if reading.reason == "unresolved" and mapped:
            reading = _Reading(mapped, _MAP_CONFIDENCE, "speaker_map", reading.speaker_id)
        readings.append((reading, segment))
        if reading.confidence >= _NAME_CONFIDENCE:
            carried = reading
    return readings


def _attached_tag(text: str, segments: list[Segment], index: int) -> str | None:
    after = _neighbor(text, segments, index, 1)
    if after and (_leading_verb(after) or _speaker_name(after)):
        return after
    before = _neighbor(text, segments, index, -1)
    if before and (_leading_verb(before) or _speaker_name(before) or before.rstrip().endswith(":")):
        return before
    return None


def _neighbor(text: str, segments: list[Segment], index: int, step: int) -> str | None:
    other = index + step
    if not 0 <= other < len(segments) or segments[other].kind != "narration":
        return None
    span = segments[other]
    return text[span.start : span.end]


def _name_beside(text: str, segments: list[Segment], index: int, tag: str | None) -> str:
    """A name in the narration on the other side of the line, as with Walker."""
    if tag and _speaker_name(tag):
        return ""
    for step in (1, -1):
        other = _neighbor(text, segments, index, step)
        if other and other != tag:
            name = _speaker_name(other)
            if name:
                return name
    return ""


def _from_tag(tag: str, beside: str = "") -> _Reading | None:
    verb = _leading_verb(tag)
    speaker = _speaker_name(tag) or beside
    verb_gender = _verb_gender(verb) if verb else None
    name_gender = _NAMES.get(speaker.casefold()) if speaker else None
    if verb_gender and name_gender and verb_gender != name_gender:
        return _Reading(verb_gender, _CONTESTED, "contested", speaker)
    if verb_gender:
        return _Reading(verb_gender, _VERB_CONFIDENCE, "verb_suffix", speaker)
    if name_gender and speaker:
        return _Reading(name_gender, _NAME_CONFIDENCE, "given_name", speaker)
    if speaker:
        return _Reading(Gender.UNKNOWN, _UNKNOWN_CONFIDENCE, "unresolved", speaker)
    return None


def _leading_verb(text: str) -> str | None:
    tokens = _tokens(text)[:3]
    for offset, token in enumerate(tokens):
        if token.casefold() in _VERBS and all(_prefix(item) for item in tokens[:offset]):
            return token
    return None


def _prefix(token: str) -> bool:
    folded = token.casefold()
    return folded in {"on", "ona", "ono", "oni", "one"} or (
        token[:1].isupper() and folded not in _VERBS
    )


def _verb_gender(verb: str) -> str | None:
    folded = verb.casefold()
    if folded.endswith("ła"):
        return Gender.FEMALE
    if folded.endswith("ł"):
        return Gender.MALE
    return None


def _tail_name(text: str) -> str:
    """The word after the last dash, when the split stayed inside one span."""
    body = text
    for dash in ("\u2014", "\u2013", " - "):
        if dash in body:
            body = body.split(dash)[-1]
    token = body.strip(" \t.")
    if token and " " not in token and _looks_like_name(token):
        return token
    return ""


def _speaker_name(text: str) -> str:
    for token in _tokens(text):
        if _looks_like_name(token):
            return token
    return ""


def _looks_like_name(token: str) -> bool:
    if len(token) < 2 or not token[:1].isupper() or token.isupper():
        return False
    return token.casefold() not in _VERBS


def _from_pronouns(blocks: list[str], index: int) -> _Reading | None:
    window = " ".join(blocks[max(0, index - 1) : index + 2])
    genders = {_word_gender(token) for token in _tokens(window)}
    genders.discard(None)
    if genders == {Gender.FEMALE}:
        return _Reading(Gender.FEMALE, _PRONOUN_CONFIDENCE, "pronoun", "")
    if genders == {Gender.MALE}:
        return _Reading(Gender.MALE, _PRONOUN_CONFIDENCE, "pronoun", "")
    return None


def _word_gender(token: str) -> str | None:
    folded = token.casefold()
    if folded in _FEMALE_WORDS or (folded.endswith("ła") and folded in _VERBS):
        return Gender.FEMALE
    if folded in _MALE_WORDS or (folded.endswith("ł") and folded in _VERBS):
        return Gender.MALE
    return None


def _unknown() -> _Reading:
    return _Reading(Gender.UNKNOWN, _UNKNOWN_CONFIDENCE, "unresolved", "")


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    cursor = 0
    while cursor < len(text):
        while cursor < len(text) and not text[cursor].isalnum():
            cursor += 1
        start = cursor
        while cursor < len(text) and text[cursor].isalnum():
            cursor += 1
        if start < cursor:
            tokens.append(text[start:cursor])
    return tokens
