# SPDX-License-Identifier: Apache-2.0
"""chunk index

A mirror of the sidecars that survived reconcile (DATA_MODEL.md §9). Disk is
still the source of truth: open deletes these rows and inserts only the keys
whose wav still matches. Identity columns from the full schema are not stored
until sidecars carry them.

Revision ID: 0004_chunks
Revises: 0003_spans
Create Date: 2026-09-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_chunks"
down_revision: str | None = "0003_spans"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "chunk",
        sa.Column("render_key", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("rel_path", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("render_key"),
    )


def downgrade() -> None:
    op.drop_table("chunk")
