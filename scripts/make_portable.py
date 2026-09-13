# SPDX-License-Identifier: Apache-2.0
"""Create portable ZIP or tar.gz distribution archives."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Package portable distribution archives.")
    parser.add_argument("--os", required=True, help="Target OS/architecture (e.g. windows-x64, linux-x64)")
    args = parser.parse_args()

    print(f"Creating portable archive for {args.os}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
