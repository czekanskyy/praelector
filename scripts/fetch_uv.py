#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch the pinned uv binary that ships inside the desktop app (D-04)."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = Path("apps") / "desktop" / "resources" / "bin"
RELEASE_URL = "https://github.com/astral-sh/uv/releases/download/{version}/{asset}"

UV_VERSION = "0.12.13"


@dataclass(frozen=True)
class Asset:
    filename: str
    sha256: str
    binaries: tuple[str, ...]


# Checksums are the ones published alongside each asset on the release page. Bumping
# UV_VERSION means bumping these too; an empty string is refused at run time rather
# than silently trusted.
ASSETS: dict[str, Asset] = {
    "x86_64-pc-windows-msvc": Asset(
        "uv-x86_64-pc-windows-msvc.zip",
        "a86c9dc7bad9b03f388583b7187c05fe9951c2e0d392217e8fd43d97787f6ec2",
        ("uv.exe", "uvx.exe"),
    ),
    "x86_64-unknown-linux-gnu": Asset(
        "uv-x86_64-unknown-linux-gnu.tar.gz",
        "745765a3b6e360ad76743599ae5c42e9278c7edf8bbff9fc76d05bf2623a04dd",
        ("uv", "uvx"),
    ),
}

CHUNK = 1 << 20


class FetchError(RuntimeError):
    """A missing prerequisite or a failed integrity check; reported as exit code 2."""


def host_triple() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        if system == "windows":
            return "x86_64-pc-windows-msvc"
        if system == "linux":
            return "x86_64-unknown-linux-gnu"
    # macOS produces no release artifact (D-23) and v1 ships no arm64 build.
    raise FetchError(
        f"no pinned uv asset for {system}/{machine}; supported targets are "
        + ", ".join(sorted(ASSETS))
    )


def asset_for(triple: str) -> Asset:
    try:
        return ASSETS[triple]
    except KeyError:
        raise FetchError(
            f"no pinned uv asset for target {triple!r}; known targets: " + ", ".join(sorted(ASSETS))
        ) from None


def download(url: str, destination: Path) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "praelector-release"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            total = int(response.headers.get("Content-Length") or 0)
            written = 0
            with destination.open("wb") as handle:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    handle.write(block)
                    written += len(block)
    except urllib.error.URLError as exc:
        raise FetchError(f"download failed for {url}: {exc}") from exc
    except OSError as exc:
        raise FetchError(f"cannot write {destination}: {exc}") from exc
    return total or written


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(archive: Path, asset: Asset, allow_unverified: bool) -> None:
    actual = sha256_of(archive)
    if not asset.sha256:
        if not allow_unverified:
            raise FetchError(
                f"checksum not pinned for this version: uv {UV_VERSION} "
                f"({asset.filename}) has no sha256 in ASSETS. Add the value from "
                f"{archive.name}.sha256 on the release page, or pass "
                f"--allow-unverified to proceed without integrity checking."
            )
        print(
            f"WARNING: no checksum pinned for {asset.filename}; downloaded {actual} is UNVERIFIED",
            file=sys.stderr,
        )
        return
    if actual != asset.sha256:
        raise FetchError(
            f"sha256 mismatch for {asset.filename}:\n  expected {asset.sha256}\n  actual   {actual}"
        )
    print(f"sha256 ok: {actual}")


def extract(archive: Path, asset: Asset, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    wanted = set(asset.bilenames)
    written: list[Path] = []

    def store(name: str, payload: bytes) -> None:
        target = dest / name
        target.write_bytes(payload)
        if os.name != "nt":
            target.chmod(0o755)
        written.append(target)

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                if info.is_dir() or Path(info.filename).name not in wanted:
                    continue
                store(Path(info.filename).name, bundle.read(info))
    else:
        # Members are read by exact basename and written by hand: extractall() would
        # trust whatever paths the archive declares.
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                name = Path(member.name).name
                if not member.isfile() or name not in wanted:
                    continue
                handle = bundle.extractfile(member)
                if handle is None:
                    continue
                with handle:
                    store(name, handle.read())

    missing = wanted - {path.name for path in written}
    if missing:
        raise FetchError(f"{asset.filename} did not contain {', '.join(sorted(missing))}")
    return written


def installed_version(binary: Path) -> str | None:
    if not binary.is_file():
        return None
    result = subprocess.run(
        [str(binary), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return None
    parts = (result.stdout or "").split()
    return parts[1] if len(parts) > 1 else None


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fetch_uv.py",
        description=(
            f"Download the pinned uv {UV_VERSION} release asset for the host "
            f"platform into {DEFAULT_DEST.as_posix()}/. The app uses this bundled "
            f"uv to provision the TTS runtime (D-04), so the version and its "
            f"checksum are pinned here and nowhere else."
        ),
        epilog="exit codes: 0 fetched or already current, 2 download/integrity failure",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "require the sha256 to be pinned and to match; this is what release.yml "
            "runs. Without it an unpinned version is refused too, unless "
            "--allow-unverified is given."
        ),
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="proceed when no checksum is pinned, printing a loud warning",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what would be downloaded and exit, without touching the network",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even when a matching uv is already present",
    )
    parser.add_argument(
        "--target",
        default=None,
        metavar="TRIPLE",
        help=f"asset target (default: host; one of {', '.join(sorted(ASSETS))})",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help=f"destination directory (default: <root>/{DEFAULT_DEST.as_posix()})",
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

    try:
        triple = args.target or host_triple()
        asset = asset_for(triple)
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    dest: Path = (args.dest or (root / DEFAULT_DEST)).resolve()
    executable = dest / asset.binaries[0]
    url = RELEASE_URL.format(version=UV_VERSION, asset=asset.filename)

    if args.check:
        print(f"uv version : {UV_VERSION}")
        print(f"target     : {triple}")
        print(f"asset      : {asset.filename}")
        print(f"url        : {url}")
        print(f"sha256     : {asset.sha256 or '(not pinned)'}")
        print(f"destination: {dest}")
        print(f"binaries   : {', '.join(asset.binaries)}")
        print(f"installed  : {installed_version(executable) or '(none)'}")
        return 0

    if not args.force:
        current = installed_version(executable)
        if current == UV_VERSION:
            print(f"ok: uv {current} already present at {executable}")
            return 0

    if args.verify and not asset.sha256 and not args.allow_unverified:
        print(
            f"error: checksum not pinned for uv {UV_VERSION} ({asset.filename}); "
            f"--verify refuses to install an unverified binary",
            file=sys.stderr,
        )
        return 2

    print(f"downloading {url}")
    with tempfile.TemporaryDirectory(prefix="praelector-uv-") as tmp:
        archive = Path(tmp) / asset.filename
        try:
            size = download(url, archive)
            print(f"downloaded {size:,} bytes to a temporary directory")
            verify(archive, asset, args.allow_unverified)
            written = extract(archive, asset, dest)
        except FetchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    for path in written:
        print(f"installed {path}")
    print(f"ok: uv {UV_VERSION} for {triple} is in {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
