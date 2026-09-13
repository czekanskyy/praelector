# SPDX-License-Identifier: Apache-2.0
"""Programmatic migration runner for Praelector SQLite databases."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def get_alembic_config(db_path: Path | str) -> Config:
    """Create Alembic Config targeting the specific SQLite database file."""
    path = Path(db_path).resolve()
    migrations_dir = Path(__file__).parent
    alembic_ini = migrations_dir / "alembic.ini"

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    return cfg


def apply_migrations(db_path: Path | str) -> None:
    """Apply all pending database migrations up to head."""
    cfg = get_alembic_config(db_path)
    command.upgrade(cfg, "head")
