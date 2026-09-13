# SPDX-License-Identifier: Apache-2.0
"""Calibre ebook-convert invocation and conversion (EB-03, EB-09, NF-04)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from praelector.errors import AppError
from praelector.probes import probe_calibre

__all__ = [
    "convert_with_calibre",
    "find_calibre_binary",
    "get_calibre_install_hint_key",
    "probe_calibre",
]


def get_calibre_install_hint_key() -> str:
    """Get i18n key for OS-specific Calibre installation instructions."""
    if sys.platform == "win32":
        return "calibre_missing_windows"
    if sys.platform == "darwin":
        return "calibre_missing_macos"
    return "calibre_missing_linux"


def find_calibre_binary(configured_path: str | None = None) -> str:
    """Find ebook-convert binary from configured path, PATH, or standard OS locations.

    Raises:
        AppError: with code 'ebook.calibre_missing' if not found.
    """
    cmd = "ebook-convert.exe" if sys.platform == "win32" else "ebook-convert"

    # 1. Configured path
    if configured_path:
        p = Path(configured_path)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
        if p.is_dir():
            cand = p / cmd
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)

    # 2. PATH or standard probes
    probe = probe_calibre()
    if probe.installed and probe.path:
        return probe.path

    # 3. Extra standard search paths
    candidates: list[Path] = []
    if sys.platform == "win32":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        localapp = os.environ.get("LOCALAPPDATA", "")
        candidates.extend(
            [
                Path(pf) / "Calibre2" / cmd,
                Path(pf86) / "Calibre2" / cmd,
                Path(localapp) / "Programs" / "Calibre2" / cmd,
            ]
        )
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/calibre.app/Contents/MacOS/ebook-convert"))
    else:
        candidates.extend(
            [
                Path("/usr/bin/ebook-convert"),
                Path("/usr/local/bin/ebook-convert"),
                Path.home() / ".local/bin/ebook-convert",
            ]
        )

    for cand in candidates:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)

    raise AppError(
        "ebook.calibre_missing",
        status_code=422,
        detail={
            "install_hint_key": get_calibre_install_hint_key(),
            "os": sys.platform,
            "message": "Calibre ebook-convert is required to convert this format but was not found.",
        },
    )


def convert_with_calibre(
    input_path: Path | str,
    output_epub_path: Path | str | None = None,
    calibre_path: str | None = None,
) -> Path:
    """Convert a PDF, MOBI, or AZW3 file to EPUB using Calibre.

    Args:
        input_path: Source document path.
        output_epub_path: Optional explicit output path. If omitted, uses a temp file.
        calibre_path: Optional user-configured path to ebook-convert.

    Returns:
        Path to the converted EPUB file.

    Raises:
        AppError: If Calibre is missing ('ebook.calibre_missing') or conversion fails ('ebook.corrupt').
    """
    src = Path(input_path)
    if not src.is_file():
        raise AppError("internal.not_found", status_code=404, detail={"path": str(src)})

    binary = find_calibre_binary(calibre_path)

    if output_epub_path is not None:
        dst = Path(output_epub_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = tempfile.mkdtemp(prefix="praelector_calibre_")
        dst = Path(temp_dir) / f"{src.stem}.epub"

    try:
        proc = subprocess.run(
            [binary, str(src), str(dst), "--enable-heuristics"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            "ebook.corrupt",
            status_code=422,
            detail={"message": "Calibre conversion timed out after 180 seconds."},
        ) from exc
    except Exception as exc:
        raise AppError(
            "ebook.corrupt",
            status_code=422,
            detail={"message": f"Failed to execute Calibre conversion: {exc}"},
        ) from exc

    if proc.returncode != 0 or not dst.is_file():
        raise AppError(
            "ebook.corrupt",
            status_code=422,
            detail={
                "message": "Calibre ebook-convert failed to convert the file.",
                "stderr": proc.stderr[-2000:] if proc.stderr else "",
                "exit_code": proc.returncode,
            },
        )

    return dst
