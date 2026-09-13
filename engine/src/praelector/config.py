# SPDX-License-Identifier: Apache-2.0
"""Configuration management and settings resolution."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_log_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Engine runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PRAELECTOR_",
        case_sensitive=False,
        extra="ignore",
    )

    token: str | None = Field(default=None, description="Shared bearer authentication token")
    data_dir: Path = Field(
        default_factory=lambda: Path(user_data_dir("Praelector", appauthor=False)),
        description="Application data directory",
    )
    config_dir: Path = Field(
        default_factory=lambda: Path(user_config_dir("Praelector", appauthor=False)),
        description="Configuration directory",
    )
    log_dir: Path = Field(
        default_factory=lambda: Path(user_log_dir("Praelector", appauthor=False)),
        description="Logs directory",
    )
    log_level: str = Field(default="INFO", description="Logging level")
    parent_pid: int | None = Field(default=None, description="Parent process PID for supervision")
    host: str = Field(default="127.0.0.1", description="Bind host (loopback only)")
    port: int = Field(default=0, description="Bind port (0 for ephemeral OS assignment)")

    # Allowed Origins for webview/browser safety
    allowed_origins: list[str] = Field(
        default=["tauri://localhost", "http://localhost:1420", "http://127.0.0.1:1420"],
        description="Allowed Origin headers",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create singleton engine settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings: Settings) -> None:
    """Override singleton engine settings (useful for tests)."""
    global _settings
    _settings = settings
