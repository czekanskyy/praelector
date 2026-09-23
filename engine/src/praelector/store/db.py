# SPDX-License-Identifier: Apache-2.0
"""SQLite engine, session scope and the Alembic migration runner (D-02).

WAL is not a preference here: a long recording job reads and writes the chunk
index while the UI queries chapters, and without WAL those contend. Combined with
short transactions and a ``busy_timeout``, that is the mitigation for the
"SQLite lock contention during a long job" risk in PLAN.md §12.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

#: SQLite is single-writer; a short timeout turns a transient writer into a wait
#: instead of an immediate "database is locked" error.
BUSY_TIMEOUT_MS = 5000


def database_url(path: Path) -> str:
    """A SQLAlchemy URL for ``path``.

    ``as_posix()`` is deliberate: on Windows ``sqlite:///C:\\…`` parses the
    backslashes as escapes, while ``sqlite:///C:/…`` works on every platform.
    """
    return f"sqlite:///{path.as_posix()}"


def create_project_engine(db_path: Path) -> Engine:
    """An engine for one project database.

    ``StaticPool`` keeps a single connection, which is what a per-project database
    with one owning process wants: no pool churn, no cross-connection PRAGMA drift.
    """
    engine = create_engine(
        database_url(db_path),
        poolclass=StaticPool,
        connect_args={"check_same_thread": False, "timeout": BUSY_TIMEOUT_MS / 1000},
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: object, _record: object) -> None:
        # PRAGMAs are per-connection, so they have to be set on every connect.
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()

    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """One transaction per block: commit on success, roll back on anything else."""
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def run_migrations(db_path: Path) -> str:
    """Upgrade to head. Returns the resulting revision, for the open response.

    Forward-only (DATA_MODEL.md §14): there is no downgrade path in production,
    because downgrading a project would silently drop lector work.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config()
    config.set_main_option("script_location", os.fspath(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url(db_path))
    # Alembic logs through the root logger; the engine's JSON formatter handles it.
    command.upgrade(config, "head")
    return current_revision(db_path)


def current_revision(db_path: Path) -> str:
    """The alembic revision the database is at, or "" when it has none."""
    engine = create_project_engine(db_path)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            return context.get_current_revision() or ""
    finally:
        engine.dispose()
