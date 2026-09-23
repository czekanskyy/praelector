# SPDX-License-Identifier: Apache-2.0
"""Secret storage: OS keyring first, an explicit local file second (LM-03).

The fallback is **obfuscation, not encryption**. There is no key that an attacker
with read access to the config directory would not also have, so pretending
otherwise would be worse than saying so: the active backend is reported by
``GET /v1/capabilities`` and the UI warns when it is ``file``.

Rules that hold either way: secrets are never written to ``config.json``, never
logged (they are registered with the redaction filter before first use), and
never returned by the API — callers get ``{"set": true}``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import stat
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

logger = logging.getLogger(__name__)

SERVICE = "praelector"
SECRETS_FILE_NAME = "secrets.json"


class _Keyring(Protocol):
    """The three calls we make. Typed locally so the lazy import stays honest."""

    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class SecretBackend(StrEnum):
    KEYRING = "keyring"
    FILE = "file"
    UNAVAILABLE = "unavailable"


class SecretStore:
    """Key/value secrets namespaced by ``SERVICE``.

    ``backend`` can be forced, which is how the tests pin the file backend and how
    a user on a machine with no credential store can opt in explicitly.
    """

    def __init__(self, config_dir: Path, *, backend: SecretBackend | None = None) -> None:
        self._config_dir = config_dir
        self._backend = backend

    @property
    def file(self) -> Path:
        return self._config_dir / SECRETS_FILE_NAME

    @property
    def backend(self) -> SecretBackend:
        """Resolved once: probing the keyring is not free."""
        if self._backend is None:
            self._backend = _detect_backend()
        return self._backend

    def get(self, key: str) -> str | None:
        if self.backend is SecretBackend.KEYRING:
            try:
                return _keyring().get_password(SERVICE, key)
            except Exception:
                logger.warning("keyring read failed", extra={"secret_key": key})
                return None
        if self.backend is SecretBackend.FILE:
            return self._read_file().get(key)
        return None

    def set(self, key: str, value: str) -> bool:
        """Store a secret. False when there is nowhere safe to put it."""
        if self.backend is SecretBackend.KEYRING:
            try:
                _keyring().set_password(SERVICE, key, value)
            except Exception:
                logger.warning("keyring write failed", extra={"secret_key": key})
                return False
            return True
        if self.backend is SecretBackend.FILE:
            data = self._read_file()
            data[key] = value
            self._write_file(data)
            return True
        logger.error("no secret backend available", extra={"secret_key": key})
        return False

    def delete(self, key: str) -> None:
        if self.backend is SecretBackend.KEYRING:
            # A missing or unreachable secret is already effectively deleted.
            with contextlib.suppress(Exception):
                _keyring().delete_password(SERVICE, key)
            return
        if self.backend is SecretBackend.FILE:
            data = self._read_file()
            if data.pop(key, None) is not None:
                self._write_file(data)

    def is_set(self, key: str) -> bool:
        return self.get(key) is not None

    def _read_file(self) -> dict[str, str]:
        try:
            raw = self.file.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("secrets file is corrupt; ignoring it")
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _write_file(self, data: dict[str, str]) -> None:
        from praelector.store.atomic import write_json_atomic

        self.file.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.file, data)
        _restrict(self.file)


def _restrict(path: Path) -> None:
    """Owner-only permissions where the platform supports expressing them."""
    try:
        if os.name == "nt":
            # POSIX modes are largely advisory on Windows; the ACL is what matters
            # and it already inherits the user profile's restrictions.
            return
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        logger.warning("could not restrict the secrets file", extra={"path": path.as_posix()})


def _keyring() -> _Keyring:
    import keyring

    return cast(_Keyring, keyring)


def _detect_backend() -> SecretBackend:
    """``keyring`` when a real backend is configured, else the local file."""
    try:
        import keyring
    except Exception:
        return SecretBackend.UNAVAILABLE

    module = type(keyring.get_keyring()).__module__.lower()
    # keyring installs `keyring.core.fail.Keyring` when nothing usable exists (no
    # SecretService, no Keychain, no Windows vault). On such a machine a file in
    # the config dir is the honest second best — and the UI says so.
    if "fail" in module:
        return SecretBackend.FILE
    return SecretBackend.KEYRING
