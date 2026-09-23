# SPDX-License-Identifier: Apache-2.0
"""Praelector engine: torch-free product logic behind a loopback HTTP/WS API."""

from __future__ import annotations

__version__ = "0.1.0"

# Bumped only for changes a client must notice: the WS envelope shape or the
# on-disk project schema (DATA_MODEL.md §14). Additive API changes do not bump it.
SCHEMA_VERSION = 1

__all__ = ["SCHEMA_VERSION", "__version__"]
