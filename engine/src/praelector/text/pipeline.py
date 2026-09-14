# SPDX-License-Identifier: Apache-2.0
"""Deterministic heuristic pre-pass pipeline (AI-02, AI-08, AI-09).

Coordinates normalisation, artifact detection, skip candidate detection,
Polish numeral/ordinal expansion, acronym readout, toponym and foreign word
recognition, and user lexicon application without mutating underlying blocks.
"""

from __future__ import annotations

from praelector.domain.enums import DetectorKind, SuggestionCategory, SuggestionStatus, VoiceMode
from praelector.domain.models import SuggestionCreate
from praelector.text.acronyms import detect_acronyms
from praelector.text.dialogue import detect_dialogue_suggestions
from praelector.text.foreign import detect_foreign_words
from praelector.text.gender import (
    ChapterSpeakerMap,
    generate_gender_suggestions,
    resolve_speaker_gender,
)
from praelector.text.lexicon import LexiconMatcher
from praelector.text.normalise import normalise_text
from praelector.text.numerals_pl import detect_numerals
from praelector.text.skip_detector import detect_skip_candidates
from praelector.text.toponyms import detect_toponyms


class DeterministicPrepassPipeline:
    """Executes deterministic linguistic pre-passes on book text blocks."""

    def __init__(self, lexicon_matcher: LexiconMatcher | None = None) -> None:
        self.lexicon_matcher = lexicon_matcher or LexiconMatcher()

    def process_block(
        self,
        text: str,
        project_id: str,
        chapter_id: str,
        block_id: str,
        base_revision: int = 0,
        chapter_speaker_map: ChapterSpeakerMap | None = None,
        adjacent_context: str | None = None,
        voice_mode: VoiceMode = VoiceMode.NARRATOR_MALE_FEMALE,
    ) -> list[SuggestionCreate]:
        """Run all deterministic detectors on a block and return suggestions.

        Preserves block immutability (Principle 1): outputs suggestions only.
        """
        suggestions: list[SuggestionCreate] = []
        occupied_spans: list[tuple[int, int]] = []

        def _overlaps(s: int, e: int) -> bool:
            return any(max(s, os) < min(e, oe) for os, oe in occupied_spans)

        def _add(sug: SuggestionCreate) -> None:
            if not _overlaps(sug.start, sug.end):
                suggestions.append(sug)
                occupied_spans.append((sug.start, sug.end))

        # 1. Normalisation & conversion artifacts (NFC, double space, line-break hyphen, soft hyphen)
        norm_res = normalise_text(text)
        for art in norm_res.artifacts:
            _add(
                SuggestionCreate(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    block_id=block_id,
                    start=art.start,
                    end=art.end,
                    category=SuggestionCategory(art.category),
                    original=art.original,
                    proposed=art.proposed,
                    rationale=art.rationale,
                    confidence=art.confidence,
                    detector=DetectorKind.HEURISTIC,
                    status=SuggestionStatus.PENDING,
                    base_revision=base_revision,
                )
            )

        # 2. Skip candidates (ISBN, copyright, page numbers, imprint)
        skip_matches = detect_skip_candidates(text)
        for sm in skip_matches:
            # Note: If skip is for the entire block (e.g. ISBN line), it marks (0, len(text))
            # We don't block other fine-grained annotations unless it's a bare page number
            is_bare_page = sm.rationale == "Bare page number"
            suggestions.append(
                SuggestionCreate(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    block_id=block_id,
                    start=sm.start,
                    end=sm.end,
                    category=SuggestionCategory.CONVERSION_ARTIFACT
                    if is_bare_page
                    else SuggestionCategory.CONVERSION_ARTIFACT,  # Skip candidates map to skip span or conversion artifact
                    original=sm.original,
                    proposed=sm.proposed,
                    rationale=sm.rationale,
                    confidence=sm.confidence,
                    detector=DetectorKind.HEURISTIC,
                    status=SuggestionStatus.PENDING,
                    base_revision=base_revision,
                )
            )
            if is_bare_page:
                occupied_spans.append((sm.start, sm.end))
                return suggestions

        # 3. Dialogue segmentation & speaker gender (DG-01..DG-06)
        split_res, diag_sugs = detect_dialogue_suggestions(
            text=text,
            project_id=project_id,
            chapter_id=chapter_id,
            block_id=block_id,
            base_revision=base_revision,
        )
        for ds in diag_sugs:
            suggestions.append(ds)

        if split_res.has_dialogue:
            resolve_speaker_gender(
                segments=split_res.segments,
                block_text=text,
                chapter_speaker_map=chapter_speaker_map,
                adjacent_context=adjacent_context,
                voice_mode=voice_mode,
            )
            gender_sugs = generate_gender_suggestions(
                segments=split_res.segments,
                project_id=project_id,
                chapter_id=chapter_id,
                block_id=block_id,
                base_revision=base_revision,
            )
            for gs in gender_sugs:
                suggestions.append(gs)

        # 4. Lexicon dictionary hits (AI-09) - highest priority user rules
        lex_matches = self.lexicon_matcher.match(text)
        for lm in lex_matches:
            status = SuggestionStatus.ACCEPTED if lm.auto_apply else SuggestionStatus.PENDING
            _add(
                SuggestionCreate(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    block_id=block_id,
                    start=lm.start,
                    end=lm.end,
                    category=SuggestionCategory(lm.category),
                    original=lm.original,
                    proposed=lm.proposed,
                    rationale=lm.rationale,
                    confidence=lm.confidence,
                    detector=DetectorKind.DICT,
                    status=status,
                    base_revision=base_revision,
                )
            )

        # 4. Curated Toponyms (AI-02) - high priority geographic names (e.g. Washington DC)
        toponym_matches = detect_toponyms(text)
        for tm in toponym_matches:
            _add(
                SuggestionCreate(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    block_id=block_id,
                    start=tm.start,
                    end=tm.end,
                    category=SuggestionCategory.TOPONYM,
                    original=tm.original,
                    proposed=tm.proposed,
                    rationale=tm.rationale,
                    confidence=tm.confidence,
                    detector=DetectorKind.HEURISTIC,
                    status=SuggestionStatus.PENDING,
                    base_revision=base_revision,
                )
            )

        # 5. Numerals, ordinal headings, clock times, Roman numerals (D-11)
        num_matches = detect_numerals(text)
        for nm in num_matches:
            _add(
                SuggestionCreate(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    block_id=block_id,
                    start=nm.start,
                    end=nm.end,
                    category=SuggestionCategory(nm.category),
                    original=nm.original,
                    proposed=nm.proposed,
                    rationale=nm.rationale,
                    confidence=nm.confidence,
                    detector=DetectorKind.HEURISTIC,
                    status=SuggestionStatus.PENDING,
                    base_revision=base_revision,
                )
            )

        # 6. Acronyms (AI-02, AI-08) (e.g. IT -> aj ti)
        acronym_matches = detect_acronyms(text)
        for am in acronym_matches:
            _add(
                SuggestionCreate(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    block_id=block_id,
                    start=am.start,
                    end=am.end,
                    category=SuggestionCategory.ACRONYM,
                    original=am.original,
                    proposed=am.proposed,
                    rationale=am.rationale,
                    confidence=am.confidence,
                    detector=DetectorKind.HEURISTIC,
                    status=SuggestionStatus.PENDING,
                    base_revision=base_revision,
                )
            )

        # 7. Foreign tokens (AI-08, D-12) (e.g. Walker -> Łoker, Deadline -> Dedlajn)
        user_words = {e.pattern.lower() for e in self.lexicon_matcher.entries if not e.is_regex}
        foreign_matches = detect_foreign_words(text, user_lexicon_words=user_words)
        for fm in foreign_matches:
            _add(
                SuggestionCreate(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    block_id=block_id,
                    start=fm.start,
                    end=fm.end,
                    category=SuggestionCategory.FOREIGN_WORD,
                    original=fm.original,
                    proposed=fm.proposed,
                    rationale=fm.rationale,
                    confidence=fm.confidence,
                    detector=DetectorKind.HEURISTIC,
                    status=SuggestionStatus.PENDING,
                    base_revision=base_revision,
                )
            )

        # Sort all suggestions by start offset
        suggestions.sort(key=lambda s: s.start)
        return suggestions

    def process_chapter_blocks(
        self,
        blocks: list[tuple[str, str]],
        project_id: str,
        chapter_id: str,
        base_revision: int = 0,
        voice_mode: VoiceMode = VoiceMode.NARRATOR_MALE_FEMALE,
    ) -> dict[str, list[SuggestionCreate]]:
        """Process all blocks of a chapter sharing a single ChapterSpeakerMap (DG-04)."""
        chapter_speaker_map = ChapterSpeakerMap()
        results: dict[str, list[SuggestionCreate]] = {}
        for idx, (b_id, b_text) in enumerate(blocks):
            adj_parts: list[str] = []
            if idx > 0:
                adj_parts.append(blocks[idx - 1][1])
            if idx + 1 < len(blocks):
                adj_parts.append(blocks[idx + 1][1])
            adj_ctx = " ".join(adj_parts)

            results[b_id] = self.process_block(
                text=b_text,
                project_id=project_id,
                chapter_id=chapter_id,
                block_id=b_id,
                base_revision=base_revision,
                chapter_speaker_map=chapter_speaker_map,
                adjacent_context=adj_ctx,
                voice_mode=voice_mode,
            )
        return results
