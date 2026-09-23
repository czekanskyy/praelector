# SPDX-License-Identifier: Apache-2.0
"""Alembic environment for per-project SQLite databases.

There is no ``alembic.ini``: the engine builds a ``Config`` programmatically
(``store/db.py``) because the database URL is only known once a project is being
opened. Logging is left to the engine's JSON formatter rather than Alembic's
``fileConfig``, which would replace our handlers.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from praelector.store.tables import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without a connection. Unused in production, kept for debugging."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER most things in place; batch mode rewrites the
            # table instead, which is what makes later migrations possible at all.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
