# SPDX-License-Identifier: Apache-2.0
"""Speaker gender resolution signal ladder for Polish dialogue (DG-03..DG-06).

Implements the 5-tier precision ladder from section 5.3 of the master plan:
1. Past-tense gender suffix of a speech verb in attached narration (-ł -> male, -ła -> female, 0.95).
2. Explicit given name in the speech tag resolved through given_names_pl.tsv (0.85),
   including mandatory -a male exceptions (Barnaba, Kuba, Bonawentura, Kosma, Jarema, Zawisza).
3. Adjacent-sentence pronouns and gendered participles (ona, zrobiła -> 0.65).
4. Chapter-scoped speaker map propagation (0.60).
5. Fallback according to project voice mode (DG-05).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from praelector.domain.enums import (
    DetectorKind,
    Gender,
    GenderDetector,
    SpanKind,
    SuggestionCategory,
    SuggestionStatus,
    VoiceMode,
    VoiceSlot,
)
from praelector.domain.models import SuggestionCreate
from praelector.text.dialogue import SPEECH_VERBS, WORD_RE, DialogueSegment

# Mandatory Polish male names ending in -a (§5.3 Rank 2)
MALE_A_EXCEPTIONS: Final[frozenset[str]] = frozenset(
    {
        "barnaba",
        "kuba",
        "bonawentura",
        "kosma",
        "jarema",
        "zawisza",
    }
)

# Third-person feminine and masculine indicators for Signal 3 (§5.3 Rank 3)
FEMININE_PRONOUNS_AND_PARTICIPLES: Final[frozenset[str]] = frozenset(
    {
        "ona",
        "jej",
        "ją",
        "nią",
        "zrobiła",
        "sama",
        "poszła",
        "zobaczyła",
        "mogła",
        "chciała",
        "wiedziała",
        "miała",
        "była",
        "stała",
        "spojrzała",
    }
)

MASCULINE_PRONOUNS_AND_PARTICIPLES: Final[frozenset[str]] = frozenset(
    {
        "on",
        "jego",
        "jemu",
        "nim",
        "zrobił",
        "sam",
        "poszedł",
        "zobaczył",
        "mógł",
        "chciał",
        "wiedział",
        "miał",
        "był",
        "stał",
        "spojrzał",
    }
)


class GivenNamesLexicon:
    """Lexicon of given names with gender markings and -a exception handling."""

    def __init__(self) -> None:
        self._names: dict[str, Gender] = {}
        self._load()

    def _load(self) -> None:
        path = Path(__file__).parent / "data" / "given_names_pl.tsv"
        if not path.is_file():
            return
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    name = parts[0].strip().lower()
                    gender_str = parts[1].strip().lower()
                    if gender_str == "male":
                        self._names[name] = Gender.MALE
                    elif gender_str == "female":
                        self._names[name] = Gender.FEMALE

    def lookup(self, word: str) -> tuple[Gender, float] | None:
        """Lookup gender for an explicit given name (0.85) or mandatory -a exception."""
        w_lower = word.lower()

        # 1. Mandatory -a male exceptions (Barnaba, Kuba, etc.) (§5.3 Rank 2)
        if w_lower in MALE_A_EXCEPTIONS:
            return Gender.MALE, 0.85

        # 2. Exact match in names lexicon (§5.3 Rank 2)
        if w_lower in self._names:
            return self._names[w_lower], 0.85

        return None


GIVEN_NAMES: Final[GivenNamesLexicon] = GivenNamesLexicon()


class ChapterSpeakerMap:
    """Tracks known speakers and their genders within a chapter scope (DG-04, DG-06)."""

    def __init__(self) -> None:
        self._speakers: dict[str, tuple[Gender, float]] = {}

    def get(self, speaker_id: str) -> tuple[Gender, float] | None:
        """Get the recorded gender and confidence for a speaker_id."""
        return self._speakers.get(speaker_id.lower())

    def record(self, speaker_id: str, gender: Gender, confidence: float) -> None:
        """Record a resolved speaker gender if confidence meets or exceeds existing."""
        if gender != Gender.UNKNOWN and speaker_id:
            key = speaker_id.lower()
            existing = self._speakers.get(key)
            if existing is None or confidence >= existing[1]:
                self._speakers[key] = (gender, confidence)

    def to_dict(self) -> dict[str, str]:
        """Return a string-to-string dictionary of speaker genders."""
        return {k: v[0].value for k, v in self._speakers.items()}


class GenderSignalResult(BaseModel):
    """Result of gender detection for a dialogue segment."""

    gender: Gender = Gender.UNKNOWN
    confidence: float = 0.0
    detector: GenderDetector = GenderDetector.HEURISTIC
    speaker_id: str | None = None
    rationale: str = "Unknown gender"
    voice_slot: VoiceSlot = VoiceSlot.NARRATOR


def _detect_speech_verb_gender(text: str) -> tuple[Gender, float, str] | None:
    """Signal 1: Past-tense gender suffix of a speech verb in attached narration (0.95).

    -ł -> male, -ła -> female.
    """
    for token in WORD_RE.findall(text):
        t_lower = token.lower()
        if t_lower in SPEECH_VERBS:
            if t_lower.endswith("ła"):
                return Gender.FEMALE, 0.95, f"Speech verb '{token}' has feminine past suffix -ła"
            elif t_lower.endswith("ł") and not t_lower.endswith("ło"):
                return Gender.MALE, 0.95, f"Speech verb '{token}' has masculine past suffix -ł"
    return None


def _detect_given_name_gender(text: str) -> tuple[str, Gender, float, str] | None:
    """Signal 2: Explicit given name in narration/speech tag (0.85).

    Resolves given names with mandatory -a male exceptions.
    """
    for token in WORD_RE.findall(text):
        if token[0].isupper():
            res = GIVEN_NAMES.lookup(token)
            if res is not None:
                gender, conf = res
                return token, gender, conf, f"Given name '{token}' resolved as {gender.value}"
    return None


def _detect_context_gender(context_text: str) -> tuple[Gender, float, str] | None:
    """Signal 3: Adjacent-sentence pronouns and gendered participles (0.65)."""
    tokens = [t.lower() for t in WORD_RE.findall(context_text)]
    fem_hits = sum(1 for t in tokens if t in FEMININE_PRONOUNS_AND_PARTICIPLES)
    masc_hits = sum(1 for t in tokens if t in MASCULINE_PRONOUNS_AND_PARTICIPLES)

    if fem_hits > 0 and masc_hits == 0:
        return Gender.FEMALE, 0.65, "Adjacent sentence feminine pronoun/participle"
    elif masc_hits > 0 and fem_hits == 0:
        return Gender.MALE, 0.65, "Adjacent sentence masculine pronoun/participle"
    return None


def resolve_segment_gender(
    dialogue_seg: DialogueSegment,
    attached_narrations: list[str],
    block_text: str,
    chapter_speaker_map: ChapterSpeakerMap | None = None,
    adjacent_context: str | None = None,
    voice_mode: VoiceMode = VoiceMode.NARRATOR_MALE_FEMALE,
) -> GenderSignalResult:
    """Resolve speaker gender for a dialogue segment using the 5-step signal ladder."""
    # 1. Check Signal 1 (Past-tense verb suffix in attached narration, 0.95)
    verb_res: tuple[Gender, float, str] | None = None
    for narr in attached_narrations:
        verb_res = _detect_speech_verb_gender(narr)
        if verb_res is not None:
            break

    # 2. Check Signal 2 (Explicit given name, 0.85)
    name_res: tuple[str, Gender, float, str] | None = None
    for narr in attached_narrations:
        name_res = _detect_given_name_gender(narr)
        if name_res is not None:
            break

    # Evaluate Signal 1 & Signal 2 combination
    if verb_res is not None and name_res is not None:
        speaker_name, name_gender, _, _ = name_res
        verb_gender, verb_conf, verb_rat = verb_res
        if verb_gender == name_gender:
            # Both agree (e.g. powiedziała Anna or Barnaba zapytał)
            slot = VoiceSlot.FEMALE if verb_gender == Gender.FEMALE else VoiceSlot.MALE
            return GenderSignalResult(
                gender=verb_gender,
                confidence=verb_conf,
                detector=GenderDetector.HEURISTIC,
                speaker_id=speaker_name,
                rationale=f"{verb_rat}; name '{speaker_name}' agrees",
                voice_slot=slot,
            )
        else:
            # Disagree -> signal conflict (§5.3 Rank 5)
            return GenderSignalResult(
                gender=Gender.UNKNOWN,
                confidence=0.50,
                detector=GenderDetector.HEURISTIC,
                speaker_id=speaker_name,
                rationale=f"Signal conflict: verb indicates {verb_gender.value} but name '{speaker_name}' indicates {name_gender.value}",
                voice_slot=VoiceSlot.NARRATOR,
            )

    if verb_res is not None:
        verb_gender, verb_conf, verb_rat = verb_res
        spk_id: str | None = name_res[0] if name_res else None
        slot = VoiceSlot.FEMALE if verb_gender == Gender.FEMALE else VoiceSlot.MALE
        return GenderSignalResult(
            gender=verb_gender,
            confidence=verb_conf,
            detector=GenderDetector.HEURISTIC,
            speaker_id=spk_id,
            rationale=verb_rat,
            voice_slot=slot,
        )

    if name_res is not None:
        speaker_name, name_gender, name_conf, name_rat = name_res
        slot = VoiceSlot.FEMALE if name_gender == Gender.FEMALE else VoiceSlot.MALE
        return GenderSignalResult(
            gender=name_gender,
            confidence=name_conf,
            detector=GenderDetector.HEURISTIC,
            speaker_id=speaker_name,
            rationale=name_rat,
            voice_slot=slot,
        )

    # 3. Check Signal 3 (Adjacent sentence pronouns and participles, 0.65)
    context_to_check = (block_text + " " + (adjacent_context or "")).strip()
    ctx_res = _detect_context_gender(context_to_check)
    if ctx_res is not None:
        ctx_gender, ctx_conf, ctx_rat = ctx_res
        slot = VoiceSlot.FEMALE if ctx_gender == Gender.FEMALE else VoiceSlot.MALE
        return GenderSignalResult(
            gender=ctx_gender,
            confidence=ctx_conf,
            detector=GenderDetector.HEURISTIC,
            speaker_id=None,
            rationale=ctx_rat,
            voice_slot=slot,
        )

    # 4. Check Signal 4 (Chapter speaker map propagation, 0.60)
    if chapter_speaker_map is not None and dialogue_seg.speaker_id:
        mapped = chapter_speaker_map.get(dialogue_seg.speaker_id)
        if mapped is not None:
            m_gender, _ = mapped
            slot = VoiceSlot.FEMALE if m_gender == Gender.FEMALE else VoiceSlot.MALE
            return GenderSignalResult(
                gender=m_gender,
                confidence=0.60,
                detector=GenderDetector.HEURISTIC,
                speaker_id=dialogue_seg.speaker_id,
                rationale=f"Propagated gender '{m_gender.value}' from chapter speaker map for '{dialogue_seg.speaker_id}'",
                voice_slot=slot,
            )

    # 5. Signal 5: Fallback when gender stays unknown (DG-05)
    fallback_slot = VoiceSlot.NARRATOR
    if voice_mode == VoiceMode.SINGLE:
        fallback_slot = VoiceSlot.NARRATOR
    elif voice_mode == VoiceMode.NARRATOR_DIALOGUE:
        fallback_slot = VoiceSlot.DIALOGUE
    elif voice_mode == VoiceMode.NARRATOR_MALE_FEMALE:
        fallback_slot = VoiceSlot.NARRATOR  # Flagged in review

    return GenderSignalResult(
        gender=Gender.UNKNOWN,
        confidence=0.0,
        detector=GenderDetector.HEURISTIC,
        speaker_id=None,
        rationale=f"Unknown gender; fallback to {fallback_slot.value} per {voice_mode.value} voice mode",
        voice_slot=fallback_slot,
    )


def resolve_speaker_gender(
    segments: list[DialogueSegment],
    block_text: str,
    chapter_speaker_map: ChapterSpeakerMap | None = None,
    adjacent_context: str | None = None,
    voice_mode: VoiceMode = VoiceMode.NARRATOR_MALE_FEMALE,
) -> list[DialogueSegment]:
    """Assign gender, speaker_id, and confidence to dialogue segments in a block."""
    # Find all narration texts in the block
    narration_texts = [s.text for s in segments if s.kind == SpanKind.NARRATION]

    # Find candidate speaker_id from block if any (e.g. Walker wzruszył ramionami)
    block_name_res = _detect_given_name_gender(block_text)
    default_speaker_id = block_name_res[0] if block_name_res else None

    # Track last resolved speaker in paragraph for dialogue continuations
    last_resolved_gender: Gender | None = None
    last_resolved_conf: float | None = None
    last_resolved_speaker: str | None = None

    for i, seg in enumerate(segments):
        if seg.kind != SpanKind.DIALOGUE:
            continue

        # Collect attached narration spans (immediate predecessor and successor)
        attached: list[str] = []
        if i + 1 < len(segments) and segments[i + 1].kind == SpanKind.NARRATION:
            attached.append(segments[i + 1].text)
        if i > 0 and segments[i - 1].kind == SpanKind.NARRATION:
            attached.append(segments[i - 1].text)
        # Fallback to all narration texts in block
        if not attached:
            attached.extend(narration_texts)

        res = resolve_segment_gender(
            dialogue_seg=seg,
            attached_narrations=attached,
            block_text=block_text,
            chapter_speaker_map=chapter_speaker_map,
            adjacent_context=adjacent_context,
            voice_mode=voice_mode,
        )

        # If unresolved but previous dialogue in the same block had a speaker, inherit it
        if (
            res.gender == Gender.UNKNOWN
            and last_resolved_gender is not None
            and last_resolved_gender != Gender.UNKNOWN
        ):
            seg.gender = last_resolved_gender
            seg.gender_confidence = last_resolved_conf
            seg.gender_detector = GenderDetector.HEURISTIC
            seg.speaker_id = last_resolved_speaker
        else:
            seg.gender = res.gender
            seg.gender_confidence = res.confidence
            seg.gender_detector = res.detector
            seg.speaker_id = res.speaker_id or default_speaker_id

            if res.gender != Gender.UNKNOWN:
                last_resolved_gender = res.gender
                last_resolved_conf = res.confidence
                last_resolved_speaker = seg.speaker_id

        # If resolved with high confidence and speaker_id exists, record into chapter map (DG-04, DG-06)
        if chapter_speaker_map is not None and seg.speaker_id and seg.gender != Gender.UNKNOWN:
            chapter_speaker_map.record(seg.speaker_id, seg.gender, seg.gender_confidence or 0.0)

    return segments


def generate_gender_suggestions(
    segments: list[DialogueSegment],
    project_id: str,
    chapter_id: str,
    block_id: str,
    base_revision: int = 0,
) -> list[SuggestionCreate]:
    """Generate SuggestionCreate records (SPEAKER_GENDER) for dialogue segments."""
    suggestions: list[SuggestionCreate] = []
    for seg in segments:
        if seg.kind != SpanKind.DIALOGUE:
            continue

        gender_val = seg.gender.value if seg.gender else "unknown"
        payload = {
            "gender": gender_val,
            "confidence": seg.gender_confidence or 0.0,
            "detector": seg.gender_detector.value if seg.gender_detector else "heuristic",
            "speaker_id": seg.speaker_id,
        }

        rationale = f"Speaker gender {gender_val}"
        if seg.speaker_id:
            rationale += f" for '{seg.speaker_id}'"

        suggestions.append(
            SuggestionCreate(
                project_id=project_id,
                chapter_id=chapter_id,
                block_id=block_id,
                start=seg.start,
                end=seg.end,
                category=SuggestionCategory.SPEAKER_GENDER,
                original=seg.text,
                proposed=gender_val,
                payload_json=json.dumps(payload, ensure_ascii=False),
                rationale=rationale,
                confidence=seg.gender_confidence or 0.0,
                detector=DetectorKind.HEURISTIC,
                status=SuggestionStatus.PENDING,
                base_revision=base_revision,
            )
        )
    return suggestions
