# SPDX-License-Identifier: Apache-2.0
"""System capability probes for external CLI tools, keyring, and runtime."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import keyring

from praelector.domain.models import (
    CapabilitiesResponse,
    KeyringProbe,
    RuntimeProbe,
    ToolProbe,
)


def probe_ffmpeg(data_dir: Path | str | None = None) -> ToolProbe:
    """Probe for ffmpeg executable and required filters (loudnorm, aresample)."""
    ffmpeg_cmd = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    ffmpeg_path: str | None = None

    # Check data_dir/bin first, then PATH
    if data_dir is not None:
        bundled = Path(data_dir) / "bin" / ffmpeg_cmd
        if bundled.is_file() and os.access(bundled, os.X_OK):
            ffmpeg_path = str(bundled)

    if ffmpeg_path is None:
        ffmpeg_path = shutil.which(ffmpeg_cmd)

    if not ffmpeg_path:
        return ToolProbe(
            installed=False,
            error="ffmpeg not found in PATH or bundled bin directory",
        )

    try:
        proc = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        version_line = proc.stdout.splitlines()[0] if proc.stdout else "unknown"

        # Check filters
        filters_proc = subprocess.run(
            [ffmpeg_path, "-filters"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        filters_out = filters_proc.stdout
        filters_ok = "loudnorm" in filters_out and "aresample" in filters_out

        return ToolProbe(
            installed=True,
            path=ffmpeg_path,
            version=version_line,
            filters_ok=filters_ok,
        )
    except Exception as err:
        return ToolProbe(
            installed=True,
            path=ffmpeg_path,
            error=str(err),
            filters_ok=False,
        )


def probe_calibre() -> ToolProbe:
    """Probe for Calibre's ebook-convert executable."""
    cmd = "ebook-convert.exe" if sys.platform == "win32" else "ebook-convert"
    calibre_path = shutil.which(cmd)

    if not calibre_path and sys.platform == "win32":
        standard = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Calibre2" / cmd
        if standard.is_file():
            calibre_path = str(standard)

    if not calibre_path:
        return ToolProbe(
            installed=False,
            error="ebook-convert not found in PATH",
        )

    try:
        proc = subprocess.run(
            [calibre_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        version = proc.stdout.strip() or "unknown"
        return ToolProbe(
            installed=True,
            path=calibre_path,
            version=version,
        )
    except Exception as err:
        return ToolProbe(
            installed=True,
            path=calibre_path,
            error=str(err),
        )


def probe_keyring() -> KeyringProbe:
    """Probe OS keyring availability."""
    try:
        kr = keyring.get_keyring()
        name = kr.__class__.__name__
        priority = getattr(kr, "priority", 1)
        available = priority > 0 and "fail" not in name.lower()
        return KeyringProbe(backend=name, available=available)
    except Exception:
        return KeyringProbe(backend="none", available=False)


def probe_runtime(data_dir: Path | str) -> RuntimeProbe:
    """Probe TTS runtime directory for installed worker environments."""
    runtimes_dir = Path(data_dir) / "runtimes"
    runtime_json = runtimes_dir / "runtime.json"
    if runtime_json.is_file():
        try:
            import json

            data = json.loads(runtime_json.read_text(encoding="utf-8"))
            return RuntimeProbe(
                flavour=data.get("flavour", "cpu"),
                ready=data.get("ready", True),
            )
        except Exception:
            pass

    return RuntimeProbe(flavour="none", ready=False)


def probe_all_capabilities(data_dir: Path | str) -> CapabilitiesResponse:
    """Aggregate probe results for external dependencies and platform services."""
    return CapabilitiesResponse(
        ffmpeg=probe_ffmpeg(data_dir),
        calibre=probe_calibre(),
        keyring=probe_keyring(),
        runtime=probe_runtime(data_dir),
        system_info={
            "platform": sys.platform,
            "python": sys.version.split()[0],
        },
    )
