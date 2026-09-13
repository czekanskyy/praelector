# SPDX-License-Identifier: Apache-2.0
"""Chapter, Block, and Span repository for SQLite storage (ED-01..ED-09, EB-05, EB-08)."""

from __future__ import annotations

import difflib
import re
import time
from typing import Any

from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.orm import Session

from praelector.domain.enums import (
    BlockKind,
    Gender,
    GenderDetector,
    SourceFormat,
    SpanKind,
    SpanOrigin,
)
from praelector.domain.ids import generate_id
from praelector.domain.models import (
    BlockResponse,
    ChapterResponse,
    ChapterTextResponse,
    ReplacePreview,
    ReplaceResponse,
    SearchHit,
    SearchResponse,
    SpanCreate,
    SpanResponse,
    SpanUpdate,
)
from praelector.ebook.blocks import normalize_block_text
from praelector.ebook.epub_read import ExtractedEpub
from praelector.ebook.frontmatter import detect_skip_candidates
from praelector.errors import AppError
from praelector.store.schema import (
    block_table,
    chapter_table,
    project_table,
    revision_table,
    span_table,
)

# Average speech reading speed: ~14 characters per second in Polish
CHARS_PER_SECOND = 14.0


class ChapterRepository:
    """Data access layer for Chapter, Block, and Span entities in project.db."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # ---------------------------------------------------------------------------
    # Ingest Storage
    # ---------------------------------------------------------------------------

    def insert_ingest_data(
        self,
        project_id: str,
        extracted_epub: ExtractedEpub,
        source_format: SourceFormat,
        source_original_rel: str,
        working_epub_rel: str,
        converter: str | None = None,
        session: Session | None = None,
    ) -> None:
        """Insert extracted ebook chapters, blocks, and initial frontmatter skip spans."""

        def _do(s: Session) -> None:
            # 1. Update Project record
            s.execute(
                update(project_table)
                .where(project_table.c.id == project_id)
                .values(
                    name=extracted_epub.title or "Untitled Project",
                    source_format=source_format.value,
                    source_original_rel=source_original_rel,
                    working_epub_rel=working_epub_rel,
                    converter=converter,
                    book_language=extracted_epub.language,
                    updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                )
            )

            # 2. Insert Chapters, Blocks, and Spans
            total_chapters = len(extracted_epub.chapters)
            for ch_idx, ch in enumerate(extracted_epub.chapters):
                s.execute(
                    chapter_table.insert().values(
                        id=ch.id,
                        project_id=project_id,
                        ordinal=ch.ordinal,
                        title=ch.title,
                        included=1,
                        source_href=ch.source_href,
                        spine_index=ch.spine_index,
                        char_count=ch.char_count,
                    )
                )

                # Insert blocks
                for blk in ch.blocks:
                    s.execute(
                        block_table.insert().values(
                            id=blk.id,
                            version_id=generate_id("blk"),
                            chapter_id=ch.id,
                            ordinal=blk.ordinal,
                            kind=blk.kind.value,
                            heading_level=blk.heading_level,
                            text=blk.text,
                            source_ref_json=blk.source_ref_json,
                            valid_from_revision=0,
                            valid_to_revision=None,
                        )
                    )

                # Heuristic skip-span detection (EB-08)
                skip_candidates = detect_skip_candidates(
                    ch.blocks,
                    chapter_title=ch.title,
                    is_first_chapter=(ch_idx == 0),
                    is_last_chapter=(ch_idx == total_chapters - 1),
                )
                for cand in skip_candidates:
                    s.execute(
                        span_table.insert().values(
                            id=generate_id("spn"),
                            version_id=generate_id("spn"),
                            block_id=cand.block_id,
                            start=cand.start,
                            end=cand.end,
                            kind=SpanKind.SKIP.value,
                            origin=SpanOrigin.HEURISTIC.value,
                            orphaned=0,
                            valid_from_revision=0,
                            valid_to_revision=None,
                        )
                    )

        if session is not None:
            _do(session)
        else:
            with Session(self.engine) as s:
                _do(s)
                s.commit()

    # ---------------------------------------------------------------------------
    # Chapter CRUD & Operations
    # ---------------------------------------------------------------------------

    def list_chapters(
        self, project_id: str, session: Session | None = None
    ) -> list[ChapterResponse]:
        """List all chapters for a project in ordinal order."""

        def _do(s: Session) -> list[ChapterResponse]:
            stmt = (
                select(
                    chapter_table.c.id,
                    chapter_table.c.ordinal,
                    chapter_table.c.title,
                    chapter_table.c.included,
                    chapter_table.c.char_count,
                    func.count(block_table.c.id).label("block_count"),
                )
                .outerjoin(
                    block_table,
                    (block_table.c.chapter_id == chapter_table.c.id)
                    & (block_table.c.valid_to_revision.is_(None)),
                )
                .where(chapter_table.c.project_id == project_id)
                .group_by(
                    chapter_table.c.id,
                    chapter_table.c.ordinal,
                    chapter_table.c.title,
                    chapter_table.c.included,
                    chapter_table.c.char_count,
                )
                .order_by(chapter_table.c.ordinal.asc())
            )
            rows = s.execute(stmt).all()
            return [
                ChapterResponse(
                    id=row.id,
                    ordinal=row.ordinal,
                    title=row.title,
                    included=bool(row.included),
                    block_count=row.block_count,
                    char_count=row.char_count,
                    est_audio_s=round(row.char_count / CHARS_PER_SECOND, 1),
                )
                for row in rows
            ]

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            return _do(s)

    def get_chapter(
        self, chapter_id: str, session: Session | None = None
    ) -> ChapterResponse | None:
        """Fetch a single chapter by ID."""

        def _do(s: Session) -> ChapterResponse | None:
            stmt = (
                select(
                    chapter_table.c.id,
                    chapter_table.c.ordinal,
                    chapter_table.c.title,
                    chapter_table.c.included,
                    chapter_table.c.char_count,
                    func.count(block_table.c.id).label("block_count"),
                )
                .outerjoin(
                    block_table,
                    (block_table.c.chapter_id == chapter_table.c.id)
                    & (block_table.c.valid_to_revision.is_(None)),
                )
                .where(chapter_table.c.id == chapter_id)
                .group_by(
                    chapter_table.c.id,
                    chapter_table.c.ordinal,
                    chapter_table.c.title,
                    chapter_table.c.included,
                    chapter_table.c.char_count,
                )
            )
            row = s.execute(stmt).first()
            if not row:
                return None
            return ChapterResponse(
                id=row.id,
                ordinal=row.ordinal,
                title=row.title,
                included=bool(row.included),
                block_count=row.block_count,
                char_count=row.char_count,
                est_audio_s=round(row.char_count / CHARS_PER_SECOND, 1),
            )

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            return _do(s)

    def update_chapter(
        self,
        chapter_id: str,
        title: str | None = None,
        included: bool | None = None,
        session: Session | None = None,
    ) -> ChapterResponse:
        """Update chapter title or included status."""

        def _do(s: Session) -> ChapterResponse:
            values: dict[str, Any] = {}
            if title is not None:
                values["title"] = title
            if included is not None:
                values["included"] = 1 if included else 0

            if values:
                s.execute(
                    update(chapter_table).where(chapter_table.c.id == chapter_id).values(**values)
                )

            res = self.get_chapter(chapter_id, session=s)
            if not res:
                raise AppError(
                    "internal.not_found",
                    status_code=404,
                    detail={"chapter_id": chapter_id},
                )
            return res

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            res = _do(s)
            s.commit()
            return res

    def reorder_chapters(
        self, project_id: str, order: list[str], session: Session | None = None
    ) -> list[ChapterResponse]:
        """Update chapter sequence by given ID list."""

        def _do(s: Session) -> list[ChapterResponse]:
            # Use negative ordinals first to avoid unique constraint collisions
            for idx, cid in enumerate(order, start=1):
                s.execute(
                    update(chapter_table)
                    .where((chapter_table.c.id == cid) & (chapter_table.c.project_id == project_id))
                    .values(ordinal=-idx)
                )
            for idx, cid in enumerate(order, start=1):
                s.execute(
                    update(chapter_table)
                    .where((chapter_table.c.id == cid) & (chapter_table.c.project_id == project_id))
                    .values(ordinal=idx)
                )
            return self.list_chapters(project_id, session=s)

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            res = _do(s)
            s.commit()
            return res

    # ---------------------------------------------------------------------------
    # Blocks and Spans Queries
    # ---------------------------------------------------------------------------

    def get_blocks(
        self, chapter_id: str, revision: int, session: Session | None = None
    ) -> list[BlockResponse]:
        """Get blocks for a chapter valid at a given revision."""

        def _do(s: Session) -> list[BlockResponse]:
            stmt = (
                select(block_table)
                .where(
                    (block_table.c.chapter_id == chapter_id)
                    & (block_table.c.valid_from_revision <= revision)
                    & (
                        block_table.c.valid_to_revision.is_(None)
                        | (block_table.c.valid_to_revision > revision)
                    )
                )
                .order_by(block_table.c.ordinal.asc())
            )
            rows = s.execute(stmt).mappings().all()
            return [
                BlockResponse(
                    id=r["id"],
                    ordinal=r["ordinal"],
                    kind=BlockKind(r["kind"]),
                    heading_level=r["heading_level"],
                    text=r["text"],
                    source_ref_json=r["source_ref_json"],
                )
                for r in rows
            ]

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            return _do(s)

    def get_spans(
        self, chapter_id: str, revision: int, session: Session | None = None
    ) -> list[SpanResponse]:
        """Get all spans valid at a given revision for blocks in a chapter."""

        def _do(s: Session) -> list[SpanResponse]:
            current_blocks = (
                select(block_table.c.id)
                .where(
                    (block_table.c.chapter_id == chapter_id)
                    & (block_table.c.valid_from_revision <= revision)
                    & (
                        block_table.c.valid_to_revision.is_(None)
                        | (block_table.c.valid_to_revision > revision)
                    )
                )
                .scalar_subquery()
            )

            stmt = (
                select(span_table)
                .where(
                    span_table.c.block_id.in_(current_blocks)
                    & (span_table.c.valid_from_revision <= revision)
                    & (
                        span_table.c.valid_to_revision.is_(None)
                        | (span_table.c.valid_to_revision > revision)
                    )
                )
                .order_by(span_table.c.start.asc())
            )
            rows = s.execute(stmt).mappings().all()
            return [
                SpanResponse(
                    id=r["id"],
                    block_id=r["block_id"],
                    start=r["start"],
                    end=r["end"],
                    kind=SpanKind(r["kind"]),
                    gender=Gender(r["gender"]) if r["gender"] else None,
                    gender_confidence=r["gender_confidence"],
                    gender_detector=GenderDetector(r["gender_detector"])
                    if r["gender_detector"]
                    else None,
                    speaker_id=r["speaker_id"],
                    spoken=r["spoken"],
                    pause_ms=r["pause_ms"],
                    origin=SpanOrigin(r["origin"]),
                    orphaned=bool(r["orphaned"]),
                )
                for r in rows
            ]

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            return _do(s)

    # ---------------------------------------------------------------------------
    # Chapter Text (Display & Spoken) (ED-02, ED-06)
    # ---------------------------------------------------------------------------

    def get_chapter_text(
        self, chapter_id: str, revision: int, view: str = "display", session: Session | None = None
    ) -> ChapterTextResponse:
        """Fetch full chapter text for display or spoken preview."""
        blocks = self.get_blocks(chapter_id, revision, session=session)
        if view == "display":
            joined_text = "\n\n".join(b.text for b in blocks)
            return ChapterTextResponse(view="display", blocks=blocks, text=joined_text)

        # Spoken view (evaluates spans: skip drops text, pronunciation replaces with spoken)
        spans = self.get_spans(chapter_id, revision, session=session)
        spans_by_block: dict[str, list[SpanResponse]] = {}
        for sp in spans:
            spans_by_block.setdefault(sp.block_id, []).append(sp)

        spoken_blocks: list[BlockResponse] = []
        for blk in blocks:
            b_spans = spans_by_block.get(blk.id, [])
            if not b_spans:
                spoken_blocks.append(blk)
                continue

            # Sort spans descending by start to replace non-destructively
            sorted_spans = sorted(b_spans, key=lambda s: s.start, reverse=True)
            text_chars = list(blk.text)
            for sp in sorted_spans:
                if sp.kind == SpanKind.SKIP:
                    text_chars[sp.start : sp.end] = []
                elif sp.kind == SpanKind.PRONUNCIATION and sp.spoken:
                    text_chars[sp.start : sp.end] = list(sp.spoken)

            spoken_text = normalize_block_text("".join(text_chars))
            if spoken_text:
                spoken_blocks.append(
                    BlockResponse(
                        id=blk.id,
                        ordinal=blk.ordinal,
                        kind=blk.kind,
                        heading_level=blk.heading_level,
                        text=spoken_text,
                        source_ref_json=blk.source_ref_json,
                    )
                )

        joined_spoken = "\n\n".join(b.text for b in spoken_blocks)
        return ChapterTextResponse(view="spoken", blocks=spoken_blocks, text=joined_spoken)

    # ---------------------------------------------------------------------------
    # Chapter Text Update & Block Re-association (ED-02, ED-07, DATA_MODEL §4)
    # ---------------------------------------------------------------------------

    def update_chapter_text(
        self,
        project_id: str,
        chapter_id: str,
        text: str,
        base_revision: int,
        session: Session | None = None,
    ) -> tuple[int, list[str]]:
        """Update chapter plain text, re-associating blocks and re-mapping spans."""

        def _do(s: Session) -> tuple[int, list[str]]:
            # 1. Bump project revision
            new_rev = base_revision + 1
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            s.execute(
                revision_table.insert().values(
                    n=new_rev,
                    created_at=now_iso,
                    label=f"Edit text for chapter {chapter_id}",
                    reverted=0,
                )
            )
            s.execute(
                update(project_table)
                .where(project_table.c.id == project_id)
                .values(current_revision=new_rev, updated_at=now_iso)
            )

            # 2. Split candidate paragraphs
            candidate_texts = [
                normalize_block_text(p)
                for p in re.split(r"\n\s*\n+", text.strip())
                if normalize_block_text(p)
            ]

            # 3. Fetch existing blocks and spans at base_revision
            existing_blocks = self.get_blocks(chapter_id, base_revision, session=s)
            existing_spans = self.get_spans(chapter_id, base_revision, session=s)
            spans_by_block: dict[str, list[SpanResponse]] = {}
            for sp in existing_spans:
                spans_by_block.setdefault(sp.block_id, []).append(sp)

            orphaned_span_ids: list[str] = []

            # 4. Match candidates with existing blocks using SequenceMatcher
            used_old_ids: set[str] = set()
            new_blocks_to_insert: list[dict[str, Any]] = []
            new_spans_to_insert: list[dict[str, Any]] = []

            for cand_idx, cand_text in enumerate(candidate_texts):
                best_ratio = 0.0
                best_old_block: BlockResponse | None = None

                for old_blk in existing_blocks:
                    if old_blk.id in used_old_ids:
                        continue
                    ratio = difflib.SequenceMatcher(None, old_blk.text, cand_text).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_old_block = old_blk

                if best_ratio >= 0.6 and best_old_block is not None:
                    # Reuse logical block ID
                    block_id = best_old_block.id
                    used_old_ids.add(block_id)
                    kind = best_old_block.kind
                    heading_level = best_old_block.heading_level

                    # Remap spans
                    matcher = difflib.SequenceMatcher(None, best_old_block.text, cand_text)
                    for old_span in spans_by_block.get(block_id, []):
                        # Find new bounds
                        remapped_start: int | None = None
                        remapped_end: int | None = None
                        span_damaged = False

                        for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
                            if tag == "equal":
                                if i1 <= old_span.start < i2:
                                    remapped_start = j1 + (old_span.start - i1)
                                if i1 < old_span.end <= i2:
                                    remapped_end = j1 + (old_span.end - i1)
                            elif tag in ("replace", "delete") and max(i1, old_span.start) < min(
                                i2, old_span.end
                            ):
                                span_damaged = True

                        if span_damaged or remapped_start is None or remapped_end is None:
                            orphaned_span_ids.append(old_span.id)
                            # Close span
                            s.execute(
                                update(span_table)
                                .where(
                                    (span_table.c.id == old_span.id)
                                    & (span_table.c.valid_to_revision.is_(None))
                                )
                                .values(valid_to_revision=new_rev, orphaned=1)
                            )
                        else:
                            # Reinsert span with updated offsets
                            new_spans_to_insert.append(
                                {
                                    "id": old_span.id,
                                    "version_id": generate_id("spn"),
                                    "block_id": block_id,
                                    "start": remapped_start,
                                    "end": remapped_end,
                                    "kind": old_span.kind.value,
                                    "gender": old_span.gender.value if old_span.gender else None,
                                    "gender_confidence": old_span.gender_confidence,
                                    "gender_detector": old_span.gender_detector.value
                                    if old_span.gender_detector
                                    else None,
                                    "speaker_id": old_span.speaker_id,
                                    "spoken": old_span.spoken,
                                    "pause_ms": old_span.pause_ms,
                                    "origin": old_span.origin.value,
                                    "orphaned": 0,
                                    "valid_from_revision": new_rev,
                                    "valid_to_revision": None,
                                }
                            )
                else:
                    # Mint fresh block ID
                    block_id = generate_id("blk")
                    kind = BlockKind.PARAGRAPH
                    heading_level = None

                new_blocks_to_insert.append(
                    {
                        "id": block_id,
                        "version_id": generate_id("blk"),
                        "chapter_id": chapter_id,
                        "ordinal": cand_idx,
                        "kind": kind.value,
                        "heading_level": heading_level,
                        "text": cand_text,
                        "source_ref_json": None,
                        "valid_from_revision": new_rev,
                        "valid_to_revision": None,
                    }
                )

            # 5. Close old block and span versions
            s.execute(
                update(block_table)
                .where(
                    (block_table.c.chapter_id == chapter_id)
                    & (block_table.c.valid_to_revision.is_(None))
                )
                .values(valid_to_revision=new_rev)
            )

            current_block_ids = [b["id"] for b in new_blocks_to_insert]
            s.execute(
                update(span_table)
                .where(
                    span_table.c.block_id.in_(current_block_ids)
                    & span_table.c.valid_to_revision.is_(None)
                )
                .values(valid_to_revision=new_rev)
            )

            # 6. Insert new block and span versions
            for b_vals in new_blocks_to_insert:
                s.execute(block_table.insert().values(**b_vals))
            for sp_vals in new_spans_to_insert:
                s.execute(span_table.insert().values(**sp_vals))

            # 7. Refresh chapter character count
            total_chars = sum(len(b["text"]) for b in new_blocks_to_insert)
            s.execute(
                update(chapter_table)
                .where(chapter_table.c.id == chapter_id)
                .values(char_count=total_chars)
            )

            return new_rev, orphaned_span_ids

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            res = _do(s)
            s.commit()
            return res

    # ---------------------------------------------------------------------------
    # Chapter Split & Merge (ED-01)
    # ---------------------------------------------------------------------------

    def split_chapter(
        self,
        project_id: str,
        chapter_id: str,
        block_id: str,
        offset: int = 0,
        session: Session | None = None,
    ) -> tuple[ChapterResponse, ChapterResponse]:
        """Split a chapter at a given block and offset."""

        def _do(s: Session) -> tuple[ChapterResponse, ChapterResponse]:
            orig_ch = self.get_chapter(chapter_id, session=s)
            if not orig_ch:
                raise AppError(
                    "internal.not_found", status_code=404, detail={"chapter_id": chapter_id}
                )

            # Find split block
            stmt = (
                select(block_table)
                .where(
                    (block_table.c.chapter_id == chapter_id)
                    & (block_table.c.valid_to_revision.is_(None))
                )
                .order_by(block_table.c.ordinal.asc())
            )
            all_blocks = s.execute(stmt).mappings().all()

            split_idx = next(
                (i for i, b in enumerate(all_blocks) if b["id"] == block_id),
                None,
            )
            if split_idx is None:
                raise AppError("internal.not_found", status_code=404, detail={"block_id": block_id})

            # Create new chapter at ordinal + 1
            new_ch_id = generate_id("chp")
            new_ordinal = orig_ch.ordinal + 1

            # Shift subsequent chapter ordinals safely without unique constraint collision
            subsequent = s.execute(
                select(chapter_table.c.id, chapter_table.c.ordinal)
                .where(
                    (chapter_table.c.project_id == project_id)
                    & (chapter_table.c.ordinal >= new_ordinal)
                )
                .order_by(chapter_table.c.ordinal.desc())
            ).all()

            for sid, sord in subsequent:
                s.execute(
                    update(chapter_table).where(chapter_table.c.id == sid).values(ordinal=-sord)
                )

            for sid, sord in subsequent:
                s.execute(
                    update(chapter_table).where(chapter_table.c.id == sid).values(ordinal=sord + 1)
                )

            s.execute(
                chapter_table.insert().values(
                    id=new_ch_id,
                    project_id=project_id,
                    ordinal=new_ordinal,
                    title=f"{orig_ch.title} (Part 2)",
                    included=1 if orig_ch.included else 0,
                    source_href=None,
                    spine_index=None,
                    char_count=0,
                )
            )

            # Re-parent blocks from split_idx onwards, splitting target block if offset > 0
            target_blk = all_blocks[split_idx]
            target_text = target_blk["text"]

            if 0 < offset < len(target_text):
                first_text = normalize_block_text(target_text[:offset])
                second_text = normalize_block_text(target_text[offset:])

                # Update first block to keep the first text
                s.execute(
                    update(block_table)
                    .where(block_table.c.version_id == target_blk["version_id"])
                    .values(text=first_text)
                )

                # Insert second part as the first block of the new chapter
                s.execute(
                    block_table.insert().values(
                        id=generate_id("blk"),
                        version_id=generate_id("blk"),
                        chapter_id=new_ch_id,
                        ordinal=0,
                        kind=target_blk["kind"],
                        heading_level=target_blk["heading_level"],
                        text=second_text,
                        source_ref_json=target_blk["source_ref_json"],
                        valid_from_revision=target_blk["valid_from_revision"],
                        valid_to_revision=None,
                    )
                )

                blocks_to_move = all_blocks[split_idx + 1 :]
                start_ord = 1
            else:
                blocks_to_move = all_blocks[split_idx:]
                start_ord = 0

            for ord_offset, blk in enumerate(blocks_to_move):
                s.execute(
                    update(block_table)
                    .where(block_table.c.version_id == blk["version_id"])
                    .values(chapter_id=new_ch_id, ordinal=start_ord + ord_offset)
                )

            # Recompute char counts
            c1_chars = (
                s.scalar(
                    select(func.sum(func.length(block_table.c.text))).where(
                        (block_table.c.chapter_id == chapter_id)
                        & (block_table.c.valid_to_revision.is_(None))
                    )
                )
                or 0
            )
            c2_chars = (
                s.scalar(
                    select(func.sum(func.length(block_table.c.text))).where(
                        (block_table.c.chapter_id == new_ch_id)
                        & (block_table.c.valid_to_revision.is_(None))
                    )
                )
                or 0
            )

            s.execute(
                update(chapter_table)
                .where(chapter_table.c.id == chapter_id)
                .values(char_count=c1_chars)
            )
            s.execute(
                update(chapter_table)
                .where(chapter_table.c.id == new_ch_id)
                .values(char_count=c2_chars)
            )

            ch1 = self.get_chapter(chapter_id, session=s)
            ch2 = self.get_chapter(new_ch_id, session=s)
            assert ch1 is not None and ch2 is not None
            return ch1, ch2

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            res = _do(s)
            s.commit()
            return res

    def merge_chapters(
        self, project_id: str, chapter_ids: list[str], session: Session | None = None
    ) -> ChapterResponse:
        """Merge multiple chapters into the first chapter."""

        def _do(s: Session) -> ChapterResponse:
            if len(chapter_ids) < 2:
                raise AppError(
                    "internal.bad_request",
                    status_code=400,
                    detail={"message": "At least 2 chapters required to merge"},
                )

            target_id = chapter_ids[0]
            secondary_ids = chapter_ids[1:]

            target_ch = self.get_chapter(target_id, session=s)
            if not target_ch:
                raise AppError(
                    "internal.not_found", status_code=404, detail={"chapter_id": target_id}
                )

            # Find max ordinal in target chapter
            max_ord = s.scalar(
                select(func.max(block_table.c.ordinal)).where(
                    (block_table.c.chapter_id == target_id)
                    & (block_table.c.valid_to_revision.is_(None))
                )
            )
            curr_ord = (max_ord + 1) if max_ord is not None else 0

            # Move blocks from secondary chapters
            for sec_id in secondary_ids:
                sec_blocks = (
                    s.execute(
                        select(block_table)
                        .where(
                            (block_table.c.chapter_id == sec_id)
                            & (block_table.c.valid_to_revision.is_(None))
                        )
                        .order_by(block_table.c.ordinal.asc())
                    )
                    .mappings()
                    .all()
                )
                for blk in sec_blocks:
                    s.execute(
                        update(block_table)
                        .where(block_table.c.version_id == blk["version_id"])
                        .values(chapter_id=target_id, ordinal=curr_ord)
                    )
                    curr_ord += 1

                # Delete secondary chapter record
                s.execute(delete(chapter_table).where(chapter_table.c.id == sec_id))

            # Recalculate target chapter char count
            new_chars = (
                s.scalar(
                    select(func.sum(func.length(block_table.c.text))).where(
                        (block_table.c.chapter_id == target_id)
                        & (block_table.c.valid_to_revision.is_(None))
                    )
                )
                or 0
            )
            s.execute(
                update(chapter_table)
                .where(chapter_table.c.id == target_id)
                .values(char_count=new_chars)
            )

            # Recompact remaining chapter ordinals
            remaining = (
                s.execute(
                    select(chapter_table.c.id)
                    .where(chapter_table.c.project_id == project_id)
                    .order_by(chapter_table.c.ordinal.asc())
                )
                .scalars()
                .all()
            )
            for idx, cid in enumerate(remaining, start=1):
                s.execute(
                    update(chapter_table).where(chapter_table.c.id == cid).values(ordinal=idx)
                )

            res = self.get_chapter(target_id, session=s)
            assert res is not None
            return res

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            res = _do(s)
            s.commit()
            return res

    # ---------------------------------------------------------------------------
    # Span Management (ED-04, ED-09)
    # ---------------------------------------------------------------------------

    def create_span(
        self,
        payload: SpanCreate,
        current_revision: int,
        session: Session | None = None,
    ) -> SpanResponse:
        """Create a manual span annotation on a block."""

        def _do(s: Session) -> SpanResponse:
            span_id = generate_id("spn")
            version_id = generate_id("spn")

            s.execute(
                span_table.insert().values(
                    id=span_id,
                    version_id=version_id,
                    block_id=payload.block_id,
                    start=payload.start,
                    end=payload.end,
                    kind=payload.kind.value,
                    gender=payload.gender.value if payload.gender else None,
                    gender_confidence=1.0 if payload.gender else None,
                    gender_detector=GenderDetector.MANUAL.value if payload.gender else None,
                    speaker_id=payload.speaker_id,
                    spoken=payload.spoken,
                    pause_ms=payload.pause_ms,
                    origin=SpanOrigin.MANUAL.value,
                    orphaned=0,
                    valid_from_revision=current_revision,
                    valid_to_revision=None,
                )
            )

            return SpanResponse(
                id=span_id,
                block_id=payload.block_id,
                start=payload.start,
                end=payload.end,
                kind=payload.kind,
                gender=payload.gender,
                gender_confidence=1.0 if payload.gender else None,
                gender_detector=GenderDetector.MANUAL if payload.gender else None,
                speaker_id=payload.speaker_id,
                spoken=payload.spoken,
                pause_ms=payload.pause_ms,
                origin=SpanOrigin.MANUAL,
                orphaned=False,
            )

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            res = _do(s)
            s.commit()
            return res

    def update_span(
        self,
        span_id: str,
        payload: SpanUpdate,
        session: Session | None = None,
    ) -> SpanResponse:
        """Update fields of an active span."""

        def _do(s: Session) -> SpanResponse:
            values: dict[str, Any] = {}
            if payload.kind is not None:
                values["kind"] = payload.kind.value
            if payload.gender is not None:
                values["gender"] = payload.gender.value
            if payload.speaker_id is not None:
                values["speaker_id"] = payload.speaker_id
            if payload.spoken is not None:
                values["spoken"] = payload.spoken
            if payload.pause_ms is not None:
                values["pause_ms"] = payload.pause_ms

            if values:
                s.execute(
                    update(span_table)
                    .where((span_table.c.id == span_id) & span_table.c.valid_to_revision.is_(None))
                    .values(**values)
                )

            stmt = select(span_table).where(
                (span_table.c.id == span_id) & span_table.c.valid_to_revision.is_(None)
            )
            r = s.execute(stmt).mappings().first()
            if not r:
                raise AppError("internal.not_found", status_code=404, detail={"span_id": span_id})

            return SpanResponse(
                id=r["id"],
                block_id=r["block_id"],
                start=r["start"],
                end=r["end"],
                kind=SpanKind(r["kind"]),
                gender=Gender(r["gender"]) if r["gender"] else None,
                gender_confidence=r["gender_confidence"],
                gender_detector=GenderDetector(r["gender_detector"])
                if r["gender_detector"]
                else None,
                speaker_id=r["speaker_id"],
                spoken=r["spoken"],
                pause_ms=r["pause_ms"],
                origin=SpanOrigin(r["origin"]),
                orphaned=bool(r["orphaned"]),
            )

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            res = _do(s)
            s.commit()
            return res

    def delete_span(self, span_id: str, session: Session | None = None) -> None:
        """Soft delete a span by closing its revision or hard deleting if uncommitted."""

        def _do(s: Session) -> None:
            s.execute(delete(span_table).where(span_table.c.id == span_id))

        if session is not None:
            _do(session)
        else:
            with Session(self.engine) as s:
                _do(s)
                s.commit()

    # ---------------------------------------------------------------------------
    # Search and Replace (ED-05)
    # ---------------------------------------------------------------------------

    def search_text(
        self,
        project_id: str,
        query: str,
        regex: bool = False,
        case_sensitive: bool = False,
        scope: str = "book",
        chapter_id: str | None = None,
        session: Session | None = None,
    ) -> SearchResponse:
        """Search text across a chapter or entire book."""

        def _do(s: Session) -> SearchResponse:
            stmt = (
                select(
                    block_table.c.id.label("block_id"),
                    block_table.c.text,
                    chapter_table.c.id.label("chapter_id"),
                    chapter_table.c.title.label("chapter_title"),
                )
                .join(chapter_table, block_table.c.chapter_id == chapter_table.c.id)
                .where(
                    (chapter_table.c.project_id == project_id)
                    & block_table.c.valid_to_revision.is_(None)
                )
                .order_by(chapter_table.c.ordinal.asc(), block_table.c.ordinal.asc())
            )
            if scope == "chapter" and chapter_id:
                stmt = stmt.where(chapter_table.c.id == chapter_id)

            rows = s.execute(stmt).all()
            flags = 0 if case_sensitive else re.IGNORECASE

            try:
                pattern = re.compile(query if regex else re.escape(query), flags)
            except Exception as exc:
                raise AppError(
                    "internal.bad_request",
                    status_code=400,
                    detail={"message": f"Invalid regex pattern: {exc}"},
                ) from exc

            hits: list[SearchHit] = []
            for r in rows:
                for match in pattern.finditer(r.text):
                    start, end = match.span()
                    ctx_start = max(0, start - 30)
                    ctx_end = min(len(r.text), end + 30)
                    snippet = (
                        ("..." if ctx_start > 0 else "")
                        + r.text[ctx_start:ctx_end]
                        + ("..." if ctx_end < len(r.text) else "")
                    )

                    hits.append(
                        SearchHit(
                            chapter_id=r.chapter_id,
                            chapter_title=r.chapter_title,
                            block_id=r.block_id,
                            start=start,
                            end=end,
                            text_match=match.group(0),
                            context=snippet,
                        )
                    )

            return SearchResponse(count=len(hits), hits=hits)

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            return _do(s)

    def replace_text(
        self,
        project_id: str,
        query: str,
        replacement: str,
        regex: bool = False,
        case_sensitive: bool = False,
        scope: str = "book",
        chapter_id: str | None = None,
        dry_run: bool = True,
        session: Session | None = None,
    ) -> ReplaceResponse:
        """Find and replace text with dry-run support."""

        def _do(s: Session) -> ReplaceResponse:
            search_res = self.search_text(
                project_id,
                query,
                regex=regex,
                case_sensitive=case_sensitive,
                scope=scope,
                chapter_id=chapter_id,
                session=s,
            )

            if not search_res.hits:
                return ReplaceResponse(count=0, previews=[], revision=None)

            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(query if regex else re.escape(query), flags)

            # Group hits by block
            hits_by_chapter: dict[str, set[str]] = {}
            for h in search_res.hits:
                hits_by_chapter.setdefault(h.chapter_id, set()).add(h.block_id)

            previews: list[ReplacePreview] = []

            # Generate previews
            for ch_id, blk_ids in hits_by_chapter.items():
                stmt = select(block_table).where(
                    block_table.c.id.in_(blk_ids) & block_table.c.valid_to_revision.is_(None)
                )
                blocks = s.execute(stmt).mappings().all()
                for b in blocks:
                    orig_text = b["text"]
                    new_text = pattern.sub(replacement, orig_text)
                    previews.append(
                        ReplacePreview(
                            chapter_id=ch_id,
                            block_id=b["id"],
                            original=orig_text,
                            proposed=new_text,
                        )
                    )

            if dry_run:
                return ReplaceResponse(count=len(previews), previews=previews, revision=None)

            # Execute replacement as a new revision
            proj_stmt = select(project_table.c.current_revision).where(
                project_table.c.id == project_id
            )
            base_rev = s.scalar(proj_stmt) or 0
            new_rev = base_rev + 1
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            s.execute(
                revision_table.insert().values(
                    n=new_rev,
                    created_at=now_iso,
                    label=f"Replace '{query}' with '{replacement}' ({len(previews)} blocks)",
                    reverted=0,
                )
            )
            s.execute(
                update(project_table)
                .where(project_table.c.id == project_id)
                .values(current_revision=new_rev, updated_at=now_iso)
            )

            for prev in previews:
                # Close old version
                s.execute(
                    update(block_table)
                    .where(
                        (block_table.c.id == prev.block_id)
                        & block_table.c.valid_to_revision.is_(None)
                    )
                    .values(valid_to_revision=new_rev)
                )
                # Insert new version
                s.execute(
                    block_table.insert().values(
                        id=prev.block_id,
                        version_id=generate_id("blk"),
                        chapter_id=prev.chapter_id,
                        ordinal=0,  # Updated below
                        kind=BlockKind.PARAGRAPH.value,
                        heading_level=None,
                        text=prev.proposed,
                        source_ref_json=None,
                        valid_from_revision=new_rev,
                        valid_to_revision=None,
                    )
                )

            return ReplaceResponse(count=len(previews), previews=previews, revision=new_rev)

        if session is not None:
            return _do(session)
        with Session(self.engine) as s:
            res = _do(s)
            s.commit()
            return res
