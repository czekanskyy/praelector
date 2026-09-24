# SPDX-License-Identifier: Apache-2.0
"""spans

SCD-2 spans hung off a logical block id (DATA_MODEL.md §5). A current span has
``valid_to_revision`` NULL.

Revision ID: 0003_spans
Revises: 0002_chapters
Create Date: 2026-09-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_spans"
down_revision: str | None = "0002_chapters"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "span",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("block_id", sa.String(), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False),
        sa.Column("end", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("gender", sa.String(), nullable=True),
        sa.Column("gender_confidence", sa.Float(), nullable=True),
        sa.Column("speaker_id", sa.String(), nullable=True),
        sa.Column("spoken", sa.String(), nullable=True),
        sa.Column("pause_ms", sa.Integer(), nullable=True),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("orphaned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("valid_from_revision", sa.Integer(), nullable=False),
        sa.Column("valid_to_revision", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('narration','dialogue','pronunciation','pause','skip')",
            name="ck_span_kind",
        ),
        sa.CheckConstraint(
            "gender IS NULL OR gender IN ('male','female','unknown')",
            name="ck_span_gender",
        ),
        sa.CheckConstraint("start >= 0 AND end >= start", name="ck_span_range"),
        sa.PrimaryKeyConstraint("version_id"),
    )
    op.create_index("ix_span_current", "span", ["block_id", "valid_to_revision", "start"])


def downgrade() -> None:
    op.drop_index("ix_span_current", table_name="span")
    op.drop_table("span")
