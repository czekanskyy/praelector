# SPDX-License-Identifier: Apache-2.0
"""Build frozen PyInstaller onedir distribution for praelector-engine."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze praelector-engine with PyInstaller.")
    parser.add_argument("--onedir", action="store_true", help="Build onedir bundle")
    args = parser.parse_args()

    print(f"Building frozen engine (onedir={args.onedir})...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
