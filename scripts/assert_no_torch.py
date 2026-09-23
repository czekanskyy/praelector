#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when a uv lockfile resolves anything from the torch stack (PLAN.md D-03)."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every `torch*` / `pytorch*` distribution on PyPI is the framework or one of its
# first-party satellites, so a bare prefix test is the fail-closed choice: a new
# satellite package is denied until a human decides it is safe.
TORCH_PREFIXES = ("torch", "pytorch")

TRITON_RE = re.compile(r"^(?:pytorch-)?triton(?:$|[-_.])", re.IGNORECASE)
NVIDIA_RE = re.compile(r"^nvidia[-_.]", re.IGNORECASE)

# `nvidia-ml-py` is a pure-Python ctypes binding for NVML and a documented core
# dependency (PLAN.md §11.1); it ships no CUDA runtime. Every other `nvidia-*`
# wheel on PyPI does, so the exception is an explicit, reviewable list.
NVIDIA_ALLOWED = frozenset({"nvidia-ml-py", "nvidia-ml-py3"})


@dataclass(frozen=True)
class Violation:
    lockfile: str
    name: str
    version: str
    reason: str


def forbidden_reason(name: str) -> str | None:
    lowered = name.lower()
    if lowered in NVIDIA_ALLOWED:
        return None
    if lowered.startswith(TORCH_PREFIXES):
        return "torch distribution"
    if TRITON_RE.match(lowered):
        return "Triton kernel compiler (torch dependency)"
    if NVIDIA_RE.match(lowered):
        return "NVIDIA CUDA runtime wheel"
    return None


def scan_lockfile(lockfile: Path, label: str) -> list[Violation]:
    with lockfile.open("rb") as handle:
        data = tomllib.load(handle)

    packages = data.get("package")
    if packages is None:
        return []
    if not isinstance(packages, list):
        raise TypeError(f"{label}: 'package' is not an array of tables")

    violations: list[Violation] = []
    for entry in packages:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        reason = forbidden_reason(name)
        if reason is None:
            continue
        version = entry.get("version")
        violations.append(
            Violation(
                lockfile=label,
                name=name,
                version=version if isinstance(version, str) else "?",
                reason=reason,
            )
        )
    return violations


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="assert_no_torch.py",
        description=(
            "Assert that the given uv lockfiles resolve no torch, Triton or NVIDIA "
            "CUDA-runtime package. The engine core lock must stay torch-free so the "
            "shipped installer stays small and vendor-neutral (D-03, D-04)."
        ),
        epilog="exit codes: 0 clean, 1 torch found, 2 usage or missing input",
    )
    parser.add_argument(
        "lockfiles",
        nargs="+",
        metavar="LOCKFILE",
        help="path to a uv.lock file, relative to --root or absolute",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root that relative lockfile paths resolve against",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root: Path = args.root.resolve()

    missing: list[str] = []
    violations: list[Violation] = []
    scanned: list[str] = []

    for raw in args.lockfiles:
        candidate = Path(raw)
        lockfile = candidate if candidate.is_absolute() else root / candidate
        label = str(candidate)
        if not lockfile.is_file():
            missing.append(label)
            continue
        try:
            violations.extend(scan_lockfile(lockfile, label))
        except (tomllib.TOMLDecodeError, TypeError, ValueError, OSError) as exc:
            print(f"error: cannot parse {label}: {exc}", file=sys.stderr)
            return 2
        scanned.append(label)

    if missing:
        for label in missing:
            print(
                f"error: lockfile not found: {label} (looked in {root})",
                file=sys.stderr,
            )
        print(
            "error: refusing to pass a lockfile that does not exist; run "
            "`uv lock --project <dir>` or fix the path",
            file=sys.stderr,
        )
        return 2

    if violations:
        print(
            f"FAIL: {len(violations)} torch-stack package(s) resolved in the core lock",
            file=sys.stderr,
        )
        for item in violations:
            print(
                f"  {item.lockfile}: {item.name} {item.version} — {item.reason}",
                file=sys.stderr,
            )
        print(
            "  the engine core lock must never resolve torch (D-03); move it to an "
            "engine-tts extra",
            file=sys.stderr,
        )
        return 1

    print(f"ok: no torch stack in {len(scanned)} lockfile(s): {', '.join(scanned)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
