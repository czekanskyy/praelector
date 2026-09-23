#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the Praelector engine sidecar and the UI together for local development.

Two development shapes exist because they exercise different code paths:

* browser mode (default) runs the engine on a *fixed* port with a fixed dev
  token and starts Vite, so the UI can be developed without a Rust toolchain.
  The engine endpoint is written to ``apps/ui/.env.local`` because there is no
  Tauri ``engine_endpoint`` command to ask.
* desktop mode delegates to ``pnpm tauri dev``, which spawns the engine through
  the real ``EngineSupervisor`` (ready handshake, health poll, Job Object /
  process group teardown) and is therefore the only mode that tests §1.6 of
  docs/plan/PLAN.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = ROOT / "engine"
UI_DIR = ROOT / "apps" / "ui"
DESKTOP_DIR = ROOT / "apps" / "desktop"

DEV_HOST = "127.0.0.1"
DEV_PORT = 8787
UI_PORT = 1420
DEV_TOKEN = "praelector-dev-token-not-a-secret"
UI_ENV_FILE = UI_DIR / ".env.local"
DEV_DATA_DIR = ROOT / ".dev" / "data"

READY_PREFIX = "PRAELECTOR_READY "


def _which(name: str) -> str:
    """Resolve an executable, appending .cmd/.exe on Windows where needed."""
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        for suffix in (".cmd", ".exe", ".bat"):
            found = shutil.which(name + suffix)
            if found:
                return found
    raise SystemExit(f"{name} is not on PATH; see docs/dev-setup.md")


def _engine_command() -> list[str]:
    override = os.environ.get("PRAELECTOR_ENGINE_CMD")
    if override:
        return override.split()
    return [_which("uv"), "run", "--project", "engine", "praelector-engine"]


def _engine_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PRAELECTOR_TOKEN": DEV_TOKEN,
            "PRAELECTOR_HOST": DEV_HOST,
            "PRAELECTOR_PORT": str(DEV_PORT),
            "PRAELECTOR_DATA_DIR": str(DEV_DATA_DIR),
            "PRAELECTOR_LOG_LEVEL": env.get("PRAELECTOR_LOG_LEVEL", "DEBUG"),
            "PRAELECTOR_PARENT_PID": str(os.getpid()),
        }
    )
    return env


def _spawn(
    cmd: Sequence[str],
    env: dict[str, str],
    cwd: Path | None,
    *,
    pipe_stdout: bool = False,
) -> subprocess.Popen[str]:
    kwargs: dict[str, object] = {
        "cwd": str(cwd) if cwd else str(ROOT),
        "env": env,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "stdout": subprocess.PIPE if pipe_stdout else None,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(list(cmd), **kwargs)


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), 15)
            proc.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        proc.kill()


def _watch_ready(proc: subprocess.Popen[str], stop: threading.Event) -> None:
    """Echo engine stdout, and say so once the READY line arrives."""
    if proc.stdout is None:
        return
    for line in proc.stdout:
        if stop.is_set():
            break
        if line.startswith(READY_PREFIX):
            try:
                info = json.loads(line[len(READY_PREFIX) :])
            except json.JSONDecodeError:
                info = {}
            port = info.get("port", DEV_PORT)
            print(
                f"\n  engine ready  http://{DEV_HOST}:{port}/v1  "
                f"(version {info.get('version', '?')})\n",
                flush=True,
            )
        else:
            print(f"  engine | {line.rstrip()}", flush=True)


def _announce_ui_when_up(url: str) -> None:
    if _wait_for_ui(url):
        print(f"\n  ui ready      {url}\n", flush=True)


def _wait_for_ui(url: str, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.4)
    return False


def _write_ui_env() -> None:
    """Point the browser-mode UI at the fixed dev engine endpoint."""
    UI_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# Written by scripts/dev.py for browser-mode development. Gitignored.\n"
        f"VITE_ENGINE_URL=http://{DEV_HOST}:{DEV_PORT}\n"
        f"VITE_ENGINE_TOKEN={DEV_TOKEN}\n"
    )
    if UI_ENV_FILE.exists() and UI_ENV_FILE.read_text(encoding="utf-8") == body:
        return
    UI_ENV_FILE.write_text(body, encoding="utf-8", newline="\n")


def _require(path: Path, hint: str) -> None:
    if not path.exists():
        raise SystemExit(f"{path} does not exist yet. {hint}")


def run_browser_mode(engine_only: bool, ui_only: bool) -> int:
    procs: list[tuple[str, subprocess.Popen[str]]] = []
    stop = threading.Event()

    if not ui_only:
        _require(ENGINE_DIR / "pyproject.toml", "The engine lands in PR 2 (feat/engine-skeleton).")
        DEV_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cmd = _engine_command()
        print(f"starting engine: {' '.join(cmd)}", flush=True)
        engine = _spawn(cmd, _engine_env(), ROOT, pipe_stdout=True)
        procs.append(("engine", engine))
        threading.Thread(target=_watch_ready, args=(engine, stop), daemon=True).start()

    if not engine_only:
        _require(UI_DIR / "package.json", "The UI lands in PR 4 (feat/ui-shell).")
        _write_ui_env()
        cmd = [_which("pnpm"), "-F", "ui", "dev", "--port", str(UI_PORT), "--strictPort"]
        print(f"starting ui:     {' '.join(cmd)}", flush=True)
        ui = _spawn(cmd, os.environ.copy(), ROOT)
        procs.append(("ui", ui))
        threading.Thread(
            target=_announce_ui_when_up,
            args=(f"http://localhost:{UI_PORT}",),
            daemon=True,
        ).start()

    if not procs:
        raise SystemExit("nothing to run: --engine-only and --ui-only are mutually exclusive")

    try:
        while True:
            for name, proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"{name} exited with code {code}", flush=True)
                    return code
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
        return 0
    finally:
        stop.set()
        for _, proc in procs:
            _kill_tree(proc)


def run_desktop_mode() -> int:
    _require(
        DESKTOP_DIR / "tauri.conf.json", "The desktop shell lands in PR 3 (feat/desktop-shell)."
    )
    _require(UI_DIR / "package.json", "The UI lands in PR 4 (feat/ui-shell).")
    cmd = [_which("pnpm"), "tauri", "dev"]
    print(f"starting desktop: {' '.join(cmd)}", flush=True)
    proc = _spawn(cmd, os.environ.copy(), ROOT)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
        _kill_tree(proc)
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--desktop",
        action="store_true",
        help="run the Tauri app, which supervises the engine itself",
    )
    mode.add_argument("--engine-only", action="store_true", help="run just the engine sidecar")
    mode.add_argument("--ui-only", action="store_true", help="run just the Vite dev server")
    args = parser.parse_args(argv)

    if args.desktop:
        return run_desktop_mode()
    return run_browser_mode(engine_only=args.engine_only, ui_only=args.ui_only)


if __name__ == "__main__":
    raise SystemExit(main())
