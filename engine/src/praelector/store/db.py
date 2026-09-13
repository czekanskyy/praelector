# SPDX-License-Identifier: Apache-2.0
"""Database engine and connection management for SQLite project stores."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from praelector.store.schema import metadata


def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Enforce WAL mode, foreign keys, synchronous normal, and busy timeout."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_project_engine(db_path: Path | str) -> Engine:
    """Create a configured SQLite SQLAlchemy engine for a project database."""
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    sqlite_url = f"sqlite:///{path.as_posix()}"

    engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def init_db_schema(engine: Engine) -> None:
    """Create all schema tables if they do not already exist."""
    metadata.create_all(engine)


@contextmanager
def project_session(engine: Engine) -> Iterator[Session]:
    """Provide a transactional session scope for database operations."""
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
