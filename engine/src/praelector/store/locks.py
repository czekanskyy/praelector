# SPDX-License-Identifier: Apache-2.0
"""``project.lock``: one process per project (JB-06, D-14).

The lock is a byte-range lock on an open file descriptor, not an exclusive-create
of the file itself, so a crash releases it: the OS drops the lock when the handle
goes away. A stale ``project.lock`` file left behind by a killed app is therefore
harmless — it is a diagnostic (it holds the owning pid), never a blocker.

This is the belt to ``tauri-plugin-single-instance``'s braces: the shell prevents
a second app instance, and this prevents a second *engine* (a developer running
``just dev-engine`` against a project the app already has open).
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from praelector.errors import AppError, ErrorCode

_IS_WINDOWS: bool = sys.platform == "win32"

#: The pid lives *after* the locked byte. On Windows a byte-range lock is
#: mandatory, so a second handle cannot read anything inside the locked range —
#: keeping the pid outside it is what lets a refused caller name the owner.
_LOCK_BYTE = 0
_PID_OFFSET = 16


def _load(name: str) -> Any:
    """Import a platform-only module without a static import mypy would reject."""
    return importlib.import_module(name)


class ProjectLock:
    """An advisory exclusive lock on one project directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> None:
        """Take the lock or raise ``project.locked`` naming the process that holds it."""
        if self._fd is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(os.fspath(self.path), os.O_RDWR | os.O_CREAT, 0o644)
        owner = _read_pid(fd)
        if not _lock_fd(fd):
            os.close(fd)
            raise AppError(
                ErrorCode.PROJECT_LOCKED,
                detail={"path": self.path.as_posix(), "owner_pid": owner},
                message="another process holds this project",
            )
        self._fd = fd
        _write_pid(fd)

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        _unlock_fd(fd)
        os.close(fd)

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def _lock_fd(fd: int) -> bool:
    """Best-effort non-blocking exclusive lock. False means someone else holds it."""
    with contextlib.suppress(OSError):
        os.lseek(fd, _LOCK_BYTE, os.SEEK_SET)
    if _IS_WINDOWS:
        msvcrt = _load("msvcrt")
        try:
            # One byte is enough: the range is what is exclusive.
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    fcntl = _load("fcntl")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_fd(fd: int) -> None:
    try:
        if _IS_WINDOWS:
            msvcrt = _load("msvcrt")
            os.lseek(fd, _LOCK_BYTE, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl = _load("fcntl")
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        # Releasing on the way out; a failure here would only mask the real error.
        pass


def _write_pid(fd: int) -> None:
    try:
        os.lseek(fd, _PID_OFFSET, os.SEEK_SET)
        written = os.write(fd, f"{os.getpid()}\n".encode())
        os.ftruncate(fd, _PID_OFFSET + written)
    except OSError:
        pass


def _read_pid(fd: int) -> int | None:
    """The pid recorded by whoever holds the lock, for the error detail."""
    try:
        os.lseek(fd, _PID_OFFSET, os.SEEK_SET)
        raw = os.read(fd, 32).decode(errors="replace").strip()
    except OSError:
        return None
    return int(raw) if raw.isdigit() else None
