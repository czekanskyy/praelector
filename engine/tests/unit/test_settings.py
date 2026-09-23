# SPDX-License-Identifier: Apache-2.0
"""Tests for settings, secrets and the external-binary probes."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

import pytest

from praelector import config as config_mod
from praelector.config import (
    ENV_DATA_DIR,
    ENV_PROJECTS_DIR,
    AppPaths,
    AudioSettings,
    Settings,
    SettingsStore,
    merge_patch,
    probe_calibre,
    probe_ffmpeg,
    resolve_paths,
)
from praelector.errors import AppError, ErrorCode
from praelector.store.secrets import SecretBackend, SecretStore

FFMPEG_VERSION = "ffmpeg version 7.1 Copyright (c) 2000-2024 the FFmpeg developers"
FFMPEG_FILTERS = """
Filters:
  T.. = Timeline support
  A.. loudnorm           A->A       EBU R128 loudness normalization
  A.. silenceremove      A->A       Remove silence.
  A.. anull              A->A       Pass the source unchanged to the output.
"""
FFMPEG_ENCODERS = """
Encoders:
 V..... = Video
 A..... libmp3lame         MP3 (MPEG audio layer 3)
 A..... aac                AAC (Advanced Audio Coding)
"""


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    return resolve_paths(
        {
            ENV_DATA_DIR: os.fspath(tmp_path / "data"),
            "PRAELECTOR_CONFIG_DIR": os.fspath(tmp_path / "config"),
            ENV_PROJECTS_DIR: os.fspath(tmp_path / "projects"),
        }
    )


@pytest.fixture
def store(paths: AppPaths) -> SettingsStore:
    return SettingsStore(paths)


# -- merge patch --------------------------------------------------------------


def test_merge_patch_replaces_scalars() -> None:
    assert merge_patch({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}


def test_merge_patch_merges_nested_objects() -> None:
    base = {"gpu": {"worker_cap": 4, "allow_cpu": True}, "language": "en"}
    assert merge_patch(base, {"gpu": {"worker_cap": 2}}) == {
        "gpu": {"worker_cap": 2, "allow_cpu": True},
        "language": "en",
    }


def test_merge_patch_null_deletes() -> None:
    assert merge_patch({"a": 1, "b": {"c": 2}}, {"b": None}) == {"a": 1}


def test_merge_patch_does_not_mutate_the_base() -> None:
    base = {"gpu": {"worker_cap": 4}}
    merge_patch(base, {"gpu": {"worker_cap": 1}})
    assert base == {"gpu": {"worker_cap": 4}}


# -- settings store -----------------------------------------------------------


def test_defaults_when_no_file_exists(store: SettingsStore, paths: AppPaths) -> None:
    assert not store.file.exists()
    settings = store.load()
    assert settings.language == "en"
    assert settings.audio.target_lufs == -23.0
    assert settings.gpu.worker_cap == 4
    assert settings.paths.ffmpeg_path is None


def test_save_then_load_round_trips(store: SettingsStore) -> None:
    store.save(Settings(language="pl", audio=AudioSettings(target_lufs=-16.0)))
    loaded = store.load()
    assert loaded.language == "pl"
    assert loaded.audio.target_lufs == -16.0
    assert loaded.audio.output_sample_rate == 44100


def test_the_file_is_written_as_canonical_json(store: SettingsStore) -> None:
    store.save(Settings())
    first = store.file.read_bytes()
    store.save(Settings())
    assert store.file.read_bytes() == first


def test_patch_persists_only_what_changed(store: SettingsStore) -> None:
    result = store.patch({"gpu": {"worker_cap": 1}})
    assert result.gpu.worker_cap == 1
    assert result.gpu.allow_cpu is True
    assert store.load().gpu.worker_cap == 1


def test_patch_rejects_out_of_range_values(store: SettingsStore) -> None:
    with pytest.raises(AppError) as excinfo:
        store.patch({"gpu": {"worker_cap": 0}})
    assert excinfo.value.code is ErrorCode.INTERNAL_VALIDATION_FAILED
    assert ["gpu", "worker_cap"] in excinfo.value.detail["fields"]


def test_patch_rejects_an_unknown_type(store: SettingsStore) -> None:
    with pytest.raises(AppError):
        store.patch({"audio": {"target_lufs": "loud"}})


def test_a_corrupt_file_falls_back_to_defaults_with_a_reason(
    store: SettingsStore, paths: AppPaths
) -> None:
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    store.file.write_text("{broken", encoding="utf-8")

    with pytest.raises(AppError) as excinfo:
        store.load()
    assert excinfo.value.detail["reason"] == "not_json"

    # The engine must still start: the user needs a working app to fix the file.
    settings, error = store.load_or_defaults()
    assert settings.language == "en"
    assert error is not None
    assert error.code is ErrorCode.INTERNAL_VALIDATION_FAILED


def test_a_json_array_config_is_rejected(store: SettingsStore, paths: AppPaths) -> None:
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    store.file.write_text("[]", encoding="utf-8")
    settings, error = store.load_or_defaults()
    assert settings == Settings()
    assert error is not None


def test_load_or_defaults_has_no_error_for_a_clean_store(store: SettingsStore) -> None:
    settings, error = store.load_or_defaults()
    assert error is None
    assert settings.schema_version == 1


# -- path precedence ----------------------------------------------------------


def test_env_beats_settings_beats_default(tmp_path: Path) -> None:
    from_env = resolve_paths({ENV_PROJECTS_DIR: os.fspath(tmp_path / "from-env")})
    assert from_env.projects_dir == tmp_path / "from-env"

    settings = Settings(paths=config_mod.PathSettings(projects_dir=str(tmp_path / "from-settings")))
    from_settings = resolve_paths({}, settings)
    assert from_settings.projects_dir == tmp_path / "from-settings"

    default = resolve_paths({})
    assert default.projects_dir == Path.home() / "Praelector" / "projects"


def test_env_wins_even_when_settings_disagree(tmp_path: Path) -> None:
    settings = Settings(paths=config_mod.PathSettings(projects_dir=str(tmp_path / "settings")))
    paths = resolve_paths({ENV_PROJECTS_DIR: os.fspath(tmp_path / "env")}, settings)
    assert paths.projects_dir == tmp_path / "env"


def test_models_dir_follows_the_data_dir(tmp_path: Path) -> None:
    paths = resolve_paths({ENV_DATA_DIR: os.fspath(tmp_path / "data")})
    assert paths.models_dir == tmp_path / "data" / "models"


# -- secrets ------------------------------------------------------------------


def test_the_file_backend_round_trips(tmp_path: Path) -> None:
    store = SecretStore(tmp_path, backend=SecretBackend.FILE)
    assert store.get("llm.openai") is None

    assert store.set("llm.openai", "sk-secret-value") is True
    assert store.get("llm.openai") == "sk-secret-value"
    assert store.is_set("llm.openai")
    assert (tmp_path / "secrets.json").exists()

    store.delete("llm.openai")
    assert store.get("llm.openai") is None


def test_the_secrets_file_keeps_several_keys(tmp_path: Path) -> None:
    store = SecretStore(tmp_path, backend=SecretBackend.FILE)
    store.set("a", "one")
    store.set("b", "two")
    assert json.loads((tmp_path / "secrets.json").read_text(encoding="utf-8")) == {
        "a": "one",
        "b": "two",
    }


def test_a_corrupt_secrets_file_is_ignored_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "secrets.json").write_text("{broken", encoding="utf-8")
    store = SecretStore(tmp_path, backend=SecretBackend.FILE)
    assert store.get("a") is None
    store.set("a", "one")
    assert store.get("a") == "one"


def test_the_unavailable_backend_refuses_to_store(tmp_path: Path) -> None:
    store = SecretStore(tmp_path, backend=SecretBackend.UNAVAILABLE)
    assert store.set("a", "one") is False
    assert store.get("a") is None


def test_backend_detection_returns_a_known_value(tmp_path: Path) -> None:
    assert SecretStore(tmp_path).backend in set(SecretBackend)


# -- probes -------------------------------------------------------------------


def _fake_probe(responses: dict[str, str | None]) -> object:
    def run(argv: Sequence[str], timeout: float = 15.0) -> str | None:
        for needle, value in responses.items():
            if needle in argv:
                return value
        return None

    return run


def test_ffmpeg_probe_accepts_a_complete_build(
    monkeypatch: pytest.MonkeyPatch, paths: AppPaths
) -> None:
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        config_mod,
        "_run_probe",
        _fake_probe(
            {
                "-version": FFMPEG_VERSION,
                "-filters": FFMPEG_FILTERS,
                "-encoders": FFMPEG_ENCODERS,
            }
        ),
    )
    probe = probe_ffmpeg(Settings(), paths)
    assert probe.present is True
    assert probe.version == "7.1"
    assert probe.reason is None
    assert probe.path == "/usr/bin/ffmpeg"


def test_ffmpeg_probe_rejects_an_old_version(
    monkeypatch: pytest.MonkeyPatch, paths: AppPaths
) -> None:
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        config_mod, "_run_probe", _fake_probe({"-version": "ffmpeg version 4.4.4 Copyright"})
    )
    probe = probe_ffmpeg(Settings(), paths)
    assert probe.present is False
    assert probe.reason == "too_old"
    assert probe.version == "4.4.4"


def test_ffmpeg_probe_reports_a_missing_encoder(
    monkeypatch: pytest.MonkeyPatch, paths: AppPaths
) -> None:
    """An LGPL build without the native aac encoder cannot mux an M4B (D-06)."""
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        config_mod,
        "_run_probe",
        _fake_probe(
            {"-version": FFMPEG_VERSION, "-filters": FFMPEG_FILTERS, "-encoders": "Encoders:\n"}
        ),
    )
    probe = probe_ffmpeg(Settings(), paths)
    assert probe.present is False
    assert probe.reason == "encoder_missing:aac"


def test_ffmpeg_probe_reports_a_missing_filter(
    monkeypatch: pytest.MonkeyPatch, paths: AppPaths
) -> None:
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(
        config_mod,
        "_run_probe",
        _fake_probe(
            {
                "-version": FFMPEG_VERSION,
                "-filters": "Filters:\n  A.. anull   A->A  Pass through.\n",
                "-encoders": FFMPEG_ENCODERS,
            }
        ),
    )
    assert probe_ffmpeg(Settings(), paths).reason == "filter_missing:loudnorm"


def test_ffmpeg_probe_reports_absence(monkeypatch: pytest.MonkeyPatch, paths: AppPaths) -> None:
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: None)
    probe = probe_ffmpeg(Settings(), paths)
    assert probe.present is False
    assert probe.reason == "not_found"


def test_ffmpeg_probe_reports_a_binary_that_will_not_run(
    monkeypatch: pytest.MonkeyPatch, paths: AppPaths
) -> None:
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(config_mod, "_run_probe", _fake_probe({}))
    assert probe_ffmpeg(Settings(), paths).reason == "probe_failed"


def test_an_explicit_ffmpeg_path_wins_over_path_lookup(
    monkeypatch: pytest.MonkeyPatch, paths: AppPaths, tmp_path: Path
) -> None:
    binary = tmp_path / "my-ffmpeg"
    binary.write_bytes(b"#!/bin/sh\n")
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: pytest.fail("PATH was consulted"))
    monkeypatch.setattr(
        config_mod,
        "_run_probe",
        _fake_probe(
            {"-version": FFMPEG_VERSION, "-filters": FFMPEG_FILTERS, "-encoders": FFMPEG_ENCODERS}
        ),
    )
    settings = Settings(paths=config_mod.PathSettings(ffmpeg_path=str(binary)))
    probe = probe_ffmpeg(settings, paths)
    assert probe.present is True
    assert probe.path == os.fspath(binary)


def test_the_app_bin_dir_is_the_last_place_looked_in(
    monkeypatch: pytest.MonkeyPatch, paths: AppPaths
) -> None:
    paths.bin_dir.mkdir(parents=True, exist_ok=True)
    bundled = paths.bin_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    bundled.write_bytes(b"stub")
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        config_mod,
        "_run_probe",
        _fake_probe(
            {"-version": FFMPEG_VERSION, "-filters": FFMPEG_FILTERS, "-encoders": FFMPEG_ENCODERS}
        ),
    )
    probe = probe_ffmpeg(Settings(), paths)
    assert probe.present is True
    assert Path(str(probe.path)) == bundled


def test_calibre_probe_reports_absence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: None)
    # This machine really does have Calibre in the default install location, and
    # the probe is supposed to find it there — so point the hint somewhere empty.
    monkeypatch.setenv("PROGRAMFILES", os.fspath(tmp_path / "no-calibre-here"))
    probe = probe_calibre(Settings())
    assert probe.present is False
    assert probe.reason == "not_found"


def test_calibre_probe_reads_the_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_mod.shutil, "which", lambda name: "/usr/bin/ebook-convert")
    monkeypatch.setattr(
        config_mod, "_run_probe", _fake_probe({"--version": "ebook-convert (calibre 7.16.0)\n"})
    )
    probe = probe_calibre(Settings())
    assert probe.present is True
    assert probe.version == "7.16.0"
