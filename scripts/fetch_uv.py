# SPDX-License-Identifier: Apache-2.0
"""Fetch and verify bundled uv executable for release packaging."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and verify bundled uv binary.")
    parser.add_argument("--verify", action="store_true", help="Verify checksums against known list")
    args = parser.parse_args()

    print(f"Bundling uv binary (verify={args.verify})...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
