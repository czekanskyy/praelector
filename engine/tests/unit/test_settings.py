# SPDX-License-Identifier: Apache-2.0
"""Unit tests for settings store and secret management."""

from __future__ import annotations

from pathlib import Path

from praelector.domain.models import SettingsUpdate
from praelector.store.settings import SettingsStore


def test_settings_store_defaults_and_updates(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"

    store = SettingsStore(config_dir=config_dir, data_dir=data_dir)

    settings = store.get_settings()
    assert settings.log_level == "INFO"
    assert len(settings.llm_profiles) >= 1
    assert settings.llm_profiles[0].api_key.set is False

    # Store a secret key
    profile_id = settings.llm_profiles[0].id
    store.secrets.set_secret(f"llm_profile:{profile_id}", "sk-secret-123")

    # Re-fetch settings, api_key should be set: True, without exposing raw string
    updated_settings = store.get_settings()
    assert updated_settings.llm_profiles[0].api_key.set is True

    # Update settings
    custom_projects_dir = str(tmp_path / "my_projects")
    store.update_settings(SettingsUpdate(projects_dir=custom_projects_dir, log_level="DEBUG"))

    reloaded = store.get_settings()
    assert reloaded.projects_dir == custom_projects_dir
    assert reloaded.log_level == "DEBUG"
