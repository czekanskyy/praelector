# SPDX-License-Identifier: Apache-2.0
"""Atomic file writing operations with durability guarantees."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write(target: Path | str, content: str | bytes, encoding: str = "utf-8") -> None:
    """Atomically write content to target path using a temp file and replace.

    Guarantees that torn writes do not leave corrupted target files.
    """
    target_path = Path(target).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a temp file in the same directory to ensure it's on the same filesystem
    prefix = f".{target_path.name}.part."
    is_bytes = isinstance(content, bytes)

    with tempfile.NamedTemporaryFile(
        mode="wb" if is_bytes else "w",
        dir=target_path.parent,
        prefix=prefix,
        delete=False,
        encoding=None if is_bytes else encoding,
    ) as f:
        temp_name = f.name
        try:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
            raise

    # Atomic rename/replace
    os.replace(temp_name, target_path)
