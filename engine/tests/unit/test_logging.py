# SPDX-License-Identifier: Apache-2.0
"""Unit tests for JSON logging and secret redaction."""

from __future__ import annotations

import json
import logging
from io import StringIO

from praelector.logging import JsonFormatter, SecretRedactionFilter, redact_secrets


def test_redact_secrets_bearer() -> None:
    text = "Sending request with Bearer secret-token-abc-12345 to loopback"
    redacted = redact_secrets(text)
    assert "secret-token-abc-12345" not in redacted
    assert "Bearer [REDACTED]" in redacted


def test_redact_secrets_api_key() -> None:
    text = 'Using provider with api_key="sk-1234567890abcdef12345678"'
    redacted = redact_secrets(text)
    assert "sk-1234567890abcdef12345678" not in redacted


def test_json_formatter_and_filter() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactionFilter())

    logger = logging.getLogger("test_redact_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger.info("Connecting with Bearer super-secret-token-value")
    output = stream.getvalue().strip()
    data = json.loads(output)
    assert data["level"] == "INFO"
    assert "super-secret-token-value" not in data["message"]
    assert "Bearer [REDACTED]" in data["message"]
