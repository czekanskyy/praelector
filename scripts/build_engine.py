#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Freeze the torch-free engine core with PyInstaller into the desktop resources."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ENGINE_DIR = Path("engine")
ENTRY_SCRIPT = "praelector-engine"
RESOURCES = Path("apps") / "desktop" / "resources"
# Everything PyInstaller produces at build time lives under resources/, which is
# already excluded from the repository (REPO_LAYOUT.md §3).
OUTPUT_DIR = RESOURCES / "engine"
WORK_DIR = RESOURCES / ".engine-build"

DATA_DIR = Path("src") / "praelector" / "text" / "data"
DATA_SUFFIXES = (".txt", ".tsv")
DATA_DEST = "praelector/text/data"

# uvicorn imports its event loop, protocol and lifespan implementations by string
# name at runtime, which no static analysis can see. Without these the frozen
# engine starts and then dies on the first request.
HIDDEN_IMPORTS = (
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
)


class BuildError(RuntimeError):
    """A missing prerequisite; reported as exit code 2."""


@dataclass(frozen=True)
class Plan:
    entry_point: str
    script: Path
    data_files: list[Path]
    command: list[str]


def read_console_script(pyproject: Path) -> str:
    try:
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise BuildError(f"cannot read {pyproject}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise BuildError(f"cannot parse {pyproject}: {exc}") from exc

    scripts = (data.get("project") or {}).get("scripts") or {}
    target = scripts.get(ENTRY_SCRIPT)
    if not isinstance(target, str) or ":" not in target:
        raise BuildError(
            f"{pyproject} does not declare a [project.scripts] entry named "
            f"{ENTRY_SCRIPT!r} pointing at module:callable"
        )
    return target


def module_to_path(engine_dir: Path, entry_point: str) -> Path:
    module = entry_point.split(":", 1)[0]
    relative = Path(*module.split("."))
    candidates = [
        engine_dir / "src" / relative / "__main__.py",
        engine_dir / "src" / relative.with_suffix(".py"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BuildError(
        f"cannot find a module file for {module!r}; looked for "
        + ", ".join(str(c) for c in candidates)
    )


def collect_data_files(engine_dir: Path) -> list[Path]:
    data_root = engine_dir / DATA_DIR
    if not data_root.is_dir():
        return []
    return sorted(
        path
        for path in data_root.iterdir()
        if path.is_file() and path.suffix.lower() in DATA_SUFFIXES
    )


def require_uv(root: Path) -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise BuildError(
            "uv is not on PATH; install it (https://docs.astral.sh/uv/) or run this "
            "script from an environment that has it"
        )
    return uv


def check_pyinstaller(root: Path, uv: str) -> str:
    result = subprocess.run(
        [uv, "run", "--project", str(ENGINE_DIR), "pyinstaller", "--version"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise BuildError(
            "PyInstaller is not available in the engine environment:\n"
            f"{(result.stdout or result.stderr).strip()}\n"
            "add `pyinstaller` to the engine's dev dependency group"
        )
    return (result.stdout or result.stderr).strip()


def build_plan(root: Path) -> Plan:
    engine_dir = root / ENGINE_DIR
    pyproject = engine_dir / "pyproject.toml"
    if not pyproject.is_file():
        raise BuildError(
            f"{ENGINE_DIR.as_posix()}/pyproject.toml does not exist; the engine "
            f"project lands in a later PR of this stacked series"
        )

    entry_point = read_console_script(pyproject)
    script = module_to_path(engine_dir, entry_point)
    data_files = collect_data_files(engine_dir)

    uv = require_uv(root)
    separator = os.pathsep
    command = [
        uv,
        "run",
        "--project",
        str(ENGINE_DIR),
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        ENTRY_SCRIPT,
        "--distpath",
        (WORK_DIR / "dist").as_posix(),
        "--workpath",
        (WORK_DIR / "work").as_posix(),
        "--specpath",
        (WORK_DIR).as_posix(),
        "--paths",
        (engine_dir / "src").as_posix(),
    ]
    for hidden in HIDDEN_IMPORTS:
        command += ["--hidden-import", hidden]
    for data in data_files:
        relative = data.relative_to(engine_dir).as_posix()
        command += ["--add-data", f"{relative}{separator}{DATA_DEST}"]
    command.append(script.relative_to(root).as_posix())

    return Plan(entry_point, script, data_files, command)


def install_output(root: Path) -> Path:
    """Move PyInstaller's `<name>/` tree into resources/engine/."""
    built = root / WORK_DIR / "dist" / ENTRY_SCRIPT
    if not built.is_dir():
        raise BuildError(f"PyInstaller produced no output at {built}")

    target = root / OUTPUT_DIR
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(built), str(target))
    shutil.rmtree(root / WORK_DIR, ignore_errors=True)
    return target


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="build_engine.py",
        description=(
            "Freeze the engine core as a PyInstaller onedir bundle in "
            "apps/desktop/resources/engine, ready for `tauri build` to pick up "
            "(D-04: onedir, never onefile)."
        ),
        epilog="exit codes: 0 built, 1 PyInstaller failed, 2 missing prerequisite",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--onedir", action="store_true", help="run the build")
    mode.add_argument(
        "--check-env",
        action="store_true",
        help="report the resolved plan and prerequisites without building",
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
        plan = build_plan(root)
        if args.check_env:
            version = check_pyinstaller(root, plan.command[0])
            print(f"PyInstaller {version}")
            print(f"entry point : {plan.entry_point}")
            print(f"entry script: {plan.script.relative_to(root).as_posix()}")
            print(f"output      : {OUTPUT_DIR.as_posix()}/")
            print(f"data files  : {len(plan.data_files)}")
            for data in plan.data_files:
                print(f"  {data.relative_to(root).as_posix()} -> {DATA_DEST}/")
            print("would run:")
            print("  " + " ".join(part.replace(str(root), ".") for part in plan.command))
            return 0
        check_pyinstaller(root, plan.command[0])
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"freezing {plan.entry_point} into {OUTPUT_DIR.as_posix()}/ …")
    result = subprocess.run(plan.command, cwd=root, check=False)
    if result.returncode != 0:
        print(
            f"error: PyInstaller exited with {result.returncode}",
            file=sys.stderr,
        )
        return 1

    try:
        target = install_output(root)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    frozen = target / f"{ENTRY_SCRIPT}{'.exe' if os.name == 'nt' else ''}"
    if not frozen.is_file():
        print(f"error: {frozen} is missing from the bundle", file=sys.stderr)
        return 1
    print(f"ok: {target.relative_to(root).as_posix()} contains {frozen.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
