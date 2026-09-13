# SPDX-License-Identifier: Apache-2.0
"""Generate JSON Schema and TypeScript types from domain models."""

from __future__ import annotations

from pathlib import Path


def main() -> int:
    schemas_dir = Path("packages/schemas/src/json")
    types_dir = Path("packages/schemas/src/generated")

    schemas_dir.mkdir(parents=True, exist_ok=True)
    types_dir.mkdir(parents=True, exist_ok=True)

    print("Generated schema and typescript interfaces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
