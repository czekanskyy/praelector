# SPDX-License-Identifier: Apache-2.0
"""Secret credential management for LLM profiles (LM-03)."""

from __future__ import annotations

from praelector.store.secrets import SecretStore


def _secret_key_for_profile(profile_id: str) -> str:
    return f"llm_profile:{profile_id}"


def get_profile_api_key(secret_store: SecretStore, profile_id: str) -> str | None:
    """Retrieve decrypted API key for an LLM profile."""
    return secret_store.get_secret(_secret_key_for_profile(profile_id))


def set_profile_api_key(secret_store: SecretStore, profile_id: str, key: str) -> None:
    """Save an API key into keyring/encrypted fallback."""
    secret_store.set_secret(_secret_key_for_profile(profile_id), key)


def delete_profile_api_key(secret_store: SecretStore, profile_id: str) -> None:
    """Remove an API key from keyring/encrypted fallback."""
    secret_store.delete_secret(_secret_key_for_profile(profile_id))
