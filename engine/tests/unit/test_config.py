# SPDX-License-Identifier: Apache-2.0
"""Tests for path resolution and the launch environment (PLAN.md §1.7)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from praelector.config import (
    ENV_DATA_DIR,
    ENV_PARENT_PID,
    ENV_PORT,
    ENV_TOKEN,
    ConfigError,
    from_posix,
    load_runtime_env,
    resolve_paths,
    to_posix,
)


def test_env_overrides_win(tmp_path: Path) -> None:
    paths = resolve_paths(
        {
            ENV_DATA_DIR: os.fspath(tmp_path / "data"),
            "PRAELECTOR_PROJECTS_DIR": os.fspath(tmp_path / "books"),
            "PRAELECTOR_MODELS_DIR": os.fspath(tmp_path / "weights"),
        }
    )
    assert paths.data_dir == tmp_path / "data"
    assert paths.projects_dir == tmp_path / "books"
    assert paths.models_dir == tmp_path / "weights"


def test_derived_dirs_default_under_the_data_dir(tmp_path: Path) -> None:
    paths = resolve_paths({ENV_DATA_DIR: os.fspath(tmp_path / "data")})
    assert paths.models_dir == tmp_path / "data" / "models"
    assert paths.runtimes_dir == tmp_path / "data" / "runtimes"
    assert paths.bin_dir == tmp_path / "data" / "bin"
    assert paths.config_file.name == "config.json"
    assert paths.global_lexicon_db.name == "lexicon.db"


def test_log_dir_follows_the_platform_convention(tmp_path: Path) -> None:
    paths = resolve_paths({ENV_DATA_DIR: os.fspath(tmp_path / "data")})
    if os.name == "nt":
        assert paths.log_dir == tmp_path / "data" / "logs"
    else:
        # XDG_STATE_HOME, not the data dir (PLAN.md §1.7).
        assert paths.log_dir != tmp_path / "data" / "logs"
        assert paths.log_dir.name == "logs"


def test_projects_default_to_the_home_directory() -> None:
    assert resolve_paths({}).projects_dir == Path.home() / "Praelector" / "projects"


def test_the_platform_path_table_matches_the_plan() -> None:
    """PLAN.md §1.7: on Windows config roams, data and logs are local."""
    paths = resolve_paths({})
    if os.name == "nt":
        local = Path(os.environ["LOCALAPPDATA"])
        roaming = Path(os.environ["APPDATA"])
        assert paths.data_dir == local / "Praelector"
        assert paths.config_dir == roaming / "Praelector"
        assert paths.log_dir == paths.data_dir / "logs"
    else:
        assert paths.data_dir.name == "praelector"
        assert paths.config_dir.name == "praelector"
        assert paths.log_dir.name == "logs"
    # platformdirs returns the data dir for user_config_dir unless roaming=True,
    # which would collapse the two and put a machine-local cache beside a roaming
    # config. That regression is what this asserts against.
    assert paths.config_dir != paths.data_dir


def test_runtime_and_model_dirs_are_content_addressed(tmp_path: Path) -> None:
    paths = resolve_paths({ENV_DATA_DIR: os.fspath(tmp_path / "data")})
    assert paths.runtime_dir("cuda", "abc123").name == "cuda-abc123"
    assert paths.model_dir("omnivoice", "k2-fsa/OmniVoice", "deadbeef") == (
        tmp_path / "data" / "models" / "omnivoice" / "k2-fsa--OmniVoice" / "deadbeef"
    )


def test_posix_serialisation_round_trips(tmp_path: Path) -> None:
    original = tmp_path / "audio" / "chunks" / "ab" / "abc.wav"
    serialised = to_posix(original)
    assert "\\" not in serialised
    assert from_posix(serialised) == original


def test_token_is_mandatory(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=ENV_TOKEN):
        load_runtime_env({ENV_DATA_DIR: os.fspath(tmp_path)})


def test_port_must_be_an_integer(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="integer"):
        load_runtime_env({ENV_TOKEN: "t" * 32, ENV_PORT: "http", ENV_DATA_DIR: os.fspath(tmp_path)})


def test_port_must_be_in_range(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="out of range"):
        load_runtime_env(
            {ENV_TOKEN: "t" * 32, ENV_PORT: "70000", ENV_DATA_DIR: os.fspath(tmp_path)}
        )


def test_port_defaults_to_os_assigned(tmp_path: Path) -> None:
    env = load_runtime_env({ENV_TOKEN: "t" * 32, ENV_DATA_DIR: os.fspath(tmp_path)})
    assert env.port == 0
    assert env.host == "127.0.0.1"
    assert env.parent_pid is None


def test_parent_pid_is_parsed_when_present(tmp_path: Path) -> None:
    env = load_runtime_env(
        {ENV_TOKEN: "t" * 32, ENV_PARENT_PID: "4242", ENV_DATA_DIR: os.fspath(tmp_path)}
    )
    assert env.parent_pid == 4242


def test_a_bad_parent_pid_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=ENV_PARENT_PID):
        load_runtime_env(
            {ENV_TOKEN: "t" * 32, ENV_PARENT_PID: "not-a-pid", ENV_DATA_DIR: os.fspath(tmp_path)}
        )
