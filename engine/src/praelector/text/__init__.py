# SPDX-License-Identifier: Apache-2.0
"""Praelector text processing, normalisation, and suggestion pipeline."""

from __future__ import annotations

from praelector.text.acronyms import AcronymMatch, detect_acronyms, spell_acronym_pl
from praelector.text.foreign import ForeignMatch, approximate_polish_phonetics, detect_foreign_words
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
    "DeterministicPrepassPipeline",
    "ForeignMatch",
    "LexiconMatch",
    "LexiconMatcher",
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
    "detect_foreign_words",
    "detect_numerals",
    "detect_skip_candidates",
    "detect_toponyms",
    "normalise_text",
    "ordinal_nominative",
    "roman_to_int",
    "roman_to_words",
    "spell_acronym_pl",
    "time_to_words",
    "year_to_words",
]
