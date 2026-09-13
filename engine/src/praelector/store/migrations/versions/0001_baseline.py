# SPDX-License-Identifier: Apache-2.0
"""Baseline schema initialization.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-13 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from praelector.store.schema import metadata

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    metadata.drop_all(bind=bind)
