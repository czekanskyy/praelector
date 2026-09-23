# SPDX-License-Identifier: Apache-2.0
"""Path resolution, the launch environment, user settings and feature probes.

Every path in the engine is a :class:`pathlib.Path`. Only the serialised form is
a string, and it is always POSIX-style with a drive prefix
(``C:/Users/...``), so a project directory copied between Windows and Linux
keeps its relative references and the UI never has to know the platform.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import platformdirs
from pydantic import BaseModel, Field, ValidationError

from praelector.errors import AppError, ErrorCode
from praelector.store.atomic import write_json_atomic

APP_NAME = "Praelector"

#: Linux directories are lowercase in PLAN.md §1.7; Windows is case-insensitive,
#: so the same constant renders as ``%LOCALAPPDATA%\Praelector``.
_APP_DIR_NAME = APP_NAME if os.name == "nt" else APP_NAME.lower()

#: ``~/Praelector/projects`` on every platform (PRD §5.2) — deliberately outside
#: the app data dir, because it holds the user's books and audiobooks.
PROJECTS_ROOT_NAME = "Praelector"

ENV_TOKEN = "PRAELECTOR_TOKEN"
ENV_DATA_DIR = "PRAELECTOR_DATA_DIR"
ENV_CONFIG_DIR = "PRAELECTOR_CONFIG_DIR"
ENV_LOG_DIR = "PRAELECTOR_LOG_DIR"
ENV_PROJECTS_DIR = "PRAELECTOR_PROJECTS_DIR"
ENV_MODELS_DIR = "PRAELECTOR_MODELS_DIR"
ENV_RUNTIMES_DIR = "PRAELECTOR_RUNTIMES_DIR"
ENV_BIN_DIR = "PRAELECTOR_BIN_DIR"
ENV_HOST = "PRAELECTOR_HOST"
ENV_PORT = "PRAELECTOR_PORT"
ENV_LOG_LEVEL = "PRAELECTOR_LOG_LEVEL"
ENV_PARENT_PID = "PRAELECTOR_PARENT_PID"
ENV_ENGINE_CMD = "PRAELECTOR_ENGINE_CMD"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0
DEFAULT_LOG_LEVEL = "INFO"


class ConfigError(Exception):
    """The environment is not usable; ``__main__`` turns this into exit code 2."""


def to_posix(path: Path) -> str:
    """Serialise a path for JSON: POSIX-style, drive prefix preserved."""
    return path.as_posix()


def from_posix(value: str) -> Path:
    """Parse a serialised path. Accepts both separators for tolerance."""
    return Path(value.replace("/", os.sep) if os.sep != "/" else value)


def default_log_dir(data_dir: Path) -> Path:
    """Windows keeps logs next to the data dir; Linux uses ``XDG_STATE_HOME``."""
    if os.name == "nt":
        return data_dir / "logs"
    return Path(platformdirs.user_state_dir(_APP_DIR_NAME, appauthor=False)) / "logs"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Where this installation keeps things. Immutable once resolved."""

    data_dir: Path
    config_dir: Path
    log_dir: Path
    projects_dir: Path
    models_dir: Path
    runtimes_dir: Path
    bin_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def global_lexicon_db(self) -> Path:
        """The global pronunciation lexicon (AI-09, DATA_MODEL.md §12)."""
        return self.config_dir / "lexicon.db"

    @property
    def engine_log_file(self) -> Path:
        return self.log_dir / "engine.log"

    def project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def runtime_dir(self, flavour: str, lock_hash: str) -> Path:
        """``<dataDir>/runtimes/<flavour>-<lockhash>`` (PLAN.md D-04)."""
        return self.runtimes_dir / f"{flavour}-{lock_hash}"

    def model_dir(self, backend_id: str, repo: str, revision: str) -> Path:
        return self.models_dir / backend_id / repo.replace("/", "--") / revision

    def ensure(self) -> None:
        """Create the directories the engine owns. Never touches projects_dir."""
        for path in (
            self.data_dir,
            self.config_dir,
            self.log_dir,
            self.models_dir,
            self.runtimes_dir,
            self.bin_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def resolve_paths(
    environ: Mapping[str, str] | None = None,
    settings: Settings | None = None,
) -> AppPaths:
    """Resolve every directory.

    Precedence is ``PRAELECTOR_*`` environment variable → ``config.json`` →
    default. The env var wins because it is how the shell and the tests pin the
    engine to a specific directory; settings are what the user chose in the UI.
    """
    env = os.environ if environ is None else environ

    data_dir = _path_or(env, ENV_DATA_DIR) or Path(
        platformdirs.user_data_dir(_APP_DIR_NAME, appauthor=False)
    )
    config_dir = _path_or(env, ENV_CONFIG_DIR) or Path(
        platformdirs.user_config_dir(_APP_DIR_NAME, appauthor=False)
    )
    return AppPaths(
        data_dir=data_dir,
        config_dir=config_dir,
        log_dir=_path_or(env, ENV_LOG_DIR) or default_log_dir(data_dir),
        projects_dir=_path_or(env, ENV_PROJECTS_DIR)
        or _setting_or(settings.paths.projects_dir if settings else None)
        or Path.home() / PROJECTS_ROOT_NAME / "projects",
        models_dir=_path_or(env, ENV_MODELS_DIR)
        or _setting_or(settings.paths.models_dir if settings else None)
        or data_dir / "models",
        runtimes_dir=_path_or(env, ENV_RUNTIMES_DIR) or data_dir / "runtimes",
        bin_dir=_path_or(env, ENV_BIN_DIR) or data_dir / "bin",
    )


def _path_or(env: Mapping[str, str], key: str) -> Path | None:
    raw = env.get(key)
    return Path(raw).expanduser() if raw else None


def _setting_or(raw: str | None) -> Path | None:
    return Path(raw).expanduser() if raw else None


@dataclass(slots=True)
class RuntimeEnv:
    """What the shell told us at launch, plus the resolved paths and settings.

    Mutable because ``PUT /v1/settings`` can move ``projects_dir`` or
    ``models_dir``, and every path is derived from them. ``token`` and ``environ``
    are excluded from the repr so a stray ``logger.debug("%s", env)`` cannot leak
    the bearer token (LM-03).
    """

    token: str = field(repr=False)
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    log_level: str = DEFAULT_LOG_LEVEL
    parent_pid: int | None = None
    paths: AppPaths = field(default_factory=lambda: resolve_paths())
    #: Snapshot of the launch environment, kept so paths can be re-resolved
    #: against the same overrides after a settings change.
    environ: Mapping[str, str] = field(default_factory=dict, repr=False)
    # The lambda defers the name lookup: `Settings` is declared further down.
    settings: Settings = field(default_factory=lambda: Settings())
    settings_error: str | None = None

    def apply_settings(self, settings: Settings) -> None:
        """Recompute derived paths after the user changes settings."""
        self.settings = settings
        self.paths = resolve_paths(self.environ, settings)


def load_runtime_env(environ: Mapping[str, str] | None = None) -> RuntimeEnv:
    """Read the launch environment.

    The token is mandatory: an engine without one would be drivable by any local
    process or web page, which is exactly what D-10 exists to prevent.
    """
    env = os.environ if environ is None else environ
    token = env.get(ENV_TOKEN, "").strip()
    if not token:
        raise ConfigError(
            f"{ENV_TOKEN} is required. The desktop shell sets it; for manual runs "
            f"use `just dev-engine` or set {ENV_TOKEN} yourself."
        )

    raw_port = env.get(ENV_PORT, "").strip() or str(DEFAULT_PORT)
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ConfigError(f"{ENV_PORT} must be an integer, got {raw_port!r}") from exc
    if not 0 <= port <= 65535:
        raise ConfigError(f"{ENV_PORT} out of range: {port}")

    raw_pid = env.get(ENV_PARENT_PID, "").strip()
    parent_pid: int | None
    if not raw_pid:
        parent_pid = None
    else:
        try:
            parent_pid = int(raw_pid)
        except ValueError as exc:
            raise ConfigError(f"{ENV_PARENT_PID} must be an integer, got {raw_pid!r}") from exc

    # Two-phase: `config.json` lives in `config_dir`, which only the environment
    # can move, so reading settings after the first resolution cannot be circular.
    bootstrap = resolve_paths(env)
    settings, settings_error = SettingsStore(bootstrap).load_or_defaults()

    return RuntimeEnv(
        token=token,
        host=(env.get(ENV_HOST, "").strip() or DEFAULT_HOST),
        port=port,
        log_level=(env.get(ENV_LOG_LEVEL, "").strip() or DEFAULT_LOG_LEVEL),
        parent_pid=parent_pid,
        paths=resolve_paths(env, settings),
        environ=dict(env),
        settings=settings,
        settings_error=settings_error.message if settings_error else None,
    )


# -- Settings -----------------------------------------------------------------
#
# `config.json` is the user's machine-level configuration, not project state:
# where ffmpeg lives, how much VRAM to reserve, which language the UI speaks.
# Project-scoped choices live in the project database. Secrets never live here
# (LM-03) — they go to the OS keyring through `store/secrets.py`.
#
# LLM profiles and task routing join this tree in M2, when the provider clients
# land; adding them now would be schema with nothing to read it.

SETTINGS_SCHEMA_VERSION = 1
MIN_FFMPEG_MAJOR = 6
#: What the ingest and mux paths depend on (D-06). `aac` is the native encoder
#: used for the M4B; the other two are filters used by the voice-sample chain.
REQUIRED_FFMPEG_ENCODERS = ("aac",)
REQUIRED_FFMPEG_FILTERS = ("loudnorm", "silenceremove")


class AudioSettings(BaseModel):
    """Global audio output (TTS-05, TTS-08).

    Applied at concat time, so changing these never invalidates rendered chunks
    (DATA_MODEL.md §9.2).
    """

    output_sample_rate: int = Field(default=44100, ge=8000, le=192000)
    output_bitrate_kbps: int = Field(default=64, ge=16, le=320)
    target_lufs: float = Field(default=-23.0, ge=-70.0, le=-5.0)
    inter_sentence_silence_ms: int = Field(default=300, ge=0, le=5000)
    crossfade_ms: int = Field(default=0, ge=0, le=2000)


class GpuPolicy(BaseModel):
    """User overrides for the GPU-04 budget math; the formula supplies defaults."""

    device_index: int = Field(default=0, ge=-1)
    reserve_mib: int | None = Field(default=None, ge=0)
    peak_worker_mib_overrides: dict[str, int] = Field(default_factory=dict)
    worker_cap: int = Field(default=4, ge=1, le=16)
    allow_cpu: bool = True


class PathSettings(BaseModel):
    """Explicit binary and directory overrides. ``None`` means "resolve it"."""

    ffmpeg_path: str | None = None
    calibre_path: str | None = None
    models_dir: str | None = None
    projects_dir: str | None = None


class Settings(BaseModel):
    """The whole settings tree, as served by ``GET /v1/settings``."""

    schema_version: int = SETTINGS_SCHEMA_VERSION
    #: UI language (IX-01). The engine has no user-facing strings; this is stored
    #: here so the choice survives before any project exists.
    language: str = "en"
    log_level: str = "INFO"
    paths: PathSettings = Field(default_factory=PathSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    gpu: GpuPolicy = Field(default_factory=GpuPolicy)


def merge_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """RFC 7386 JSON Merge Patch: nested objects merge, ``null`` deletes."""
    result = dict(base)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_patch(result[key], value)
        else:
            result[key] = value
    return result


class SettingsStore:
    """Reads and writes ``<configDir>/config.json`` atomically."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths

    @property
    def file(self) -> Path:
        return self._paths.config_file

    def load(self) -> Settings:
        """Current settings, or defaults when the file does not exist yet."""
        try:
            raw = self.file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Settings()
        except OSError as exc:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                detail={"path": self.file.as_posix(), "reason": "unreadable"},
                message=str(exc),
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError(
                ErrorCode.INTERNAL_VALIDATION_FAILED,
                detail={"path": self.file.as_posix(), "reason": "not_json"},
                message="config.json is not valid JSON",
            ) from exc
        if not isinstance(data, dict):
            raise AppError(
                ErrorCode.INTERNAL_VALIDATION_FAILED,
                detail={"path": self.file.as_posix(), "reason": "not_an_object"},
            )
        return _validate_settings(data, self.file)

    def load_or_defaults(self) -> tuple[Settings, AppError | None]:
        """Settings plus the reason they had to fall back.

        A corrupt ``config.json`` must not stop the engine from starting: the user
        needs a working app in order to fix it. The error is surfaced through
        ``GET /v1/capabilities`` instead of being swallowed.
        """
        try:
            return self.load(), None
        except AppError as exc:
            return Settings(), exc

    def save(self, settings: Settings) -> Settings:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.file, settings.model_dump(mode="json"))
        return settings

    def patch(self, changes: dict[str, Any]) -> Settings:
        """Merge-patch the stored settings and persist the result."""
        merged = merge_patch(self.load().model_dump(mode="json"), changes)
        return self.save(_validate_settings(merged, self.file))


def _validate_settings(data: dict[str, Any], source: Path) -> Settings:
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise AppError(
            ErrorCode.INTERNAL_VALIDATION_FAILED,
            detail={
                "path": source.as_posix(),
                "reason": "schema",
                "fields": [list(err["loc"]) for err in exc.errors()],
            },
            message=f"settings failed validation: {exc.error_count()} fields",
        ) from exc


# -- Feature probes -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BinaryProbe:
    """The result of looking for one external binary (MX-04, EB-03)."""

    present: bool
    path: str | None = None
    version: str | None = None
    #: Stable snake_case reason, never prose — the UI localises it (D-16):
    #: ``not_found``, ``too_old``, ``probe_failed``, ``encoder_missing:<name>``,
    #: ``filter_missing:<name>``.
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Capabilities:
    """What this machine can actually do, probed once and cached."""

    ffmpeg: BinaryProbe
    calibre: BinaryProbe
    keyring_backend: str
    settings_error: str | None = None


def _run_probe(argv: Sequence[str], timeout: float = 15.0) -> str | None:
    """Run a probe command, returning stdout or None if it cannot be run."""
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _resolve_binary(name: str, explicit: str | None, extra_dirs: Sequence[Path]) -> str | None:
    """settings → PATH → the app's own bin dir (PLAN.md §1.7)."""
    if explicit:
        candidate = Path(explicit).expanduser()
        return os.fspath(candidate) if candidate.is_file() else None
    found = shutil.which(name)
    if found:
        return found
    exe = f"{name}.exe" if os.name == "nt" else name
    for directory in extra_dirs:
        candidate = directory / exe
        if candidate.is_file():
            return os.fspath(candidate)
    return None


def probe_ffmpeg(settings: Settings, paths: AppPaths) -> BinaryProbe:
    """ffmpeg ≥ 6.0 with the three filters we depend on (D-06).

    Never bundled and never assumed: the probe result is what turns into
    ``audio.ffmpeg_missing`` with per-OS instructions when a job needs it.
    """
    resolved = _resolve_binary("ffmpeg", settings.paths.ffmpeg_path, [paths.bin_dir])
    if resolved is None:
        return BinaryProbe(present=False, reason="not_found")

    banner = _run_probe([resolved, "-hide_banner", "-version"])
    if banner is None:
        return BinaryProbe(present=False, path=resolved, reason="probe_failed")
    parts = _parse_ffmpeg_version(banner)
    if parts is None:
        return BinaryProbe(present=False, path=resolved, reason="probe_failed")

    version = ".".join(str(part) for part in parts)
    if parts[0] < MIN_FFMPEG_MAJOR:
        return BinaryProbe(present=False, path=resolved, version=version, reason="too_old")

    listing = _run_probe([resolved, "-hide_banner", "-filters"])
    if listing is None:
        return BinaryProbe(present=True, path=resolved, version=version, reason="probe_failed")
    encoders = _run_probe([resolved, "-hide_banner", "-encoders"])
    if encoders is None:
        return BinaryProbe(present=True, path=resolved, version=version, reason="probe_failed")

    for name in REQUIRED_FFMPEG_ENCODERS:
        if name not in _tool_names(encoders):
            return _ffmpeg_incomplete(resolved, version, "encoder", name)
    for name in REQUIRED_FFMPEG_FILTERS:
        if name not in _tool_names(listing):
            return _ffmpeg_incomplete(resolved, version, "filter", name)
    return BinaryProbe(present=True, path=resolved, version=version)


def _ffmpeg_incomplete(path: str, version: str, kind: str, name: str) -> BinaryProbe:
    return BinaryProbe(
        present=False,
        path=path,
        version=version,
        reason=f"{kind}_missing:{name}",
    )


def _tool_names(listing: str) -> set[str]:
    """The second column of an ffmpeg ``-filters``/``-encoders`` listing."""
    return {fields[1] for line in listing.splitlines() if len(fields := line.split()) > 2}


def probe_calibre(settings: Settings) -> BinaryProbe:
    """``ebook-convert`` is optional; PDF/MOBI ingest needs it (EB-03)."""
    hints: list[Path] = []
    if os.name == "nt":
        # The default installer location is not on PATH for every user.
        hints.append(Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Calibre2")
    resolved = _resolve_binary("ebook-convert", settings.paths.calibre_path, hints)
    if resolved is None:
        return BinaryProbe(present=False, reason="not_found")
    banner = _run_probe([resolved, "--version"])
    if banner is None:
        return BinaryProbe(present=True, path=resolved, reason="probe_failed")
    match = re.search(r"\d+\.\d+(?:\.\d+)?", banner)
    return BinaryProbe(present=True, path=resolved, version=match.group(0) if match else None)


def probe_keyring() -> str:
    """The active keyring backend, so the UI can warn when secrets will not land
    in the OS credential store (LM-03)."""
    try:
        import keyring

        return type(keyring.get_keyring()).__name__
    except Exception:  # a broken keyring backend must not stop the app
        return "unavailable"


def _parse_ffmpeg_version(banner: str) -> tuple[int, ...] | None:
    match = re.search(r"ffmpeg version (\d+)(?:\.(\d+))?(?:\.(\d+))?", banner)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups() if part is not None)
