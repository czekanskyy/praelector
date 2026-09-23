#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write and verify sha256sum(1)-compatible manifests for release artifacts (D-24)."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MANIFEST = "SHA256SUMS"
CHUNK = 1 << 20
# hash, one space, then a space (text mode) or an asterisk (binary mode), then name.
LINE_RE = re.compile(r"^([0-9a-fA-F]{64}) ([ *])(.*)$")


# release.yml redirects this script's stdout into dist/SHA256SUMS.<target>, so the
# shell has already created that file inside the tree being hashed. Including it
# would make the manifest depend on a race (and on its own contents), so every
# SHA256SUMS* file is excluded by name.
def is_manifest(path: Path) -> bool:
    return path.name == MANIFEST or path.name.startswith(f"{MANIFEST}.")


def iter_files(directory: Path) -> Iterator[tuple[str, Path]]:
    for dirpath, dirnames, filenames in os.walk(directory, followlinks=False):
        dirnames.sort()
        current = Path(dirpath)
        for name in sorted(filenames):
            path = current / name
            if is_manifest(path):
                continue
            # Only regular files are hashed: a symlink's digest would depend on its
            # target, which is not what a release manifest promises.
            if path.is_symlink() or not path.is_file():
                continue
            yield path.relative_to(directory).as_posix(), path


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            hasher.update(block)
    return hasher.hexdigest()


def format_line(checksum: str, name: str) -> str:
    """Render one sha256sum(1) line, escaping the whole line when the name needs it."""
    if "\\" in name or "\n" in name:
        escaped = name.replace("\\", "\\\\").replace("\n", "\\n")
        return f"\\{checksum}  {escaped}"
    return f"{checksum}  {name}"


def decode_name(name: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(name):
        char = name[index]
        if char == "\\" and index + 1 < len(name):
            following = name[index + 1]
            if following == "\\":
                out.append("\\")
                index += 2
                continue
            if following == "n":
                out.append("\n")
                index += 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


def build_manifest(directory: Path) -> list[str]:
    entries = sorted(iter_files(directory), key=lambda item: item[0])
    return [format_line(digest(path), name) for name, path in entries]


def parse_manifest(text: str, source: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        # A leading backslash marks a line whose filename was escaped; the separator
        # is two spaces in text mode and " *" in binary mode.
        line = raw.removeprefix("\\")
        match = LINE_RE.match(line)
        if match is None:
            print(
                f"warning: {source}:{number} is not a sha256sum line; skipped",
                file=sys.stderr,
            )
            continue
        records.append((match.group(1).lower(), decode_name(match.group(3))))
    return records


def verify(directory: Path, manifest: Path, quiet: bool) -> int:
    if not manifest.is_file():
        print(f"error: manifest not found: {manifest}", file=sys.stderr)
        return 2

    records = parse_manifest(manifest.read_text(encoding="utf-8"), str(manifest))
    if not records:
        print(f"error: {manifest} lists no files", file=sys.stderr)
        return 2

    failed: list[str] = []
    missing: list[str] = []
    for expected, encoded in records:
        name = decode_name(encoded)
        target = directory / name
        if not target.is_file():
            missing.append(name)
            if not quiet:
                print(f"{name}: MISSING")
            continue
        actual = digest(target)
        if actual != expected:
            failed.append(name)
            print(f"{name}: FAILED")
            continue
        if not quiet:
            print(f"{name}: OK")

    if failed:
        print(
            f"{MANIFEST}: WARNING: {len(failed)} computed checksum(s) did NOT match",
            file=sys.stderr,
        )
    if missing:
        print(
            f"{MANIFEST}: WARNING: {len(missing)} listed file(s) are missing",
            file=sys.stderr,
        )
    if failed or missing:
        return 1

    if quiet:
        print(f"ok: {len(records)} file(s) verified against {manifest.name}")
    return 0


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="checksums.py",
        description=(
            f"Hash every regular file under DIR and emit a {MANIFEST} manifest in "
            f"sha256sum(1) format (hex, two spaces, POSIX-relative filename). "
            f"v1 binaries are unsigned, so this manifest is the only integrity "
            f"story a user has (D-24)."
        ),
        epilog=(
            "exit codes: 0 written or verified, 1 verification failure, 2 usage or missing input"
        ),
    )
    parser.add_argument("directory", metavar="DIR", help="directory to hash")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help=f"write DIR/{MANIFEST} instead of printing to stdout",
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help=f"check files against DIR/{MANIFEST} (or --file) instead of hashing",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help="write the manifest to FILE instead of stdout (implies --write)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        metavar="FILE",
        help=f"manifest to verify (default: DIR/{MANIFEST})",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="with --verify, print only failures",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root that a relative DIR resolves against",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root: Path = args.root.resolve()

    raw = Path(args.directory)
    directory = raw if raw.is_absolute() else root / raw
    if not directory.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    if args.verify:
        manifest = args.file or (directory / MANIFEST)
        if not manifest.is_absolute():
            manifest = root / manifest
        return verify(directory, manifest.resolve(), args.quiet)

    lines = build_manifest(directory)

    if args.output is not None:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {output} ({len(lines)} file(s))")
        return 0

    if args.write:
        target = directory / MANIFEST
        target.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {target}", file=sys.stderr)
        return 0

    sys.stdout.write("\n".join(lines) + ("\n" if lines else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
