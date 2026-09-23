# SPDX-License-Identifier: Apache-2.0
"""Engine entry point: bind, announce readiness on stdout, serve.

stdout carries exactly one line — ``PRAELECTOR_READY {json}`` — because the shell
parses stdout to discover the port (PLAN.md §1.6). Everything else, including all
logs, goes to stderr. The socket is bound here rather than by uvicorn so the
announced port is the real one even when the OS assigns it (``port=0``).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import socket
import sys
import threading
from collections.abc import Sequence

import uvicorn

from praelector import SCHEMA_VERSION, __version__
from praelector.app import create_app
from praelector.config import (
    ENV_DATA_DIR,
    ENV_HOST,
    ENV_LOG_LEVEL,
    ENV_PORT,
    ENV_TOKEN,
    ConfigError,
    RuntimeEnv,
    load_runtime_env,
)
from praelector.logging import configure_logging, register_secret
from praelector.state import AppState

logger = logging.getLogger(__name__)

READY_PREFIX = "PRAELECTOR_READY "
PARENT_POLL_INTERVAL_S = 5.0
GRACEFUL_SHUTDOWN_TIMEOUT_S = 10
LISTEN_BACKLOG = 128

#: Annotated ``bool`` so mypy does not narrow it to a literal and then declare the
#: other platform's code path unreachable.
_IS_WINDOWS: bool = sys.platform == "win32"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="praelector-engine",
        description="Praelector engine sidecar. Normally launched by the desktop shell.",
    )
    parser.add_argument("--version", action="version", version=_version_line())
    parser.add_argument("--host", help=f"override ${ENV_HOST} (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help=f"override ${ENV_PORT} (0 = OS-assigned)")
    parser.add_argument("--token", help=f"override ${ENV_TOKEN}")
    parser.add_argument("--data-dir", help=f"override ${ENV_DATA_DIR}")
    parser.add_argument("--log-level", help=f"override ${ENV_LOG_LEVEL}")
    parser.add_argument(
        "--plain-logs",
        action="store_true",
        help="human-readable logs instead of JSON, for running by hand",
    )
    return parser


def _version_line() -> str:
    return f"praelector-engine {__version__} (schema {SCHEMA_VERSION})"


def _merged_environ(args: argparse.Namespace) -> dict[str, str]:
    """Environment variables win over nothing; explicit CLI flags win over both."""
    env = dict(os.environ)
    overrides = {
        ENV_HOST: args.host,
        ENV_PORT: None if args.port is None else str(args.port),
        ENV_TOKEN: args.token,
        ENV_DATA_DIR: args.data_dir,
        ENV_LOG_LEVEL: args.log_level,
    }
    for key, value in overrides.items():
        if value is not None:
            env[key] = value
    return env


def _bind(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        sock.listen(LISTEN_BACKLOG)
    except OSError:
        sock.close()
        raise
    return sock


def _announce_ready(port: int) -> None:
    """The single stdout line the shell waits for, key order included."""
    payload = {
        "port": port,
        "pid": os.getpid(),
        "version": __version__,
        "schema": SCHEMA_VERSION,
    }
    print(READY_PREFIX + json.dumps(payload, separators=(",", ":")), flush=True)


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if _IS_WINDOWS:
        return _windows_process_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _windows_process_alive(pid: int) -> bool:
    """Exit-code probe via ``OpenProcess``/``GetExitCodeProcess``.

    ``ctypes.windll`` is reached through ``getattr`` and the platform flag is a
    plain ``bool``: typeshed gates ``windll`` on ``sys.platform == "win32"``, so a
    direct check would make mypy declare the POSIX path unreachable on Windows
    and the Windows path untypeable on Linux.
    """
    import ctypes

    process_query_limited_information = 0x1000
    still_active = 259

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        # Cannot probe: assume the parent lives rather than exit on a guess.
        return True

    kernel32 = windll.kernel32
    # A HANDLE is a pointer; without restype ctypes truncates it to 32 bits.
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return bool(exit_code.value == still_active)
    finally:
        kernel32.CloseHandle(handle)


def _watch_parent(env: RuntimeEnv, state: AppState, stop: threading.Event) -> None:
    """Portable orphan backstop: exit when the shell is gone and no job is running.

    The platform-specific mechanisms (Windows Job Object, POSIX process group)
    are the primary defence; this catches the case where the shell died in a way
    that skipped them. A running job is allowed to finish first — killing it
    would waste rendered audio for no benefit.
    """
    pid = env.parent_pid
    if pid is None:
        return
    while not stop.wait(PARENT_POLL_INTERVAL_S):
        if _process_alive(pid):
            continue
        if state.active_job_id is not None:
            logger.warning(
                "parent process is gone but a job is active; staying up",
                extra={"parent_pid": pid, "job_id": state.active_job_id},
            )
            continue
        logger.warning("parent process is gone; exiting", extra={"parent_pid": pid})
        state.request_shutdown()
        return


def _run(env: RuntimeEnv) -> int:
    state = AppState.create(env)
    app = create_app(env, state=state)

    try:
        sock = _bind(env.host, env.port)
    except OSError as exc:
        logger.error("cannot bind", extra={"host": env.host, "port": env.port, "error": str(exc)})
        print(f"praelector-engine: cannot bind {env.host}:{env.port}: {exc}", file=sys.stderr)
        return 2

    port = int(sock.getsockname()[1])
    config = uvicorn.Config(
        app,
        host=env.host,
        port=port,
        log_config=None,
        access_log=False,
        server_header=False,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_TIMEOUT_S,
    )
    server = uvicorn.Server(config)
    state.server = server

    _announce_ready(port)
    logger.info(
        "listening",
        extra={"host": env.host, "port": port, "parent_pid": env.parent_pid},
    )

    stop = threading.Event()
    if env.parent_pid is not None:
        threading.Thread(
            target=_watch_parent,
            args=(env, state, stop),
            name="parent-watchdog",
            daemon=True,
        ).start()

    try:
        asyncio.run(server.serve(sockets=[sock]))
    finally:
        stop.set()
        with contextlib.suppress(OSError):
            sock.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        env = load_runtime_env(_merged_environ(args))
    except ConfigError as exc:
        print(f"praelector-engine: {exc}", file=sys.stderr)
        return 2

    configure_logging(
        env.log_level,
        log_file=env.paths.log_dir / "engine.log",
        json_output=not args.plain_logs,
    )
    register_secret(env.token)
    return _run(env)


if __name__ == "__main__":
    raise SystemExit(main())
