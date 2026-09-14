# SPDX-License-Identifier: Apache-2.0
"""Preparation pipeline job running deterministic heuristics and LLM refinement (AI-01, AI-03, D-15)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from praelector.domain.enums import (
    DetectorKind,
    JobState,
    SuggestionCategory,
    SuggestionStatus,
    VoiceMode,
)
from praelector.domain.models import JobCounts, SuggestionCreate
from praelector.jobs.manager import JobManager
from praelector.llm.protocol import LlmMessage, LlmRole
from praelector.llm.router import LlmRouter, build_bounded_context
from praelector.store.project_manager import ProjectManager
from praelector.store.repositories.chapters import ChapterRepository
from praelector.store.repositories.lexicon import LexiconRepository
from praelector.store.repositories.suggestions import SuggestionRepository
from praelector.text.lexicon import LexiconMatcher
from praelector.text.pipeline import DeterministicPrepassPipeline

logger = logging.getLogger(__name__)


class PrepJob:
    """Two-phase preparation job executing deterministic linguistic pre-passes and LLM refinement."""

    def __init__(
        self,
        job_id: str,
        project_id: str,
        job_manager: JobManager,
        project_manager: ProjectManager,
        llm_router: LlmRouter | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.job_id = job_id
        self.project_id = project_id
        self.job_manager = job_manager
        self.project_manager = project_manager
        self.llm_router = llm_router
        self.options = options or {}

    def _is_cancelled(self) -> bool:
        job = self.job_manager.get_job(self.job_id, self.project_id)
        return job is not None and job.state == JobState.CANCELLED.value

    async def run(self) -> None:
        """Execute the two-phase pipeline with progress tracking and cancel checking."""
        engine = self.project_manager.get_project_engine(self.project_id)
        chapter_repo = ChapterRepository(engine)
        suggestion_repo = SuggestionRepository(engine)
        lexicon_repo = LexiconRepository(
            self.project_manager.settings_store.get_settings().config_dir,
            project_engine=engine,
        )

        project = self.project_manager.get_project(self.project_id)
        revision = project.current_revision
        voice_mode = (
            VoiceMode(project.voice_mode) if project.voice_mode else VoiceMode.NARRATOR_MALE_FEMALE
        )
        cloud_llm_enabled = project.cloud_llm_enabled

        counts = JobCounts()
        warnings: list[dict[str, Any]] = []

        try:
            if self._is_cancelled():
                logger.info("PrepJob %s cancelled before start", self.job_id)
                return

            # ------------------------------------------------------------------
            # Phase 1: Deterministic Heuristics (AI-01, AI-02)
            # ------------------------------------------------------------------
            self.job_manager.update_job(
                self.job_id,
                state=JobState.RUNNING.value,
                stage="heuristic",
            )

            all_chapters = chapter_repo.list_chapters(self.project_id)
            target_ids = self.options.get("chapter_ids")
            if target_ids:
                chapters = [c for c in all_chapters if c.id in target_ids]
            else:
                chapters = [c for c in all_chapters if c.included]

            # Collect total block count
            total_blocks = 0
            chapter_blocks_map: dict[str, list[Any]] = {}
            for ch in chapters:
                blocks = chapter_repo.get_blocks(ch.id, revision)
                chapter_blocks_map[ch.id] = blocks
                total_blocks += len(blocks)

            counts.chapters_total = len(chapters)
            counts.blocks_total = total_blocks
            self.job_manager.update_job(self.job_id, counts=counts)

            # Build lexicon matcher
            lexicon_entries = lexicon_repo.list_entries(self.project_id)
            pipeline = DeterministicPrepassPipeline(LexiconMatcher(project_entries=lexicon_entries))

            heuristic_suggestions: list[SuggestionCreate] = []

            for ch in chapters:
                if self._is_cancelled():
                    logger.info("PrepJob %s cancelled during Phase 1", self.job_id)
                    return

                blocks = chapter_blocks_map[ch.id]
                block_tuples = [(b.id, b.text) for b in blocks]
                block_results = pipeline.process_chapter_blocks(
                    blocks=block_tuples,
                    project_id=self.project_id,
                    chapter_id=ch.id,
                    base_revision=revision,
                    voice_mode=voice_mode,
                )

                ch_suggestions: list[SuggestionCreate] = []
                for b_sugs in block_results.values():
                    ch_suggestions.extend(b_sugs)

                if ch_suggestions:
                    suggestion_repo.create_many(ch_suggestions)
                    heuristic_suggestions.extend(ch_suggestions)
                    counts.suggestions_emitted += len(ch_suggestions)

                counts.blocks_done += len(blocks)
                counts.chapters_done += 1
                self.job_manager.update_job(self.job_id, counts=counts)
                await asyncio.sleep(0)  # Yield control to event loop

            # ------------------------------------------------------------------
            # Phase 2: LLM Refinement (AI-01, AI-03, D-15)
            # ------------------------------------------------------------------
            skip_llm = self.options.get("skip_llm", False)
            if not skip_llm and self.llm_router is not None:
                self.job_manager.update_job(self.job_id, stage="llm")

                # Build block context lookup: block_id -> (text, prev_text, next_text)
                block_context: dict[str, tuple[str, str | None, str | None]] = {}
                for ch in chapters:
                    blocks = chapter_blocks_map[ch.id]
                    for idx, b in enumerate(blocks):
                        prev_text = blocks[idx - 1].text if idx > 0 else None
                        next_text = blocks[idx + 1].text if idx + 1 < len(blocks) else None
                        block_context[b.id] = (b.text, prev_text, next_text)

                # Candidates for refinement: low confidence dialogue or gender, or foreign words
                refinement_items = [
                    s
                    for s in heuristic_suggestions
                    if (s.category == SuggestionCategory.DIALOGUE_SPLIT and s.confidence < 0.75)
                    or (s.category == SuggestionCategory.SPEAKER_GENDER and s.confidence < 0.70)
                    or (s.category == SuggestionCategory.FOREIGN_WORD)
                ]

                cloud_disabled_warned = False

                for item in refinement_items:
                    if self._is_cancelled():
                        logger.info("PrepJob %s cancelled during Phase 2", self.job_id)
                        return

                    target_text, prev_t, next_t = block_context.get(
                        item.block_id, (item.original, None, None)
                    )
                    bounded_ctx = build_bounded_context(
                        target_block=target_text,
                        prev_block=prev_t,
                        next_block=next_t,
                    )

                    if item.category in (
                        SuggestionCategory.DIALOGUE_SPLIT,
                        SuggestionCategory.SPEAKER_GENDER,
                    ):
                        task_key = "dialogue_hard"
                        messages = [
                            LlmMessage(
                                role=LlmRole.SYSTEM,
                                content=(
                                    "You are an expert editor for Polish audiobooks. Analyze dialogue lines "
                                    "and identify speaker turns and speaker genders ('male', 'female', or 'unknown'). "
                                    "Return structured JSON matching the requested schema."
                                ),
                            ),
                            LlmMessage(
                                role=LlmRole.USER,
                                content=(
                                    f"Context:\n{bounded_ctx}\n\n"
                                    f"Candidate: {item.original}\n"
                                    "Analyze whether this block contains dialogue, identify segments, and determine speaker gender."
                                ),
                            ),
                        ]
                    else:  # FOREIGN_WORD -> pronounce
                        task_key = "pronounce"
                        messages = [
                            LlmMessage(
                                role=LlmRole.SYSTEM,
                                content=(
                                    "You are a Polish phonetic respelling assistant for TTS. Provide an approximate "
                                    "Polish phonetic spelling for foreign tokens so a Polish text-to-speech voice can pronounce them naturally. "
                                    "Return structured JSON matching the requested schema."
                                ),
                            ),
                            LlmMessage(
                                role=LlmRole.USER,
                                content=(
                                    f"Context:\n{bounded_ctx}\n\n"
                                    f"Token: {item.original}\n"
                                    "Provide the Polish phonetic readout."
                                ),
                            ),
                        ]

                    res_dict, error_code = await self.llm_router.execute_task(
                        task_key=task_key,
                        messages=messages,
                        project_id=self.project_id,
                        cloud_llm_enabled=cloud_llm_enabled,
                    )

                    if error_code == "llm.cloud_disabled":
                        if not cloud_disabled_warned:
                            warnings.append(
                                {
                                    "code": "llm.cloud_disabled",
                                    "message": "Cloud LLM profile required but cloud_llm_enabled is off; skipped remaining cloud LLM tasks.",
                                }
                            )
                            self.job_manager.update_job(self.job_id, warnings=warnings)
                            cloud_disabled_warned = True
                        continue

                    if res_dict is not None:
                        # Successful LLM suggestion
                        proposed_val: str | None = None
                        if task_key == "pronounce":
                            items_out = res_dict.get("items", [])
                            if items_out and isinstance(items_out[0], dict):
                                proposed_val = items_out[0].get("spoken")
                        elif task_key == "dialogue_hard":
                            proposed_val = res_dict.get("rationale") or json.dumps(
                                res_dict.get("segments", [])
                            )

                        llm_sug = SuggestionCreate(
                            project_id=self.project_id,
                            chapter_id=item.chapter_id,
                            block_id=item.block_id,
                            start=item.start,
                            end=item.end,
                            category=item.category,
                            original=item.original,
                            proposed=proposed_val,
                            payload_json=json.dumps(res_dict),
                            rationale=res_dict.get("rationale"),
                            confidence=0.85,
                            detector=DetectorKind.LLM,
                            status=SuggestionStatus.PENDING,
                            base_revision=revision,
                        )
                        suggestion_repo.create_many([llm_sug])
                        counts.suggestions_emitted += 1
                    else:
                        # Failed LLM suggestion (AI-03, D-15)
                        failed_sug = SuggestionCreate(
                            project_id=self.project_id,
                            chapter_id=item.chapter_id,
                            block_id=item.block_id,
                            start=item.start,
                            end=item.end,
                            category=item.category,
                            original=item.original,
                            proposed=None,
                            payload_json=None,
                            rationale=None,
                            confidence=0.0,
                            detector=DetectorKind.LLM,
                            status=SuggestionStatus.FAILED,
                            error_code=error_code or "llm.invalid_json",
                            base_revision=revision,
                        )
                        suggestion_repo.create_many([failed_sug])
                        counts.suggestions_emitted += 1

                    self.job_manager.update_job(self.job_id, counts=counts)
                    await asyncio.sleep(0)

            if self._is_cancelled():
                logger.info("PrepJob %s cancelled before completion", self.job_id)
                return

            # Mark completed
            self.job_manager.update_job(
                self.job_id,
                state=JobState.DONE.value,
                stage="complete",
                counts=counts,
                warnings=warnings if warnings else None,
            )
            logger.info("PrepJob %s completed successfully", self.job_id)

        except asyncio.CancelledError:
            logger.info("PrepJob %s was cancelled", self.job_id)
            self.job_manager.cancel_job(self.job_id)
            raise
        except Exception as exc:
            logger.exception("PrepJob %s failed with exception: %s", self.job_id, exc)
            self.job_manager.update_job(
                self.job_id,
                state=JobState.FAILED.value,
                error=str(exc),
            )
            raise
