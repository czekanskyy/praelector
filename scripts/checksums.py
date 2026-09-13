# SPDX-License-Identifier: Apache-2.0
"""Generate SHA256 checksums for files in a directory."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python checksums.py <directory>", file=sys.stderr)
        return 1

    target_dir = Path(sys.argv[1])
    if not target_dir.exists():
        print(f"Directory not found: {target_dir}", file=sys.stderr)
        return 1

    for item in sorted(target_dir.glob("*")):
        if item.is_file():
            hasher = hashlib.sha256()
            hasher.update(item.read_bytes())
            print(f"{hasher.hexdigest()}  {item.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
