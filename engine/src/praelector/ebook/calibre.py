# SPDX-License-Identifier: Apache-2.0
"""Calibre ``ebook-convert`` for PDF, MOBI and AZW3 (EB-03, EB-09, NF-04).

Discovery is :func:`praelector.config.probe_calibre` — settings, then ``PATH``,
then the Windows ``Calibre2`` directory. This module does not look anywhere
else. The binary is never bundled; a missing one is ``ebook.calibre_missing``
with the per-OS install key the UI localises (OPENAPI_SKETCH.md §4). Conversion
runs in a directory the caller owns, and stderr comes back on
``ebook.conversion_failed``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from praelector.config import Settings, probe_calibre
from praelector.errors import AppError, ErrorCode

CALIBRE_TIMEOUT_S: Final = 600
_STDERR_LIMIT: Final = 4000
_CREATE_NO_WINDOW: Final = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


@dataclass(frozen=True, slots=True)
class ConvertResult:
    """The outcome of one ``ebook-convert`` invocation."""

    returncode: int
    stderr: str
    stdout: str = ""


#: Tests pass a fake runner. Production uses :func:`_run_convert`, which is the
#: only place this process starts Calibre.
Converter = Callable[[Sequence[str]], ConvertResult]


def locate_ebook_convert(settings: Settings) -> str:
    """Absolute path to ``ebook-convert``, or ``ebook.calibre_missing``."""
    probe = probe_calibre(settings)
    if probe.present and probe.path and Path(probe.path).is_file():
        return probe.path
    raise _missing()


def convert_to_epub(
    source: Path,
    dest_dir: Path,
    *,
    binary: str,
    runner: Converter | None = None,
) -> Path:
    """Convert ``source`` to ``dest_dir/converted.epub``.

    ``binary`` is an explicit path. An empty string or a path that is not a
    file is absence — the same ``ebook.calibre_missing`` as a failed lookup —
    and does not fall through to ``PATH``. The runner is invoked with the
    argument vector; unit tests never take the default, which shells out.
    """
    if not binary or not Path(binary).is_file():
        raise _missing()
    dest_dir.mkdir(parents=True, exist_ok=True)
    output = dest_dir / "converted.epub"
    argv = [binary, _path(source), _path(output)]
    result = (runner or _run_convert)(argv)
    if result.returncode != 0 or not output.is_file():
        detail: dict[str, object] = {"returncode": result.returncode}
        stderr = _tail(result.stderr)
        if stderr:
            detail["stderr"] = stderr
        if result.returncode == 0:
            detail["reason"] = "no_output"
        raise AppError(
            ErrorCode.EBOOK_CONVERSION_FAILED,
            detail=detail,
            message="ebook-convert failed",
        )
    return output


def _run_convert(argv: Sequence[str]) -> ConvertResult:
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CALIBRE_TIMEOUT_S,
            check=False,
            creationflags=_CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr
        text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else (stderr or "")
        raise AppError(
            ErrorCode.EBOOK_CONVERSION_FAILED,
            detail={"reason": "timeout", "stderr": _tail(text)},
            message="ebook-convert timed out",
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise AppError(
            ErrorCode.EBOOK_CONVERSION_FAILED,
            detail={"reason": "spawn_failed"},
            message="ebook-convert could not be started",
        ) from exc
    return ConvertResult(
        returncode=completed.returncode,
        stderr=completed.stderr or "",
        stdout=completed.stdout or "",
    )


def _missing() -> AppError:
    return AppError(
        ErrorCode.EBOOK_CALIBRE_MISSING,
        detail=_install_detail(),
        message="ebook-convert is not available",
    )


def _host_platform() -> str:
    """``str``, not ``sys.platform``: mypy treats the latter as the host literal."""
    return sys.platform


def _install_detail() -> dict[str, str]:
    """Machine-readable per-OS instructions. The UI localises ``install_hint_key``."""
    platform = _host_platform()
    if platform == "win32":
        # dev-setup.md: ``winget install --id calibre.calibre``. PLAN.md §2: the
        # default install directory is searched by ``probe_calibre``, not here.
        return {
            "install_hint_key": "calibre_windows",
            "binary": "ebook-convert",
            "platform": "windows",
            "winget_id": "calibre.calibre",
            "default_dir": r"C:\Program Files\Calibre2",
        }
    if platform == "darwin":
        return {
            "install_hint_key": "calibre_macos",
            "binary": "ebook-convert",
            "platform": "macos",
        }
    # PLAN.md §2: ``pacman -S calibre``. The package name is the instruction.
    return {
        "install_hint_key": "calibre_linux",
        "binary": "ebook-convert",
        "platform": "linux",
        "package": "calibre",
        "package_manager": "pacman",
    }


def _tail(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _STDERR_LIMIT:
        return stripped
    return stripped[-_STDERR_LIMIT:]


def _path(path: Path) -> str:
    return os.fspath(path)
