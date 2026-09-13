# SPDX-License-Identifier: Apache-2.0
"""Check or enforce SPDX license headers in all source files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SPDX_LINE_HASH = "# SPDX-License-Identifier: Apache-2.0"
SPDX_LINE_SLASH = "// SPDX-License-Identifier: Apache-2.0"

EXT_MAP = {
    ".py": SPDX_LINE_HASH,
    ".rs": SPDX_LINE_SLASH,
    ".ts": SPDX_LINE_SLASH,
    ".tsx": SPDX_LINE_SLASH,
    ".js": SPDX_LINE_SLASH,
    ".mjs": SPDX_LINE_SLASH,
}

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "generated",
    "migrations",
}


def should_ignore(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


def check_or_fix(root: Path, fix: bool = False) -> int:
    missing_files: list[Path] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_ignore(path):
            continue
        if path.suffix not in EXT_MAP:
            continue

        expected = EXT_MAP[path.suffix]
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        first_lines = content.splitlines()[:5]
        has_spdx = any(expected in line for line in first_lines)

        if not has_spdx:
            if fix:
                if content.startswith("#!"):
                    lines = content.split("\n", 1)
                    new_content = f"{lines[0]}\n{expected}\n" + (lines[1] if len(lines) > 1 else "")
                else:
                    new_content = f"{expected}\n{content}"
                path.write_text(new_content, encoding="utf-8")
                print(f"Fixed: {path}")
            else:
                missing_files.append(path)

    if missing_files:
        print("Missing SPDX license headers in the following files:", file=sys.stderr)
        for f in missing_files:
            print(f"  {f}", file=sys.stderr)
        print(
            "\nRun `python scripts/spdx_headers.py --fix` to add missing headers.",
            file=sys.stderr,
        )
        return 1

    print("All source files contain valid SPDX license headers.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or fix SPDX license headers.")
    parser.add_argument(
        "--check", action="store_true", help="Check headers (exit 1 if any missing)"
    )
    parser.add_argument("--fix", action="store_true", help="Automatically add missing headers")
    parser.add_argument("root", nargs="?", default=".", help="Root directory to scan")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    return check_or_fix(root, fix=args.fix)


if __name__ == "__main__":
    raise SystemExit(main())
