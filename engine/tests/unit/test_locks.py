# SPDX-License-Identifier: Apache-2.0
"""Unit tests for exclusive file locking."""

from __future__ import annotations

from pathlib import Path

import pytest

from praelector.errors import AppError
from praelector.store.locks import ProjectLock


def test_lock_acquire_and_release(tmp_path: Path) -> None:
    lock_file = tmp_path / "project.lock"
    lock = ProjectLock(lock_file)

    assert not lock.is_locked
    lock.acquire()
    assert lock.is_locked
    assert lock_file.is_file()

    lock.release()
    assert not lock.is_locked


def test_lock_conflict_raises_error(tmp_path: Path) -> None:
    lock_file = tmp_path / "project.lock"
    lock1 = ProjectLock(lock_file)
    lock2 = ProjectLock(lock_file)

    lock1.acquire()
    try:
        with pytest.raises(AppError) as exc_info:
            lock2.acquire()

        assert exc_info.value.code == "project.locked"
        assert exc_info.value.status_code == 409
    finally:
        lock1.release()

    # Now lock2 should succeed
    lock2.acquire()
    assert lock2.is_locked
    lock2.release()


def test_lock_context_manager(tmp_path: Path) -> None:
    lock_file = tmp_path / "project.lock"
    with ProjectLock(lock_file) as lock:
        assert lock.is_locked

    assert not lock.is_locked
