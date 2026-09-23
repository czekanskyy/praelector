# SPDX-License-Identifier: Apache-2.0
"""The ready handshake, exercised against a real subprocess.

This is the contract the Rust ``EngineSupervisor`` depends on (PLAN.md §1.6):
exactly one line on stdout, an OS-assigned port, a graceful shutdown on
``POST /v1/shutdown``, and no secret in any stream.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import TextIO

import httpx

from praelector import SCHEMA_VERSION, __version__
from praelector.__main__ import READY_PREFIX
from praelector.config import (
    ENV_CONFIG_DIR,
    ENV_DATA_DIR,
    ENV_LOG_DIR,
    ENV_LOG_LEVEL,
    ENV_PORT,
    ENV_PROJECTS_DIR,
    ENV_TOKEN,
)
from praelector.security import generate_token

REPO_ROOT = Path(__file__).resolve().parents[3]
STARTUP_TIMEOUT_S = 60.0
SHUTDOWN_TIMEOUT_S = 30.0


def _readline_with_deadline(stream: TextIO, timeout: float) -> str:
    """Read one line without hanging forever if the child never becomes ready."""
    lines: list[str] = []

    def reader() -> None:
        lines.append(stream.readline())

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"no ready line within {timeout}s")
    return lines[0] if lines else ""


def test_ready_handshake_serves_and_shuts_down_cleanly(tmp_path: Path) -> None:
    token = generate_token()
    env = os.environ.copy()
    env.update(
        {
            ENV_TOKEN: token,
            ENV_PORT: "0",
            ENV_LOG_LEVEL: "INFO",
            ENV_DATA_DIR: os.fspath(tmp_path / "data"),
            # Keeps the spawned engine off the developer's real config dir, which
            # it would otherwise read at startup and create on first run.
            ENV_CONFIG_DIR: os.fspath(tmp_path / "config"),
            ENV_LOG_DIR: os.fspath(tmp_path / "logs"),
            ENV_PROJECTS_DIR: os.fspath(tmp_path / "projects"),
        }
    )

    process = subprocess.Popen(
        [sys.executable, "-m", "praelector"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=os.fspath(REPO_ROOT),
    )
    try:
        line = _readline_with_deadline(process.stdout, STARTUP_TIMEOUT_S)
        assert line.startswith(READY_PREFIX), f"expected a ready line, got {line!r}"

        info = json.loads(line.removeprefix(READY_PREFIX))
        assert set(info) == {"port", "pid", "version", "schema"}
        # Not compared to `process.pid`: on Windows the python.exe of a uv-created
        # venv is a trampoline that spawns the real interpreter as a child. The
        # frozen PyInstaller binary the shell launches reports its own pid.
        assert isinstance(info["pid"], int) and info["pid"] != os.getpid()
        assert info["version"] == __version__
        assert info["schema"] == SCHEMA_VERSION
        assert isinstance(info["port"], int) and info["port"] > 0

        base_url = f"http://127.0.0.1:{info['port']}"
        headers = {"Authorization": f"Bearer {token}"}
        with httpx.Client(base_url=base_url, timeout=10.0) as http:
            assert http.get("/v1/health").status_code == 401
            health = http.get("/v1/health", headers=headers)
            assert health.status_code == 200
            assert health.json()["status"] == "ok"
            assert http.post("/v1/shutdown", headers=headers).status_code == 200

        stdout_rest, stderr_rest = process.communicate(timeout=SHUTDOWN_TIMEOUT_S)
        assert process.returncode == 0
        # stdout carries exactly one line, ever.
        assert stdout_rest.strip() == ""
        assert stderr_rest.strip(), "expected JSON logs on stderr"
        assert token not in stderr_rest, "the launch token leaked into the logs"
        for log_line in stderr_rest.strip().splitlines():
            json.loads(log_line)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_a_missing_token_refuses_to_start(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop(ENV_TOKEN, None)
    env[ENV_DATA_DIR] = os.fspath(tmp_path / "data")

    result = subprocess.run(
        [sys.executable, "-m", "praelector"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=os.fspath(REPO_ROOT),
        timeout=60,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert ENV_TOKEN in result.stderr


def test_an_unusable_port_is_reported_not_swallowed(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            ENV_TOKEN: generate_token(),
            ENV_PORT: "99999999",
            ENV_DATA_DIR: os.fspath(tmp_path / "data"),
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "praelector"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=os.fspath(REPO_ROOT),
        timeout=60,
    )
    assert result.returncode == 2
    assert "out of range" in result.stderr


def test_the_served_api_is_usable_end_to_end(tmp_path: Path) -> None:
    """The M0 exit criterion, minus the window: a real process serving the real API.

    Drives version, settings, capabilities, GPU devices and the whole project
    lifecycle over a socket against a spawned engine, then shuts it down. No GPU is
    required — a machine without one still answers ``/v1/gpu/devices`` with the CPU
    pseudo-device (GPU-08).
    """
    token = generate_token()
    projects_dir = tmp_path / "projects"
    env = os.environ.copy()
    env.update(
        {
            ENV_TOKEN: token,
            ENV_PORT: "0",
            ENV_LOG_LEVEL: "INFO",
            ENV_DATA_DIR: os.fspath(tmp_path / "data"),
            # Without this the spawned engine reads AND writes the real user
            # config dir: the settings PUT below would survive into the next run
            # and onto the developer's machine.
            ENV_CONFIG_DIR: os.fspath(tmp_path / "config"),
            ENV_LOG_DIR: os.fspath(tmp_path / "logs"),
            ENV_PROJECTS_DIR: os.fspath(projects_dir),
        }
    )

    process = subprocess.Popen(
        [sys.executable, "-m", "praelector"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=os.fspath(REPO_ROOT),
    )
    try:
        line = _readline_with_deadline(process.stdout, STARTUP_TIMEOUT_S)
        info = json.loads(line.removeprefix(READY_PREFIX))
        headers = {"Authorization": f"Bearer {token}"}

        with httpx.Client(base_url=f"http://127.0.0.1:{info['port']}", timeout=30.0) as http:
            assert http.get("/v1/version", headers=headers).json()["engine"] == __version__

            assert http.get("/v1/settings", headers=headers).json()["language"] == "en"
            updated = http.put(
                "/v1/settings",
                headers=headers,
                json={"language": "pl", "gpu": {"worker_cap": 2}},
            )
            assert updated.status_code == 200
            assert updated.json()["language"] == "pl"
            assert updated.json()["gpu"]["worker_cap"] == 2
            # Merge patch, not replace.
            assert http.get("/v1/settings", headers=headers).json()["gpu"]["allow_cpu"] is True

            capabilities = http.get("/v1/capabilities", headers=headers).json()
            assert set(capabilities["ffmpeg"]) == {"present", "path", "version", "reason"}
            assert capabilities["secret_backend"] in {"keyring", "file", "unavailable"}
            assert "\\" not in capabilities["paths"]["projects_dir"]

            devices = http.get("/v1/gpu/devices", headers=headers).json()
            assert devices["devices"][-1]["vendor"] == "cpu"
            assert devices["vendors"]

            created = http.post("/v1/projects", headers=headers, json={"name": "End to end"})
            assert created.status_code == 201, created.text
            project_id = created.json()["id"]
            assert (projects_dir / project_id / "project.json").is_file()
            assert (projects_dir / project_id / "project.db").is_file()
            assert (projects_dir / project_id / "audio" / "chunks").is_dir()

            listed = http.get("/v1/projects", headers=headers).json()
            assert [entry["id"] for entry in listed["projects"]] == [project_id]

            assert http.post(f"/v1/projects/{project_id}/open", headers=headers).status_code == 200
            assert http.get("/v1/health", headers=headers).json()["project_open"] is True
            # A second engine must not be able to take the same project (JB-06).
            assert (projects_dir / project_id / "project.lock").is_file()
            assert http.post(f"/v1/projects/{project_id}/close", headers=headers).status_code == 204
            assert http.get("/v1/health", headers=headers).json()["project_open"] is False

            deleted = http.delete(
                f"/v1/projects/{project_id}", headers=headers, params={"delete_files": True}
            )
            assert deleted.status_code == 204
            assert not (projects_dir / project_id).exists()

            assert http.post("/v1/shutdown", headers=headers).status_code == 200

        stdout_rest, stderr_rest = process.communicate(timeout=SHUTDOWN_TIMEOUT_S)
        assert process.returncode == 0
        assert stdout_rest.strip() == "", "stdout carries only the ready line"
        assert token not in stderr_rest, "the launch token leaked into the logs"
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
