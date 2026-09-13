# SPDX-License-Identifier: Apache-2.0
"""Praelector engine entry point, socket binding, ready handshake, and parent supervision."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import socket
import sys
import threading
import time

import uvicorn

import praelector
from praelector.api.v1.version import SCHEMA_VERSION
from praelector.app import create_app
from praelector.config import get_settings

logger = logging.getLogger("praelector.main")


def is_process_alive(pid: int) -> bool:
    """Check whether a process with given PID is still running."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return False
        process_query_limited_information = 0x1000
        kernel32 = windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        still_active = 259
        return bool(exit_code.value == still_active)
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def start_parent_watchdog(parent_pid: int | None, poll_interval_s: float = 5.0) -> None:
    """Watch parent PID and exit cleanly if parent terminates."""
    if not parent_pid:
        return

    def watchdog() -> None:
        while True:
            time.sleep(poll_interval_s)
            if not is_process_alive(parent_pid):
                # Parent exited; terminate to prevent orphan processes
                sys.exit(0)

    t = threading.Thread(target=watchdog, daemon=True, name="ParentWatchdog")
    t.start()


def main() -> int:
    """Main engine sidecar entry point."""
    parser = argparse.ArgumentParser(description="Praelector engine core sidecar")
    parser.add_argument("--port", type=int, default=None, help="Port to bind (0 for ephemeral)")
    parser.add_argument("--host", type=str, default=None, help="Host to bind")
    parser.add_argument("--token", type=str, default=None, help="Bearer authentication token")
    args = parser.parse_args()

    settings = get_settings()
    if args.port is not None:
        settings.port = args.port
    if args.host is not None:
        settings.host = args.host
    if args.token is not None:
        settings.token = args.token

    # Start parent watchdog if supervisor provided parent PID
    start_parent_watchdog(settings.parent_pid)

    app = create_app(settings)

    # Bind loopback socket (ephemeral port support)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((settings.host, settings.port))
    bound_port = sock.getsockname()[1]

    # Ready handshake line to stdout (PLAN.md §1.6)
    ready_data = {
        "port": bound_port,
        "pid": os.getpid(),
        "version": praelector.__version__,
        "schema": SCHEMA_VERSION,
    }
    sys.stdout.write(f"PRAELECTOR_READY {json.dumps(ready_data)}\n")
    sys.stdout.flush()

    config = uvicorn.Config(
        app=app,
        log_config=None,  # Use praelector structured logging
        access_log=False,
    )
    server = uvicorn.Server(config=config)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
