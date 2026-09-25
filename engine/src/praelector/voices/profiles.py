# SPDX-License-Identifier: Apache-2.0
"""Voice profile rows (DATA_MODEL.md §7, TTS-03).

The ingest chain writes the wav. This module only stores the row that points
at it. One assigned slot per project; a null slot means the sample is unused.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from praelector.domain.enums import VoiceSlot
from praelector.domain.ids import IdPrefix, new_id
from praelector.errors import AppError, ErrorCode
from praelector.store.manifest import utc_now
from praelector.store.tables import VoiceProfileRow, to_db_time

_SLOTS = frozenset(VoiceSlot)


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    """The row the rest of the engine reads."""

    id: str
    project_id: str
    name: str
    slot: str | None
    source_filename: str
    source_sha256: str
    ref_text: str
    processed_rel: str
    sample_rate: int
    channels: int
    duration_s: float
    measured_lufs: float | None
    target_lufs: float
    trim_applied: bool
    content_hash: str
    chain_version: str
    created_at: str


def create_profile(
    session: Session,
    *,
    project_id: str,
    name: str,
    source_filename: str,
    source_sha256: str,
    ref_text: str,
    processed_rel: str,
    sample_rate: int,
    duration_s: float,
    content_hash: str,
    chain_version: str,
    slot: str | None = None,
    channels: int = 1,
    measured_lufs: float | None = None,
    target_lufs: float = -23.0,
    trim_applied: bool = True,
) -> VoiceProfile:
    """Insert one profile. A taken slot is ``voice.slot_conflict``."""
    text = _ref_text(ref_text)
    chosen = _slot(slot)
    _claim(session, project_id, chosen, ignore_id=None)
    row = VoiceProfileRow(
        id=new_id(IdPrefix.VOICE_PROFILE),
        project_id=project_id,
        name=name,
        slot=chosen,
        source_filename=source_filename,
        source_sha256=source_sha256,
        ref_text=text,
        processed_rel=processed_rel,
        sample_rate=sample_rate,
        channels=channels,
        duration_s=duration_s,
        measured_lufs=measured_lufs,
        target_lufs=target_lufs,
        trim_applied=trim_applied,
        content_hash=content_hash,
        chain_version=chain_version,
        created_at=to_db_time(utc_now()),
    )
    session.add(row)
    session.flush()
    return _profile(row)


def list_profiles(session: Session, project_id: str) -> list[VoiceProfile]:
    """Profiles for one project, oldest first."""
    rows = session.scalars(
        select(VoiceProfileRow)
        .where(VoiceProfileRow.project_id == project_id)
        .order_by(VoiceProfileRow.created_at, VoiceProfileRow.id)
    ).all()
    return [_profile(row) for row in rows]


def get_profile(session: Session, profile_id: str) -> VoiceProfile:
    """Load one profile, or ``voice.not_found``."""
    return _profile(_row(session, profile_id))


def rename_profile(session: Session, profile_id: str, name: str) -> VoiceProfile:
    row = _row(session, profile_id)
    row.name = name
    session.flush()
    return _profile(row)


def set_ref_text(session: Session, profile_id: str, ref_text: str) -> VoiceProfile:
    row = _row(session, profile_id)
    row.ref_text = _ref_text(ref_text)
    session.flush()
    return _profile(row)


def set_slot(session: Session, profile_id: str, slot: str | None) -> VoiceProfile:
    """Move the sample onto a slot, or clear it with ``None``."""
    row = _row(session, profile_id)
    chosen = _slot(slot)
    _claim(session, row.project_id, chosen, ignore_id=row.id)
    row.slot = chosen
    session.flush()
    return _profile(row)


def delete_profile(session: Session, profile_id: str) -> None:
    """Drop the row. The wav file is left for the caller."""
    session.delete(_row(session, profile_id))
    session.flush()


def _row(session: Session, profile_id: str) -> VoiceProfileRow:
    row = session.get(VoiceProfileRow, profile_id)
    if row is None:
        raise AppError(ErrorCode.VOICE_NOT_FOUND, detail={"id": profile_id})
    return row


def _ref_text(ref_text: str) -> str:
    text = ref_text.strip()
    if not text:
        raise AppError(ErrorCode.VOICE_REF_TEXT_REQUIRED)
    return text


def _slot(slot: str | None) -> str | None:
    if slot is None:
        return None
    if slot not in _SLOTS:
        raise AppError(ErrorCode.VOICE_SLOT_CONFLICT, detail={"slot": slot})
    return slot


def _claim(session: Session, project_id: str, slot: str | None, *, ignore_id: str | None) -> None:
    if slot is None:
        return
    taken = session.scalars(
        select(VoiceProfileRow).where(
            VoiceProfileRow.project_id == project_id,
            VoiceProfileRow.slot == slot,
        )
    ).one_or_none()
    if taken is not None and taken.id != ignore_id:
        raise AppError(
            ErrorCode.VOICE_SLOT_CONFLICT,
            detail={"slot": slot, "id": taken.id},
        )


def _profile(row: VoiceProfileRow) -> VoiceProfile:
    return VoiceProfile(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        slot=row.slot,
        source_filename=row.source_filename,
        source_sha256=row.source_sha256,
        ref_text=row.ref_text,
        processed_rel=row.processed_rel,
        sample_rate=row.sample_rate,
        channels=row.channels,
        duration_s=row.duration_s,
        measured_lufs=row.measured_lufs,
        target_lufs=row.target_lufs,
        trim_applied=row.trim_applied,
        content_hash=row.content_hash,
        chain_version=row.chain_version,
        created_at=row.created_at,
    )
