# SPDX-License-Identifier: Apache-2.0
"""Application settings persistence and retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praelector.domain.models import (
    AppSettings,
    AudioSettings,
    GpuPolicy,
    LlmProfile,
    SecretField,
    SettingsUpdate,
    TaskRouting,
)
from praelector.store.atomic import atomic_write
from praelector.store.secrets import SecretStore


class SettingsStore:
    """Manages application-wide configuration in <config_dir>/config.json."""

    def __init__(self, config_dir: Path | str, data_dir: Path | str) -> None:
        self.config_dir = Path(config_dir).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.config_file = self.config_dir / "config.json"
        self.secrets = SecretStore(self.config_dir)

    def _default_settings(self) -> dict[str, Any]:
        projects_dir = self.data_dir / "projects"
        return {
            "projects_dir": str(projects_dir),
            "data_dir": str(self.data_dir),
            "config_dir": str(self.config_dir),
            "log_level": "INFO",
            "llm_profiles": [
                {
                    "id": "llm_local_ollama",
                    "kind": "openai_compatible",
                    "preset": "ollama",
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "qwen2.5:14b-instruct",
                    "is_cloud": False,
                    "supports_json_schema": True,
                    "timeout_s": 120,
                    "max_tokens": 1024,
                }
            ],
            "task_routing": {
                "classify_cheap": "llm_local_ollama",
                "dialogue_hard": "llm_local_ollama",
                "pronounce": "llm_local_ollama",
            },
            "gpu_policy": {
                "device_index": 0,
                "reserve_mib": None,
                "peak_worker_mib_overrides": {},
                "worker_cap": 4,
                "allow_cpu": False,
            },
            "audio": {
                "output_sample_rate": 44100,
                "output_bitrate_kbps": 64,
                "target_lufs": -23.0,
                "inter_sentence_silence_ms": 300,
                "crossfade_ms": 0,
            },
        }

    def read_raw(self) -> dict[str, Any]:
        """Read configuration JSON from disk, generating defaults if absent."""
        if not self.config_file.is_file():
            defaults = self._default_settings()
            self.write_raw(defaults)
            return defaults

        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            return dict(data) if isinstance(data, dict) else self._default_settings()
        except Exception:
            return self._default_settings()

    def write_raw(self, data: dict[str, Any]) -> None:
        """Write configuration JSON to disk atomically."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self.config_file, json.dumps(data, indent=2))

    def get_settings(self) -> AppSettings:
        """Get AppSettings with secrets appropriately masked (LM-03)."""
        raw = self.read_raw()

        # Populate profiles with secret status
        profiles: list[LlmProfile] = []
        for p in raw.get("llm_profiles", []):
            pid = p.get("id", "")
            has_secret = self.secrets.has_secret(f"llm_profile:{pid}")
            profile = LlmProfile(
                id=pid,
                kind=p.get("kind", "openai_compatible"),
                preset=p.get("preset", "ollama"),
                base_url=p.get("base_url", "http://127.0.0.1:11434/v1"),
                model=p.get("model", "qwen2.5:14b-instruct"),
                is_cloud=p.get("is_cloud", False),
                supports_json_schema=p.get("supports_json_schema", True),
                timeout_s=p.get("timeout_s", 120),
                max_tokens=p.get("max_tokens", 1024),
                api_key=SecretField(set=has_secret),
            )
            profiles.append(profile)

        tr_data = raw.get("task_routing", {})
        gpu_data = raw.get("gpu_policy", {})
        audio_data = raw.get("audio", {})

        return AppSettings(
            projects_dir=raw.get("projects_dir", str(self.data_dir / "projects")),
            data_dir=raw.get("data_dir", str(self.data_dir)),
            config_dir=raw.get("config_dir", str(self.config_dir)),
            log_level=raw.get("log_level", "INFO"),
            llm_profiles=profiles,
            task_routing=TaskRouting(**tr_data) if tr_data else TaskRouting(),
            gpu_policy=GpuPolicy(**gpu_data) if gpu_data else GpuPolicy(),
            audio=AudioSettings(**audio_data) if audio_data else AudioSettings(),
        )

    def update_settings(self, update: SettingsUpdate) -> AppSettings:
        """Apply partial updates to stored settings."""
        raw = self.read_raw()

        if update.projects_dir is not None:
            raw["projects_dir"] = update.projects_dir
        if update.log_level is not None:
            raw["log_level"] = update.log_level
        if update.task_routing is not None:
            raw["task_routing"] = update.task_routing.model_dump()
        if update.gpu_policy is not None:
            raw["gpu_policy"] = update.gpu_policy.model_dump()
        if update.audio is not None:
            raw["audio"] = update.audio.model_dump()

        self.write_raw(raw)
        return self.get_settings()
