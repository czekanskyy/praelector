# SPDX-License-Identifier: Apache-2.0
"""voice profiles

One reference sample per row (DATA_MODEL.md §7). A slot is unique inside a
project only when it is assigned; unassigned profiles may share a null slot.

Revision ID: 0005_voice_profiles
Revises: 0004_chunks
Create Date: 2026-09-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_voice_profiles"
down_revision: str | None = "0004_chunks"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "voice_profile",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slot", sa.String(), nullable=True),
        sa.Column("source_filename", sa.String(), nullable=False),
        sa.Column("source_sha256", sa.String(), nullable=False),
        sa.Column("ref_text", sa.String(), nullable=False),
        sa.Column("processed_rel", sa.String(), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False),
        sa.Column("channels", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("measured_lufs", sa.Float(), nullable=True),
        sa.Column("target_lufs", sa.Float(), nullable=False, server_default="-23.0"),
        sa.Column("trim_applied", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("chain_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            "slot IS NULL OR slot IN ('narrator','dialogue','male','female')",
            name="ck_voice_profile_slot",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_voice_slot",
        "voice_profile",
        ["project_id", "slot"],
        unique=True,
        sqlite_where=sa.text("slot IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_voice_slot", table_name="voice_profile")
    op.drop_table("voice_profile")
