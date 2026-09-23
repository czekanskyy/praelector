# SPDX-License-Identifier: Apache-2.0
"""Chapter tree, plain-text commits and find/replace (ED-01, ED-02, ED-05).

Blocks are stored as SCD-2 versions (DATA_MODEL.md §4). The row the editor sees
has ``valid_to_revision`` NULL. A text commit closes those rows and inserts the
next revision, reusing a block id when the text is still similar.

Reorder and rename touch the chapter row only. They do not write block text and
they do not bump ``current_revision``. Merge and split do, because block
ownership changed. A merged chapter keeps its row at a negative ordinal so the
closed block versions still have a foreign key.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from praelector.domain.enums import BlockKind, SourceFormat
from praelector.domain.ids import IdPrefix, new_id
from praelector.ebook import detect_format, read_epub, stage_epub
from praelector.ebook.blocks import SourceRef, extractable_characters
from praelector.ebook.epub_read import Book
from praelector.errors import AppError, ErrorCode
from praelector.store.db import session_scope
from praelector.store.manifest import utc_now, write_manifest
from praelector.store.projects import OpenProject
from praelector.store.tables import BlockRow, ChapterRow, ProjectRow, RevisionRow, to_db_time
from praelector.text.plain import associate_block_ids, join_plain_text, split_plain_text

logger = logging.getLogger(__name__)

#: Temporary ordinals during a reorder. Far below the negative tombstones merge
#: leaves behind, so the unique (project, ordinal) constraint can be updated in
#: two steps without a collision.
_TEMP_ORDINAL = -1_000_000


@dataclass(frozen=True, slots=True)
class StoredChapter:
    id: str
    ordinal: int
    title: str
    included: bool
    block_count: int
    char_count: int


@dataclass(frozen=True, slots=True)
class ChapterTree:
    revision: int
    chapters: tuple[StoredChapter, ...]


@dataclass(frozen=True, slots=True)
class StoredBlock:
    id: str
    ordinal: int
    kind: BlockKind
    text: str


@dataclass(frozen=True, slots=True)
class ChapterText:
    view: str
    revision: int
    text: str
    blocks: tuple[StoredBlock, ...]


@dataclass(frozen=True, slots=True)
class TextCommit:
    revision: int
    orphaned_span_ids: tuple[str, ...]
    text: str
    blocks: tuple[StoredBlock, ...]


@dataclass(frozen=True, slots=True)
class SplitResult:
    revision: int
    first: StoredChapter
    second: StoredChapter


@dataclass(frozen=True, slots=True)
class MergeResult:
    revision: int
    chapter: StoredChapter


@dataclass(frozen=True, slots=True)
class ReplaceHit:
    chapter_id: str
    block_id: str
    count: int


@dataclass(frozen=True, slots=True)
class ReplaceOutcome:
    count: int
    dry_run: bool
    revision: int | None
    preview: tuple[ReplaceHit, ...]


@dataclass(frozen=True, slots=True)
class IngestCommit:
    chapter_count: int
    block_count: int
    original_rel: str
    working_epub_rel: str
    revision: int


class ChapterStore:
    """Reads and writes the open project's chapter tree."""

    def __init__(self, project: OpenProject) -> None:
        self._project = project

    def commit_epub(self, source: Path) -> IngestCommit:
        """Copy ``source`` into the project and store its chapters.

        The path is only read. DRM and an empty spine come back as the ebook
        error codes from the reader. A project that already has lector edits
        (revision above the as-ingested 0) is not overwritten.
        """
        detected = detect_format(source)
        if detected.format is not SourceFormat.EPUB:
            raise AppError(
                ErrorCode.EBOOK_UNSUPPORTED_FORMAT,
                detail={"format": detected.format.value, "needs_conversion": True},
                message="ingest commit only accepts an epub",
            )
        book = read_epub(source)
        self._refuse_reingest_after_edits()
        original, working = stage_epub(source, self._project.layout.source, book)
        original_rel = self._project.layout.relative(original)
        working_rel = self._project.layout.relative(working)
        with self._session() as session:
            self._refuse_reingest_after_edits(session)
            self._clear_chapters(session)
            chapters, blocks = self._insert_book(session, book)
            project = self._project_row(session)
            project.source_format = SourceFormat.EPUB.value
            project.source_original_rel = original_rel
            project.working_epub_rel = working_rel
            project.converter = None
            project.book_language = book.language or None
            self._touch(session, project)
            revision = project.current_revision
        logger.info(
            "chapters ingested",
            extra={
                "project_id": self._project.id,
                "chapters": chapters,
                "blocks": blocks,
            },
        )
        return IngestCommit(
            chapter_count=chapters,
            block_count=blocks,
            original_rel=original_rel,
            working_epub_rel=working_rel,
            revision=revision,
        )

    def tree(self) -> ChapterTree:
        with self._session() as session:
            project = self._project_row(session)
            chapters = self._stored_many(session, self._active(session))
            return ChapterTree(revision=project.current_revision, chapters=tuple(chapters))

    def update(
        self,
        chapter_id: str,
        *,
        title: str | None = None,
        included: bool | None = None,
    ) -> StoredChapter:
        """Rename and include/exclude. Neither rewrites block text."""
        with self._session() as session:
            chapter = self._active_chapter(session, chapter_id)
            changed = False
            if title is not None:
                cleaned = title.strip()
                if not cleaned:
                    raise AppError(
                        ErrorCode.INTERNAL_VALIDATION_FAILED,
                        detail={"field": "title", "reason": "empty"},
                        message="a chapter title cannot be empty",
                    )
                if chapter.title != cleaned:
                    chapter.title = cleaned
                    changed = True
            if included is not None and chapter.included != included:
                chapter.included = included
                changed = True
            if changed:
                self._touch(session, self._project_row(session))
            stored = self._stored_many(session, [chapter])[0]
        return stored

    def reorder(self, order: Sequence[str]) -> ChapterTree:
        """Permutation of the live chapter ids. Block rows are not written."""
        with self._session() as session:
            rows = self._active(session)
            current = [row.id for row in rows]
            if len(order) != len(current) or sorted(order) != sorted(current):
                raise AppError(
                    ErrorCode.INTERNAL_VALIDATION_FAILED,
                    detail={"reason": "order"},
                    message="reorder must list each live chapter once",
                )
            if list(order) != current:
                by_id = {row.id: row for row in rows}
                self._write_ordinals(
                    session, [(by_id[chapter_id], index) for index, chapter_id in enumerate(order)]
                )
                self._touch(session, self._project_row(session))
            project = self._project_row(session)
            chapters = self._stored_many(session, self._active(session))
            return ChapterTree(revision=project.current_revision, chapters=tuple(chapters))

    def merge(self, ids: Sequence[str]) -> MergeResult:
        """Append the later of two adjacent chapters onto the earlier one."""
        if len(ids) != 2 or ids[0] == ids[1]:
            raise AppError(
                ErrorCode.INTERNAL_VALIDATION_FAILED,
                detail={"reason": "count"},
                message="merge takes exactly two chapters",
            )
        with self._session() as session:
            first = self._active_chapter(session, ids[0])
            second = self._active_chapter(session, ids[1])
            if abs(first.ordinal - second.ordinal) != 1:
                raise AppError(
                    ErrorCode.INTERNAL_VALIDATION_FAILED,
                    detail={"reason": "not_adjacent", "ids": [first.id, second.id]},
                    message="only adjacent chapters can be merged",
                )
            if second.ordinal < first.ordinal:
                first, second = second, first
            kept = self._current_blocks(session, first.id)
            moved = self._current_blocks(session, second.id)
            revision = self._bump(session, "merge chapters")
            self._reversion_blocks(
                session,
                moved,
                chapter_id=first.id,
                revision=revision,
                ordinal_start=len(kept),
            )
            old_ordinal = second.ordinal
            self._write_ordinals(session, [(second, self._next_tombstone(session))])
            self._shift_ordinals(session, start=old_ordinal + 1, delta=-1)
            self._refresh_char_count(session, first)
            second.char_count = 0
            stored = self._stored_many(session, [first])[0]
        return MergeResult(revision=revision, chapter=stored)

    def split(self, chapter_id: str, block_id: str, offset: int) -> SplitResult:
        """Split at a character offset inside one block.

        Offset 0 starts the new chapter at that block. Offset ``len(text)``
        starts it at the next block. Anything between splits the block's text;
        the left piece keeps the id.
        """
        with self._session() as session:
            chapter = self._active_chapter(session, chapter_id)
            blocks = self._current_blocks(session, chapter.id)
            index = next((pos for pos, block in enumerate(blocks) if block.id == block_id), None)
            if index is None:
                raise AppError(
                    ErrorCode.TEXT_BLOCK_NOT_FOUND,
                    detail={"chapter_id": chapter_id, "block_id": block_id},
                    message="block is not in this chapter",
                )
            block = blocks[index]
            if offset > len(block.text):
                raise AppError(
                    ErrorCode.TEXT_SPAN_OUT_OF_RANGE,
                    detail={"block_id": block_id, "offset": offset, "length": len(block.text)},
                    message="split offset is outside the block",
                )
            cut, left_text, right_text = _split_point(blocks, index, offset)
            # A boundary split with nothing on one side would empty a chapter.
            # Dividing the block's own text always leaves both pieces.
            boundary = left_text is None and right_text is None
            if boundary and (cut <= 0 or cut >= len(blocks)):
                raise AppError(
                    ErrorCode.INTERNAL_VALIDATION_FAILED,
                    detail={"reason": "empty_side", "block_id": block_id, "offset": offset},
                    message="a split must leave text on both sides",
                )
            revision = self._bump(session, "split chapter")
            if left_text is not None and right_text is not None:
                self._reversion_blocks(
                    session,
                    [block],
                    chapter_id=chapter.id,
                    revision=revision,
                    ordinal_start=block.ordinal,
                    texts=[left_text],
                )
                right_blocks = blocks[index + 1 :]
                head_kind = block.kind
                head_level = block.heading_level
                head_source = block.source_ref_json
            else:
                right_blocks = blocks[cut:]
                head_kind = None
                head_level = None
                head_source = None
            self._shift_ordinals(session, start=chapter.ordinal + 1, delta=1)
            title = _split_title(chapter.title, right_text, right_blocks, head_kind)
            created = ChapterRow(
                id=new_id(IdPrefix.CHAPTER),
                project_id=self._project.id,
                ordinal=chapter.ordinal + 1,
                title=title,
                included=chapter.included,
                source_href=chapter.source_href,
                spine_index=chapter.spine_index,
                char_count=0,
            )
            session.add(created)
            session.flush()
            ordinal = 0
            if right_text is not None:
                self._add_block(
                    session,
                    block_id=new_id(IdPrefix.BLOCK),
                    chapter_id=created.id,
                    ordinal=0,
                    kind=head_kind or BlockKind.PARAGRAPH.value,
                    heading_level=head_level,
                    text=right_text,
                    source_ref_json=head_source,
                    revision=revision,
                )
                ordinal = 1
            self._reversion_blocks(
                session,
                right_blocks,
                chapter_id=created.id,
                revision=revision,
                ordinal_start=ordinal,
            )
            self._refresh_char_count(session, chapter)
            self._refresh_char_count(session, created)
            first, second = self._stored_many(session, [chapter, created])
        return SplitResult(revision=revision, first=first, second=second)

    def text(self, chapter_id: str, view: str) -> ChapterText:
        """``display`` and ``spoken`` are the same text until spans exist (ED-06)."""
        with self._session() as session:
            chapter = self._active_chapter(session, chapter_id)
            project = self._project_row(session)
            blocks = tuple(
                _stored_block(block) for block in self._current_blocks(session, chapter.id)
            )
            return ChapterText(
                view=view,
                revision=project.current_revision,
                text=join_plain_text([block.text for block in blocks]),
                blocks=blocks,
            )

    def put_text(self, chapter_id: str, text: str, base_revision: int) -> TextCommit:
        pieces = split_plain_text(text)
        with self._session() as session:
            chapter = self._active_chapter(session, chapter_id)
            project = self._project_row(session)
            existing = self._current_blocks(session, chapter.id)
            if [block.text for block in existing] == pieces:
                blocks = tuple(_stored_block(block) for block in existing)
                return TextCommit(
                    revision=project.current_revision,
                    orphaned_span_ids=(),
                    text=join_plain_text(pieces),
                    blocks=blocks,
                )
            if project.current_revision != base_revision:
                raise AppError(
                    ErrorCode.TEXT_REVISION_CONFLICT,
                    detail={
                        "current_revision": project.current_revision,
                        "base_revision": base_revision,
                    },
                    message="chapter text was edited at a newer revision",
                )
            assigned = associate_block_ids(
                [(block.id, block.text) for block in existing],
                pieces,
            )
            by_id = {block.id: block for block in existing}
            revision = self._bump(session, "edit chapter")
            for block in existing:
                block.valid_to_revision = revision
            session.flush()
            stored: list[StoredBlock] = []
            for ordinal, (piece, block_id) in enumerate(zip(pieces, assigned, strict=True)):
                previous = by_id[block_id] if block_id is not None else None
                identity = block_id if block_id is not None else new_id(IdPrefix.BLOCK)
                kind = previous.kind if previous is not None else BlockKind.PARAGRAPH.value
                self._add_block(
                    session,
                    block_id=identity,
                    chapter_id=chapter.id,
                    ordinal=ordinal,
                    kind=kind,
                    heading_level=previous.heading_level if previous is not None else None,
                    text=piece,
                    source_ref_json=previous.source_ref_json if previous is not None else None,
                    revision=revision,
                )
                stored.append(
                    StoredBlock(id=identity, ordinal=ordinal, kind=BlockKind(kind), text=piece)
                )
            chapter.char_count = sum(extractable_characters(piece) for piece in pieces)
            logger.info(
                "chapter text committed",
                extra={"chapter_id": chapter.id, "revision": revision, "blocks": len(stored)},
            )
            return TextCommit(
                revision=revision,
                orphaned_span_ids=(),
                text=join_plain_text(pieces),
                blocks=tuple(stored),
            )

    def replace(
        self,
        *,
        query: str,
        replacement: str,
        dry_run: bool,
        chapter_id: str | None,
        all_chapters: bool,
    ) -> ReplaceOutcome:
        """Case-sensitive literal replace. One chapter, unless ``all_chapters``."""
        if not query:
            raise AppError(
                ErrorCode.INTERNAL_VALIDATION_FAILED,
                detail={"field": "query", "reason": "empty"},
                message="replace needs a query",
            )
        if not all_chapters and chapter_id is None:
            raise AppError(
                ErrorCode.INTERNAL_VALIDATION_FAILED,
                detail={"reason": "scope"},
                message="replace needs a chapter or all_chapters",
            )
        with self._session() as session:
            if all_chapters:
                chapters = self._active(session)
            else:
                assert chapter_id is not None
                chapters = [self._active_chapter(session, chapter_id)]
            hits: list[ReplaceHit] = []
            edits: list[tuple[BlockRow, str]] = []
            total = 0
            for chapter in chapters:
                for block in self._current_blocks(session, chapter.id):
                    count = block.text.count(query)
                    if count == 0:
                        continue
                    total += count
                    hits.append(ReplaceHit(chapter_id=chapter.id, block_id=block.id, count=count))
                    updated = block.text.replace(query, replacement)
                    if updated != block.text:
                        edits.append((block, updated))
            preview = tuple(hits[:50])
            if dry_run or not edits:
                return ReplaceOutcome(count=total, dry_run=dry_run, revision=None, preview=preview)
            revision = self._bump(session, "replace text")
            touched: set[str] = set()
            for block, updated in edits:
                touched.add(block.chapter_id)
                self._reversion_blocks(
                    session,
                    [block],
                    chapter_id=block.chapter_id,
                    revision=revision,
                    ordinal_start=block.ordinal,
                    texts=[updated],
                )
            by_id = {chapter.id: chapter for chapter in chapters}
            for chapter_id_touched in touched:
                self._refresh_char_count(session, by_id[chapter_id_touched])
            return ReplaceOutcome(count=total, dry_run=False, revision=revision, preview=preview)

    def _refuse_reingest_after_edits(self, session: Session | None = None) -> None:
        def check(active: Session) -> None:
            project = self._project_row(active)
            has_chapters = (
                active.scalar(
                    select(func.count())
                    .select_from(ChapterRow)
                    .where(ChapterRow.project_id == self._project.id)
                )
                or 0
            )
            if has_chapters and project.current_revision != 0:
                raise AppError(
                    ErrorCode.TEXT_REVISION_CONFLICT,
                    detail={"current_revision": project.current_revision},
                    message="refusing to replace chapters after they were edited",
                )

        if session is not None:
            check(session)
            return
        with self._session() as opened:
            check(opened)

    def _clear_chapters(self, session: Session) -> None:
        chapter_ids = list(
            session.scalars(select(ChapterRow.id).where(ChapterRow.project_id == self._project.id))
        )
        if not chapter_ids:
            return
        session.execute(delete(BlockRow).where(BlockRow.chapter_id.in_(chapter_ids)))
        session.execute(delete(ChapterRow).where(ChapterRow.project_id == self._project.id))
        session.flush()

    def _insert_book(self, session: Session, book: Book) -> tuple[int, int]:
        project = self._project_row(session)
        revision = project.current_revision
        block_count = 0
        for ordinal, chapter in enumerate(book.chapters):
            row = ChapterRow(
                id=new_id(IdPrefix.CHAPTER),
                project_id=self._project.id,
                ordinal=ordinal,
                title=chapter.title.strip() or f"Chapter {ordinal + 1}",
                included=True,
                source_href=chapter.href,
                spine_index=ordinal,
                char_count=sum(extractable_characters(block.text) for block in chapter.blocks),
            )
            session.add(row)
            session.flush()
            for block in chapter.blocks:
                self._add_block(
                    session,
                    block_id=new_id(IdPrefix.BLOCK),
                    chapter_id=row.id,
                    ordinal=block.ordinal,
                    kind=block.kind.value,
                    heading_level=block.heading_level,
                    text=block.text,
                    source_ref_json=_source_ref_json(block.source_ref),
                    revision=revision,
                )
                block_count += 1
        return len(book.chapters), block_count

    @contextmanager
    def _session(self) -> Iterator[Session]:
        with session_scope(self._project.engine) as session:
            yield session

    def _project_row(self, session: Session) -> ProjectRow:
        row = session.get(ProjectRow, self._project.id)
        if row is None:
            raise AppError(
                ErrorCode.PROJECT_NOT_FOUND,
                detail={"project_id": self._project.id},
                message="open project has no database row",
            )
        return row

    def _active(self, session: Session) -> list[ChapterRow]:
        return list(
            session.scalars(
                select(ChapterRow)
                .where(ChapterRow.project_id == self._project.id, ChapterRow.ordinal >= 0)
                .order_by(ChapterRow.ordinal)
            )
        )

    def _active_chapter(self, session: Session, chapter_id: str) -> ChapterRow:
        chapter = session.get(ChapterRow, chapter_id)
        if chapter is None or chapter.project_id != self._project.id or chapter.ordinal < 0:
            raise AppError(
                ErrorCode.TEXT_CHAPTER_NOT_FOUND,
                detail={"chapter_id": chapter_id},
                message="chapter is not in the open project",
            )
        return chapter

    def _current_blocks(self, session: Session, chapter_id: str) -> list[BlockRow]:
        return list(
            session.scalars(
                select(BlockRow)
                .where(BlockRow.chapter_id == chapter_id, BlockRow.valid_to_revision.is_(None))
                .order_by(BlockRow.ordinal)
            )
        )

    def _stored_many(self, session: Session, rows: Sequence[ChapterRow]) -> list[StoredChapter]:
        ids = [row.id for row in rows]
        counts: dict[str, int] = {}
        if ids:
            counted = session.execute(
                select(BlockRow.chapter_id, func.count(BlockRow.version_id))
                .where(BlockRow.chapter_id.in_(ids), BlockRow.valid_to_revision.is_(None))
                .group_by(BlockRow.chapter_id)
            ).all()
            counts = {str(chapter_id): int(count) for chapter_id, count in counted}
        return [
            StoredChapter(
                id=row.id,
                ordinal=row.ordinal,
                title=row.title,
                included=bool(row.included),
                block_count=counts.get(row.id, 0),
                char_count=row.char_count,
            )
            for row in rows
        ]

    def _add_block(
        self,
        session: Session,
        *,
        block_id: str,
        chapter_id: str,
        ordinal: int,
        kind: str,
        heading_level: int | None,
        text: str,
        source_ref_json: str | None,
        revision: int,
    ) -> BlockRow:
        row = BlockRow(
            id=block_id,
            version_id=f"{block_id}:{revision}",
            chapter_id=chapter_id,
            ordinal=ordinal,
            kind=kind,
            heading_level=heading_level,
            text=text,
            source_ref_json=source_ref_json,
            valid_from_revision=revision,
            valid_to_revision=None,
        )
        session.add(row)
        return row

    def _reversion_blocks(
        self,
        session: Session,
        blocks: Sequence[BlockRow],
        *,
        chapter_id: str,
        revision: int,
        ordinal_start: int,
        texts: Sequence[str] | None = None,
    ) -> None:
        """Close ``blocks`` and insert current rows that keep their ids."""
        if not blocks:
            return
        for block in blocks:
            block.valid_to_revision = revision
        session.flush()
        for offset, block in enumerate(blocks):
            text = block.text if texts is None else texts[offset]
            self._add_block(
                session,
                block_id=block.id,
                chapter_id=chapter_id,
                ordinal=ordinal_start + offset,
                kind=block.kind,
                heading_level=block.heading_level,
                text=text,
                source_ref_json=block.source_ref_json,
                revision=revision,
            )

    def _refresh_char_count(self, session: Session, chapter: ChapterRow) -> None:
        texts = session.scalars(
            select(BlockRow.text).where(
                BlockRow.chapter_id == chapter.id,
                BlockRow.valid_to_revision.is_(None),
            )
        )
        chapter.char_count = sum(extractable_characters(text) for text in texts)

    def _write_ordinals(self, session: Session, pairs: Sequence[tuple[ChapterRow, int]]) -> None:
        if not pairs:
            return
        for index, (row, _ordinal) in enumerate(pairs):
            row.ordinal = _TEMP_ORDINAL - index
        session.flush()
        for row, ordinal in pairs:
            row.ordinal = ordinal
        session.flush()

    def _shift_ordinals(self, session: Session, *, start: int, delta: int) -> None:
        if delta == 0:
            return
        pairs = [
            (row, row.ordinal + delta) for row in self._active(session) if row.ordinal >= start
        ]
        self._write_ordinals(session, pairs)

    def _next_tombstone(self, session: Session) -> int:
        current = session.scalar(
            select(func.min(ChapterRow.ordinal)).where(ChapterRow.project_id == self._project.id)
        )
        if current is None or current >= 0:
            return -1
        return int(current) - 1

    def _bump(self, session: Session, label: str) -> int:
        project = self._project_row(session)
        revision = project.current_revision + 1
        now = utc_now()
        project.current_revision = revision
        project.updated_at = to_db_time(now)
        session.add(
            RevisionRow(n=revision, created_at=to_db_time(now), label=label, reverted=False)
        )
        self._write_manifest(revision=revision, updated_at=now)
        return revision

    def _touch(self, session: Session, project: ProjectRow) -> None:
        now = utc_now()
        project.updated_at = to_db_time(now)
        self._write_manifest(revision=project.current_revision, updated_at=now)

    def _write_manifest(self, *, revision: int, updated_at: object) -> None:
        manifest = self._project.manifest.model_copy(
            update={"current_revision": revision, "updated_at": updated_at}
        )
        write_manifest(self._project.layout.manifest, manifest)
        self._project.manifest = manifest


def _stored_block(block: BlockRow) -> StoredBlock:
    return StoredBlock(
        id=block.id,
        ordinal=block.ordinal,
        kind=BlockKind(block.kind),
        text=block.text,
    )


def _source_ref_json(ref: SourceRef) -> str:
    return json.dumps(
        {"href": ref.href, "path": ref.path},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _split_point(
    blocks: Sequence[BlockRow], index: int, offset: int
) -> tuple[int, str | None, str | None]:
    """Return ``(cut, left_text, right_text)``.

    ``left_text`` and ``right_text`` are set only when the block itself is
    divided. ``cut`` is the first block index that moves, used when it is not.
    """
    block = blocks[index]
    if offset == 0:
        return index, None, None
    if offset == len(block.text):
        return index + 1, None, None
    return index, block.text[:offset], block.text[offset:]


def _split_title(
    original: str,
    right_text: str | None,
    right_blocks: Sequence[BlockRow],
    head_kind: str | None,
) -> str:
    if head_kind == BlockKind.HEADING.value and right_text and right_text.strip() != original:
        return right_text.strip()
    if right_blocks and right_blocks[0].kind == BlockKind.HEADING.value:
        heading = right_blocks[0].text.strip()
        if heading and heading != original:
            return heading
    return f"{original} (2)"
