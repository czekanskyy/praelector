#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the portable release archive from the Tauri bundle output (NF-11)."""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sys
import tarfile
import tomllib
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DESKTOP_DIR = Path("apps") / "desktop"
CARGO_TOML = DESKTOP_DIR / "Cargo.toml"
BUNDLE_DIR = DESKTOP_DIR / "target" / "release" / "bundle"
DIST_DIR = Path("dist")
CHUNK = 1 << 20

# Fixed metadata in both archive formats: the artifact a tag produces must be
# byte-identical no matter which runner built it or when.
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
TAR_MTIME = 0

EXECUTABLE_SUFFIXES = frozenset({".exe", ".appimage", ".sh", ".bin"})


@dataclass(frozen=True)
class Target:
    name: str
    suffix: str  # ".zip" | ".tar.gz"


TARGETS: dict[str, Target] = {
    "windows-x64": Target("windows-x64", ".zip"),
    "linux-x64": Target("linux-x64", ".tar.gz"),
}


class PortableError(RuntimeError):
    """A missing prerequisite; reported as exit code 2."""


def read_version(root: Path) -> str:
    cargo = root / CARGO_TOML
    if not cargo.is_file():
        raise PortableError(f"{CARGO_TOML.as_posix()} does not exist")
    try:
        with cargo.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise PortableError(f"cannot read {cargo}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise PortableError(f"cannot parse {cargo}: {exc}") from exc

    package = data.get("package") or {}
    version = package.get("version")
    if isinstance(version, str) and version:
        return version
    if isinstance(version, dict) and version.get("workspace"):
        workspace_toml = root / "Cargo.toml"
        if not workspace_toml.is_file():
            raise PortableError(
                f"{CARGO_TOML.as_posix()} inherits its version from the workspace but "
                f"{workspace_toml} does not exist"
            )
        with workspace_toml.open("rb") as handle:
            inherited = tomllib.load(handle)
        value = ((inherited.get("workspace") or {}).get("package") or {}).get("version")
        if isinstance(value, str) and value:
            return value
        raise PortableError(f"{workspace_toml} declares no [workspace.package] version")
    raise PortableError(f"{CARGO_TOML.as_posix()} declares no [package] version")


def is_executable(path: Path) -> bool:
    if path.suffix.lower() in EXECUTABLE_SUFFIXES:
        return True
    return bool(path.stat().st_mode & 0o111)


def collect(root: Path) -> list[tuple[str, Path]]:
    bundle = root / BUNDLE_DIR
    if not bundle.is_dir():
        raise PortableError(
            f"{BUNDLE_DIR.as_posix()} does not exist. Run `pnpm tauri build "
            f"--bundles <target>` first; this script only repackages what the "
            f"bundler produced."
        )
    entries: list[tuple[str, Path]] = []
    for path in bundle.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        entries.append((path.relative_to(bundle).as_posix(), path))
    if not entries:
        raise PortableError(f"{BUNDLE_DIR.as_posix()} contains no files")
    return sorted(entries, key=lambda item: item[0])


def write_zip(archive: Path, entries: Sequence[tuple[str, Path]]) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for arcname, path in entries:
            info = zipfile.ZipInfo(arcname, date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # unix: keeps the mode bits meaningful on both hosts
            info.external_attr = (0o755 if is_executable(path) else 0o644) << 16
            with path.open("rb") as source, bundle.open(info, "w") as destination:
                shutil.copyfileobj(source, destination, CHUNK)


def write_tar(archive: Path, entries: Sequence[tuple[str, Path]]) -> None:
    with (
        archive.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as bundle,
    ):
        for arcname, path in entries:
            info = tarfile.TarInfo(arcname)
            info.size = path.stat().st_size
            info.mtime = TAR_MTIME
            info.mode = 0o755 if is_executable(path) else 0o644
            info.type = tarfile.REGTYPE
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with path.open("rb") as source:
                bundle.addfile(info, source)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="make_portable.py",
        description=(
            "Repackage apps/desktop/target/release/bundle/** into "
            "dist/Praelector_<version>_<os>_portable.<ext>. The archive is "
            "reproducible: fixed timestamps, owners and modes."
        ),
        epilog="exit codes: 0 written, 1 write failure, 2 missing input",
    )
    parser.add_argument(
        "--os",
        dest="target",
        required=True,
        choices=sorted(TARGETS),
        help="artifact target, matching the release.yml matrix",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the resolved plan and the files that would be packed, then exit",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (default: the parent of scripts/)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root: Path = args.root.resolve()
    target = TARGETS[args.target]

    try:
        version = read_version(root)
        entries = collect(root)
    except PortableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    archive_name = f"Praelector_{version}_{target.name}_portable{target.suffix}"
    destination = root / DIST_DIR / archive_name

    if args.list:
        print(f"version : {version}")
        print(f"target  : {target.name}")
        print(f"source  : {BUNDLE_DIR.as_posix()}/")
        print(f"output  : {destination.relative_to(root).as_posix()}")
        total = 0
        for arcname, path in entries:
            size = path.stat().st_size
            total += size
            mode = "0755" if is_executable(path) else "0644"
            print(f"  {mode} {size:>12,}  {arcname}")
        print(f"files: {len(entries)}, {total:,} bytes uncompressed")
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        if target.suffix == ".zip":
            write_zip(destination, entries)
        else:
            write_tar(destination, entries)
    except OSError as exc:
        print(f"error: cannot write {destination}: {exc}", file=sys.stderr)
        return 1

    print(
        f"ok: {destination.relative_to(root).as_posix()} "
        f"({len(entries)} file(s), {destination.stat().st_size:,} bytes)"
    )
    if os.name == "nt" and target.suffix != ".zip":
        print(
            "note: a linux-x64 tar.gz was produced on Windows; file modes are "
            "guessed from the extension",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
