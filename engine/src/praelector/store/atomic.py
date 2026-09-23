# SPDX-License-Identifier: Apache-2.0
"""Atomic writes: temp file beside the target, fsync, ``os.replace`` (JB-02).

``os.replace`` is atomic on both NTFS and POSIX, so a reader sees either the old
file or the new one, never a partial write. That is what makes "kill the app at
40 % and restart" a data question rather than a corruption question (JB-07).

The temp file is created **in the target's directory**: a rename across
filesystems is not atomic, and on Windows it is not even a rename.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_IS_WINDOWS: bool = sys.platform == "win32"


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Replace ``path`` with ``data`` or leave the previous contents untouched."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=os.fspath(path.parent),
        prefix=f"{path.name}.",
        suffix=".part",
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _sync_directory(path.parent)


def write_text_atomic(path: Path, text: str) -> None:
    write_bytes_atomic(path, text.encode("utf-8"))


def write_json_atomic(path: Path, payload: Any) -> None:
    """Canonical JSON, so two writes of equal data produce equal bytes."""
    write_text_atomic(path, canonical_json(payload))


def canonical_json(payload: Any) -> str:
    """Sorted keys, no trailing whitespace, LF endings, non-ASCII preserved.

    Determinism matters twice: ``render_key`` hashes canonical JSON
    (DATA_MODEL.md §9.1) and CI diffs generated files.
    """
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        + "\n"
    )


def _sync_directory(directory: Path) -> None:
    """Flush the rename itself. Windows has no directory fsync; skip it there."""
    if _IS_WINDOWS:
        return
    try:
        fd = os.open(os.fspath(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
