# SPDX-License-Identifier: Apache-2.0
"""Exclusive file locking for project directories."""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import IO, Any

from praelector.errors import AppError

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class ProjectLock:
    """Acquires an exclusive, non-blocking lock on a project directory.

    Guarantees single-writer safety for project.db and workspace directories.
    """

    def __init__(self, lock_file_path: Path | str) -> None:
        self.path = Path(lock_file_path).resolve()
        self._file: IO[Any] | None = None
        self._locked = False

    @property
    def is_locked(self) -> bool:
        return self._locked

    def acquire(self) -> None:
        """Acquire the exclusive lock or raise AppError(project.locked)."""
        if self._locked:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Open file in append/read-write mode without truncating; handle kept open during lock
            self._file = open(self.path, "a+b")  # noqa: SIM115
        except OSError as err:
            raise AppError(
                code="project.lock_failed",
                detail={"path": str(self.path), "error": str(err)},
                status_code=500,
            ) from err

        try:
            if sys.platform == "win32":
                self._file.seek(0)
                # Lock byte 0 with non-blocking mode
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Write current PID into lock file for diagnostic inspection
            self._file.seek(0)
            self._file.truncate()
            self._file.write(f"pid={os.getpid()}\n".encode())
            self._file.flush()
            self._locked = True
        except (OSError, BlockingIOError, PermissionError) as err:
            if self._file:
                with contextlib.suppress(OSError):
                    self._file.close()
                self._file = None
            raise AppError(
                code="project.locked",
                detail={"path": str(self.path), "reason": "Another process has this project open"},
                status_code=409,
                retryable=False,
            ) from err

    def release(self) -> None:
        """Release the exclusive lock."""
        if not self._locked or self._file is None:
            return

        try:
            if sys.platform == "win32":
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            with contextlib.suppress(OSError):
                self._file.close()
            self._file = None
            self._locked = False

    def __enter__(self) -> ProjectLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()
