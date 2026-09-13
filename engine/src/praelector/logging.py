# SPDX-License-Identifier: Apache-2.0
"""Structured JSON logging with secret-redaction filters."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

# Regex patterns for sensitive tokens and keys
PATTERNS_TO_REDACT = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{10,}", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9_\-]{20,})", re.IGNORECASE),
    re.compile(
        r"((?:api[_-]?key|token|secret|password)[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9_\-\.]{8,}",
        re.IGNORECASE,
    ),
]


def redact_secrets(text: str) -> str:
    """Mask sensitive tokens and keys in log strings."""
    for pattern in PATTERNS_TO_REDACT:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Logging filter that scrubs sensitive strings from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (redact_secrets(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(a) if isinstance(a, str) else a for a in record.args
                )
        return True


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data)


def configure_logging(level_name: str = "INFO") -> None:
    """Configure root logger for structured JSON output with secret redaction."""
    root_logger = logging.getLogger()
    level = getattr(logging, level_name.upper(), logging.INFO)
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactionFilter())
    root_logger.addHandler(handler)
