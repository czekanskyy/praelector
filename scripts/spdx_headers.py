#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check or insert the SPDX header every source file must carry (REPO_LAYOUT.md §1)."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

COMMENT_PREFIX: dict[str, str] = {
    ".py": "#",
    ".ts": "//",
    ".tsx": "//",
    ".rs": "//",
}

SKIP_DIRS = frozenset(
    {
        ".git",
        ".qwen",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "target",
        "venv",
        ".venv",
    }
)

# Generated code is produced by gen_ts_types.py and re-checked by the CI diff, so a
# header there would be wiped by the next codegen run.
GENERATED_SUBTREE = Path("packages") / "schemas" / "src" / "generated"

LICENSE_ID = "Apache-2.0"
SPDX_RE = re.compile(r"SPDX-License-Identifier\s*[:=]\s*(\S+)")


@dataclass(frozen=True)
class Violation:
    path: Path
    kind: str  # "missing" | "wrong"
    detail: str


def expected_header(suffix: str) -> str:
    return f"{COMMENT_PREFIX[suffix]} SPDX-License-Identifier: {LICENSE_ID}"


def source_files(root: Path) -> Iterator[Path]:
    generated = (root / GENERATED_SUBTREE).resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in SKIP_DIRS and (current / name).resolve() != generated
        )
        for filename in sorted(filenames):
            suffix = Path(filename).suffix.lower()
            if suffix in COMMENT_PREFIX:
                yield current / filename


def read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        print(f"warning: {path} is not valid UTF-8; skipped", file=sys.stderr)
        return None
    except OSError as exc:
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return None


def inspect(path: Path, root: Path) -> Violation | None:
    text = read_text(path)
    if text is None:
        return None

    header = expected_header(path.suffix.lower())
    lines = text.splitlines()
    # A shebang must stay the first line, so the header is allowed to sit on line 2.
    offset = 1 if lines and lines[0].startswith("#!") else 0

    for index in range(min(len(lines), offset + 3)):
        match = SPDX_RE.search(lines[index])
        if match is None:
            continue
        declared = match.group(1)
        if index != offset:
            return Violation(
                path=path.relative_to(root),
                kind="missing",
                detail=f"SPDX header is on line {index + 1}, expected line {offset + 1}",
            )
        if lines[index].strip() != header:
            if declared == LICENSE_ID:
                return Violation(
                    path=path.relative_to(root),
                    kind="wrong",
                    detail=f"malformed header line: {lines[index].strip()!r}",
                )
            return Violation(
                path=path.relative_to(root),
                kind="wrong",
                detail=f"declares {declared!r}, expected {LICENSE_ID!r}",
            )
        return None

    return Violation(
        path=path.relative_to(root),
        kind="missing",
        detail=f"expected {header!r} on line {offset + 1}",
    )


def fix(path: Path) -> bool:
    text = read_text(path)
    if text is None:
        return False

    header = expected_header(path.suffix.lower())
    newline = "\r\n" if "\r\n" in text[:4096] else "\n"
    lines = text.splitlines()
    offset = 1 if lines and lines[0].startswith("#!") else 0

    for index in range(min(len(lines), offset + 3)):
        if SPDX_RE.search(lines[index]) is None:
            continue
        if lines[index].strip() == header:
            return False
        lines[index] = header
        _write(path, lines, newline)
        return True

    lines.insert(offset, header)
    # Keep the header visually separate from the module docstring or first import.
    following = lines[offset + 1 : offset + 2]
    if following and following[0].strip():
        lines.insert(offset + 1, "")
    _write(path, lines, newline)
    return True


def _write(path: Path, lines: list[str], newline: str) -> None:
    body = newline.join(lines)
    if body and not body.endswith(newline):
        body += newline
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(body)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="spdx_headers.py",
        description=(
            "Verify that every .py/.ts/.tsx/.rs file starts with "
            f"'SPDX-License-Identifier: {LICENSE_ID}'."
        ),
        epilog="exit codes: 0 clean, 1 violations, 2 usage error",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="report violations and exit 1 if any (default)",
    )
    mode.add_argument(
        "--fix",
        action="store_true",
        help="insert or correct the header in place",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root to walk (default: the parent of scripts/)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root: Path = args.root.resolve()
    if not root.is_dir():
        print(f"error: --root is not a directory: {root}", file=sys.stderr)
        return 2

    if args.fix:
        changed: list[Path] = []
        for path in source_files(root):
            if fix(path):
                changed.append(path.relative_to(root))
        for path in changed:
            print(f"fixed: {path}")
        print(f"ok: {len(changed)} file(s) updated")
        return 0

    violations = [v for v in (inspect(p, root) for p in source_files(root)) if v]
    for item in violations:
        print(f"{item.kind}: {item.path} — {item.detail}")

    missing = sum(1 for v in violations if v.kind == "missing")
    wrong = len(violations) - missing
    if violations:
        print(
            f"FAIL: {len(violations)} SPDX violation(s): {missing} missing, {wrong} wrong license id",
            file=sys.stderr,
        )
        print("  run `python scripts/spdx_headers.py --fix` to repair them", file=sys.stderr)
        return 1

    print(f"ok: every source file carries the {LICENSE_ID} SPDX header")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
