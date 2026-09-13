# SPDX-License-Identifier: Apache-2.0
"""Secret credential storage via OS keyring with encrypted local fallback (LM-03)."""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import keyring
from cryptography.fernet import Fernet
from keyring.errors import KeyringError

SERVICE_NAME = "praelector"


class SecretStore:
    """Manages secret credentials using OS keyring with Fernet encrypted fallback."""

    def __init__(self, config_dir: Path | str) -> None:
        self.config_dir = Path(config_dir).resolve()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._key_file = self.config_dir / ".secret_key"
        self._enc_file = self.config_dir / "secrets.enc"
        self._fernet: Fernet | None = None

    def _get_fernet(self) -> Fernet:
        """Initialize or retrieve local Fernet cipher."""
        if self._fernet is not None:
            return self._fernet

        if not self._key_file.exists():
            key = Fernet.generate_key()
            self._key_file.write_bytes(key)
            if sys.platform != "win32":
                with contextlib.suppress(OSError):
                    self._key_file.chmod(0o600)
        else:
            key = self._key_file.read_bytes().strip()

        self._fernet = Fernet(key)
        return self._fernet

    def _read_fallback_secrets(self) -> dict[str, str]:
        """Read fallback secrets dictionary from encrypted file."""
        if not self._enc_file.exists():
            return {}
        try:
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(self._enc_file.read_bytes())
            result = json.loads(decrypted.decode("utf-8"))
            if isinstance(result, dict):
                return {str(k): str(v) for k, v in result.items()}
            return {}
        except Exception:
            return {}

    def _write_fallback_secrets(self, data: dict[str, str]) -> None:
        """Write secrets dictionary to encrypted fallback file."""
        fernet = self._get_fernet()
        payload = json.dumps(data).encode("utf-8")
        encrypted = fernet.encrypt(payload)
        self._enc_file.write_bytes(encrypted)
        if sys.platform != "win32":
            with contextlib.suppress(OSError):
                self._enc_file.chmod(0o600)

    def set_secret(self, key: str, value: str) -> None:
        """Save a secret credential, trying OS keyring first then encrypted fallback."""
        try:
            keyring.set_password(SERVICE_NAME, key, value)
            return
        except (KeyringError, Exception):
            pass

        # Fallback to encrypted file
        secrets = self._read_fallback_secrets()
        secrets[key] = value
        self._write_fallback_secrets(secrets)

    def get_secret(self, key: str) -> str | None:
        """Retrieve a secret credential."""
        try:
            val = keyring.get_password(SERVICE_NAME, key)
            if val is not None:
                return val
        except (KeyringError, Exception):
            pass

        secrets = self._read_fallback_secrets()
        return secrets.get(key)

    def delete_secret(self, key: str) -> None:
        """Delete a secret credential."""
        with contextlib.suppress(KeyringError, Exception):
            keyring.delete_password(SERVICE_NAME, key)

        secrets = self._read_fallback_secrets()
        if key in secrets:
            del secrets[key]
            self._write_fallback_secrets(secrets)

    def has_secret(self, key: str) -> bool:
        """Check whether a secret credential is set without exposing its value."""
        val = self.get_secret(key)
        return val is not None and len(val) > 0
