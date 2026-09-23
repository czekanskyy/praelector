# SPDX-License-Identifier: Apache-2.0
"""baseline: project and revision

The initial schema for a project database. Only the tables this milestone uses are
created; every later PR adds its own migration alongside the code that needs it,
so the schema never runs ahead of the features.

Shapes are transcribed from docs/plan/DATA_MODEL.md §2.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("source_format", sa.String(), nullable=True),
        sa.Column("source_original_rel", sa.String(), nullable=True),
        sa.Column("working_epub_rel", sa.String(), nullable=True),
        sa.Column("converter", sa.String(), nullable=True),
        sa.Column("book_language", sa.String(), nullable=True),
        sa.Column("spoken_language", sa.String(), nullable=False, server_default="pl"),
        sa.Column("voice_mode", sa.String(), nullable=False),
        sa.Column("backend_id", sa.String(), nullable=True),
        sa.Column("backend_params_json", sa.String(), nullable=True),
        sa.Column("precision", sa.String(), nullable=True, server_default="fp16"),
        sa.Column("cloud_llm_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "voice_mode IN ('single','narrator_dialogue','narrator_male_female')",
            name="ck_project_voice_mode",
        ),
    )

    op.create_table(
        "revision",
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("batch_id", sa.String(), nullable=True),
        sa.Column("reverted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("n"),
    )


def downgrade() -> None:
    # Forward-only in production (DATA_MODEL.md §14); this exists so a test can
    # prove the baseline is reversible, never so a project can be downgraded.
    op.drop_table("revision")
    op.drop_table("project")
