# SPDX-License-Identifier: Apache-2.0
"""Asserts that engine lockfile does not contain torch or torch dependencies."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/assert_no_torch.py <path/to/uv.lock>",
            file=sys.stderr,
        )
        return 1

    lockfile_path = Path(sys.argv[1])
    if not lockfile_path.exists():
        print(f"Error: Lockfile not found at {lockfile_path}", file=sys.stderr)
        return 1

    content = lockfile_path.read_text(encoding="utf-8")
    # Check for torch package definition in uv.lock
    forbidden = [
        'name = "torch"',
        "name = 'torch'",
        'name = "torchaudio"',
        'name = "torchvision"',
    ]
    for pkg in forbidden:
        if pkg in content:
            print(
                f"Assertion failed: Forbidden dependency {pkg} found in {lockfile_path}!",
                file=sys.stderr,
            )
            print("The engine core must remain torch-free.", file=sys.stderr)
            return 1

    print(f"Success: No torch found in {lockfile_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
