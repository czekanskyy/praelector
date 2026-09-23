# SPDX-License-Identifier: Apache-2.0
"""chapters and blocks

Chapter tree and SCD-2 block versions (DATA_MODEL.md §3 and §4). Span rows are
not created here: a later revision can hang them off ``block.id``.

A merged chapter is not deleted. Its ordinal becomes negative so the block
versions that still name it keep a foreign key, and the tree query ignores
ordinals below zero.

Revision ID: 0002_chapters
Revises: 0001_baseline
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_chapters"
down_revision: str | None = "0001_baseline"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "chapter",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_href", sa.String(), nullable=True),
        sa.Column("spine_index", sa.Integer(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], name="fk_chapter_project"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "ordinal", name="uq_chapter_ordinal"),
    )
    op.create_index("ix_chapter_project", "chapter", ["project_id", "ordinal"])

    op.create_table(
        "block",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("chapter_id", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("heading_level", sa.Integer(), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("source_ref_json", sa.String(), nullable=True),
        sa.Column("valid_from_revision", sa.Integer(), nullable=False),
        sa.Column("valid_to_revision", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('paragraph','heading','blockquote','list_item','caption')",
            name="ck_block_kind",
        ),
        sa.CheckConstraint(
            "heading_level IS NULL OR (heading_level >= 1 AND heading_level <= 6)",
            name="ck_block_heading_level",
        ),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapter.id"], name="fk_block_chapter"),
        sa.PrimaryKeyConstraint("version_id"),
    )
    op.create_index("ix_block_current", "block", ["chapter_id", "valid_to_revision", "ordinal"])
    op.create_index("ix_block_id", "block", ["id", "valid_from_revision"])


def downgrade() -> None:
    op.drop_index("ix_block_id", table_name="block")
    op.drop_index("ix_block_current", table_name="block")
    op.drop_table("block")
    op.drop_index("ix_chapter_project", table_name="chapter")
    op.drop_table("chapter")
