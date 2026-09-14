# SPDX-License-Identifier: Apache-2.0
"""Praelector text processing, normalisation, and suggestion pipeline."""

from __future__ import annotations

from praelector.text.acronyms import AcronymMatch, detect_acronyms, spell_acronym_pl
from praelector.text.dialogue import (
    DialogueSegment,
    DialogueSplitResult,
    detect_dialogue_suggestions,
    split_dialogue,
)
from praelector.text.foreign import ForeignMatch, approximate_polish_phonetics, detect_foreign_words
from praelector.text.gender import (
    GIVEN_NAMES,
    MALE_A_EXCEPTIONS,
    ChapterSpeakerMap,
    GenderSignalResult,
    GivenNamesLexicon,
    generate_gender_suggestions,
    resolve_segment_gender,
    resolve_speaker_gender,
)
from praelector.text.lexicon import LexiconMatch, LexiconMatcher
from praelector.text.normalise import ArtifactMatch, NormaliseResult, normalise_text
from praelector.text.numerals_pl import (
    NumeralMatch,
    cardinal_nominative,
    decimal_to_words,
    detect_numerals,
    ordinal_nominative,
    roman_to_int,
    roman_to_words,
    time_to_words,
    year_to_words,
)
from praelector.text.pipeline import DeterministicPrepassPipeline
from praelector.text.segmentation import (
    PysbdSentenceSegmenter,
    RegexSentenceSegmenter,
    SentenceSegment,
    SentenceSegmenter,
)
from praelector.text.skip_detector import SkipMatch, detect_skip_candidates
from praelector.text.toponyms import ToponymMatch, detect_toponyms

__all__ = [
    "AcronymMatch",
    "ArtifactMatch",
    "ChapterSpeakerMap",
    "DeterministicPrepassPipeline",
    "DialogueSegment",
    "DialogueSplitResult",
    "ForeignMatch",
    "GIVEN_NAMES",
    "GenderSignalResult",
    "GivenNamesLexicon",
    "LexiconMatch",
    "LexiconMatcher",
    "MALE_A_EXCEPTIONS",
    "NormaliseResult",
    "NumeralMatch",
    "PysbdSentenceSegmenter",
    "RegexSentenceSegmenter",
    "SentenceSegment",
    "SentenceSegmenter",
    "SkipMatch",
    "ToponymMatch",
    "approximate_polish_phonetics",
    "cardinal_nominative",
    "decimal_to_words",
    "detect_acronyms",
    "detect_dialogue_suggestions",
    "detect_foreign_words",
    "detect_numerals",
    "detect_skip_candidates",
    "detect_toponyms",
    "generate_gender_suggestions",
    "normalise_text",
    "ordinal_nominative",
    "resolve_segment_gender",
    "resolve_speaker_gender",
    "roman_to_int",
    "roman_to_words",
    "spell_acronym_pl",
    "split_dialogue",
    "time_to_words",
    "year_to_words",
]
