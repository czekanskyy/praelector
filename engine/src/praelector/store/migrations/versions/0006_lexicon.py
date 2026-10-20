# SPDX-License-Identifier: Apache-2.0
"""project lexicon

Project pronunciation rules (DATA_MODEL.md §12). Global rules stay in their
own database, so every row here belongs to a project.

Revision ID: 0006_lexicon
Revises: 0005_voice_profiles
Create Date: 2026-09-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_lexicon"
down_revision: str | None = "0005_voice_profiles"
branch_labels: str | None = None
depends_on: str | None = None

_CATEGORIES = (
    "'foreign_word','acronym','toponym','numeral','ordinal_heading',"
    "'dialogue_split','speaker_gender','conversion_artifact','dict_hit'"
)


def upgrade() -> None:
    op.create_table(
        "lexicon_entry",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("is_regex", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("spoken", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=False, server_default="pl"),
        sa.Column("category", sa.String(), nullable=False, server_default="dict_hit"),
        sa.Column("auto_apply", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(f"category IN ({_CATEGORIES})", name="ck_lexicon_category"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "pattern", "is_regex", name="uq_lexicon_pattern"),
    )
    op.create_index("ix_lexicon_project", "lexicon_entry", ["project_id", "priority"])


def downgrade() -> None:
    op.drop_index("ix_lexicon_project", table_name="lexicon_entry")
    op.drop_table("lexicon_entry")
