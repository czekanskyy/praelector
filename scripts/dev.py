# SPDX-License-Identifier: Apache-2.0
"""Development launcher for Praelector (Engine + Vite + Tauri)."""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn


def find_repo_root() -> Path:
    """Find the root repository directory containing engine/pyproject.toml."""
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / "engine" / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


def resolve_binary(name: str) -> str:
    """Resolve executable path across platforms (e.g. pnpm -> pnpm.cmd on Windows)."""
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if sys.platform == "win32":
        for ext in [".cmd", ".exe", ".bat"]:
            resolved = shutil.which(f"{name}{ext}")
            if resolved:
                return resolved
    return name


def terminate_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    """Gracefully terminate a list of child processes."""
    for proc in processes:
        if proc.poll() is None:
            with contextlib.suppress(OSError):
                proc.terminate()

    deadline = time.time() + 3.0
    for proc in processes:
        if proc.poll() is None:
            remaining = max(0.0, deadline - time.time())
            try:
                proc.wait(timeout=remaining)
            except (subprocess.TimeoutExpired, OSError):
                with contextlib.suppress(OSError):
                    proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Praelector development environment launcher.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--engine-only",
        action="store_true",
        help="Run only the FastAPI sidecar engine.",
    )
    group.add_argument(
        "--ui-only",
        action="store_true",
        help="Run only the Vite UI dev server.",
    )
    group.add_argument(
        "--browser",
        action="store_true",
        help="Run engine and Vite UI concurrently for browser development (no Tauri desktop shell).",
    )

    args = parser.parse_args()

    repo_root = find_repo_root()
    env = dict(os.environ)
    env["PRAELECTOR_WORKSPACE_ROOT"] = str(repo_root)
    env["PYTHONUNBUFFERED"] = "1"

    pnpm_bin = resolve_binary("pnpm")
    uv_bin = resolve_binary("uv")

    processes: list[subprocess.Popen[bytes]] = []

    def handle_signal(_sig: int, _frame: object | None) -> NoReturn:
        print("\nStopping Praelector development environment...")
        terminate_processes(processes)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    try:
        if args.engine_only:
            print("🚀 Starting Praelector engine only...")
            cmd = [uv_bin, "run", "--project", "engine", "praelector-engine"]
            proc = subprocess.Popen(cmd, cwd=repo_root, env=env)
            processes.append(proc)
            return proc.wait()

        if args.ui_only:
            print("🚀 Starting Praelector UI dev server only...")
            cmd = [pnpm_bin, "-F", "ui", "dev"]
            proc = subprocess.Popen(cmd, cwd=repo_root, env=env)
            processes.append(proc)
            return proc.wait()

        if args.browser:
            print("🚀 Starting Praelector in browser mode (Engine + Vite)...")
            engine_cmd = [uv_bin, "run", "--project", "engine", "praelector-engine"]
            ui_cmd = [pnpm_bin, "-F", "ui", "dev"]

            engine_proc = subprocess.Popen(engine_cmd, cwd=repo_root, env=env)
            processes.append(engine_proc)

            ui_proc = subprocess.Popen(ui_cmd, cwd=repo_root, env=env)
            processes.append(ui_proc)

            while True:
                time.sleep(0.5)
                for p in processes:
                    if p.poll() is not None:
                        print(f"Process {p.args} exited with code {p.returncode}")
                        terminate_processes(processes)
                        return p.returncode

        # Default: Full desktop development mode (Engine + Vite + Tauri)
        print("🚀 Starting Praelector desktop development environment...")
        print(f"📂 Workspace root: {repo_root}")
        desktop_cmd = [pnpm_bin, "tauri", "dev"]
        proc = subprocess.Popen(desktop_cmd, cwd=repo_root, env=env)
        processes.append(proc)
        return proc.wait()

    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
        terminate_processes(processes)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
