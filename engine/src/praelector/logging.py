# SPDX-License-Identifier: Apache-2.0
"""JSON logging with secret redaction (LM-03: never log secrets).

Two layers, because one is not enough:

1. Values registered with :func:`register_secret` — the launch token, every LLM
   API key — are replaced wherever they appear. Registration is mandatory before
   a secret is used, and it is exact-match, so it cannot be fooled by
   formatting.
2. Shape-based patterns (``Bearer …``, ``sk-…``, ``key=value`` pairs) catch a
   secret nobody registered.

Redaction runs on the **formatted line**, not on the record, so a secret that
arrives through an unexpected ``extra`` field is still caught. The replacement
token contains no quotes or backslashes, so the JSON stays parseable.

Logs go to **stderr**. stdout carries exactly one line — the ready handshake —
and anything else printed there would break the shell's parser.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import re
import sys
import threading
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REDACTED = "[REDACTED]"
_MIN_SECRET_LENGTH = 8

_secrets_lock = threading.Lock()
_secrets: set[str] = set()

_KV_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|secret|passwd|password|token)"
    r"(['\"]?\s*[:=]\s*['\"]?)([^\s'\",;}\]]+)"
)
# Patterns whose first group is the part worth keeping ("Bearer ", "").
_SHAPE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
)
_OPAQUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),
)

_RESERVED_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def register_secret(value: str | None) -> None:
    """Make ``value`` unprintable in every log line this process writes."""
    if not value or len(value) < _MIN_SECRET_LENGTH:
        return
    with _secrets_lock:
        _secrets.add(value)


def forget_secret(value: str | None) -> None:
    """Drop a rotated secret so it stops masking unrelated text."""
    if not value:
        return
    with _secrets_lock:
        _secrets.discard(value)


def clear_secrets() -> None:
    """Forget every registered secret. For test teardown; production rotates."""
    with _secrets_lock:
        _secrets.clear()


def _registered() -> list[str]:
    with _secrets_lock:
        # Longest first: a short secret nested in a longer one must not win.
        return sorted(_secrets, key=len, reverse=True)


def redact(text: str) -> str:
    """Replace every known secret and secret-shaped token in ``text``."""
    for secret in _registered():
        if secret in text:
            text = text.replace(secret, REDACTED)

    def _kv(match: re.Match[str]) -> str:
        return f"{match.group(1)}{match.group(2)}{REDACTED}"

    text = _KV_PATTERN.sub(_kv, text)
    for pattern in _SHAPE_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    for pattern in _OPAQUE_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Redacts the message and args of a record, for plain-text handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, Mapping):
            record.args = {
                key: redact(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, ``extra`` keys promoted to top level."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            # RFC 3339 UTC with a Z suffix, matching the WS envelope.
            "ts": (
                datetime.fromtimestamp(record.created, tz=UTC)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            ),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return redact(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=False))


def configure_logging(
    level: str = "INFO",
    *,
    log_file: Path | None = None,
    json_output: bool = True,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Point the root logger at stderr (and optionally a rolling file).

    Idempotent: repeated calls replace handlers rather than stacking them, which
    matters because tests reconfigure per case.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    resolved_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    root.setLevel(resolved_level)

    formatter: logging.Formatter = (
        JsonFormatter()
        if json_output
        else logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s")
    )

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(formatter)
    stderr.addFilter(SecretRedactionFilter())
    root.addHandler(stderr)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        rolling = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        rolling.setFormatter(formatter)
        rolling.addFilter(SecretRedactionFilter())
        root.addHandler(rolling)

    # uvicorn's own loggers would otherwise double-format or, worse, log request
    # lines. The access log is disabled outright: a WebSocket handshake carries
    # the bearer token in its query string.
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).disabled = True
    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def silence_loggers(names: Iterable[str]) -> None:
    for name in names:
        logging.getLogger(name).setLevel(logging.WARNING)
