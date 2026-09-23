# SPDX-License-Identifier: Apache-2.0
"""Tests for JSON logging and secret redaction (LM-03)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from io import StringIO
from pathlib import Path

import pytest

from praelector.logging import (
    REDACTED,
    JsonFormatter,
    SecretRedactionFilter,
    clear_secrets,
    configure_logging,
    forget_secret,
    redact,
    register_secret,
)

Emit = Callable[..., dict[str, object]]


@pytest.fixture(autouse=True)
def _isolate_secrets() -> Iterator[None]:
    clear_secrets()
    yield
    clear_secrets()


@pytest.fixture
def emit() -> Iterator[Emit]:
    """Log a record and hand back the parsed JSON line it produced."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactionFilter())
    logger = logging.getLogger("test.redaction")
    logger.setLevel(logging.DEBUG)
    logger.handlers = [handler]
    logger.propagate = False

    def _emit(message: str, **extra: object) -> dict[str, object]:
        logger.info(message, extra=extra)
        line = stream.getvalue().strip().splitlines()[-1]
        return json.loads(line)

    yield _emit
    logger.handlers = []


def test_a_registered_secret_never_reaches_the_line(emit: Emit) -> None:
    secret = "hunter2-super-secret-value"
    register_secret(secret)
    record = emit(f"connecting with {secret} now")
    assert secret not in json.dumps(record)
    assert REDACTED in str(record["message"])


def test_secrets_in_extra_fields_are_redacted_too(emit: Emit) -> None:
    register_secret("another-secret-value")
    record = emit("llm call", detail={"api_key": "another-secret-value"})
    assert "another-secret-value" not in json.dumps(record)


def test_short_values_are_not_registered() -> None:
    register_secret("abc")
    # Too short to match safely: masking every "abc" would shred ordinary prose.
    assert redact("abc") == "abc"


def test_forget_secret_stops_redaction() -> None:
    register_secret("rotated-secret-value")
    assert "rotated-secret-value" not in redact("rotated-secret-value")
    forget_secret("rotated-secret-value")
    assert "rotated-secret-value" in redact("rotated-secret-value")


def test_the_longest_registered_secret_wins() -> None:
    register_secret("abc123")
    register_secret("abc123xyz")
    assert redact("abc123xyz") == REDACTED


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("Authorization: Bearer abcdef0123456789", "Bearer "),
        ('{"api_key": "zzzzzzzz"}', "api_key"),
        # Low entropy and a short AIza tail on purpose: the redactor matches the
        # shape, and gitleaks' generic-api-key / gcp-api-key rules do not.
        ("token=aaaaaaaaaaaaaaaa", "token="),
        ("sk-proj-ABCDEFGHIJKLMNOP", ""),
        ("ghp_0123456789abcdefghijABCDEF", ""),
        ("AIzaSyA-0123456789abcdef", ""),
    ],
)
def test_secret_shapes_are_redacted_without_registration(text: str, kept: str) -> None:
    result = redact(text)
    assert REDACTED in result
    if kept:
        assert kept in result


def test_plain_text_survives_redaction() -> None:
    text = "Anna odłożyła raport. — Nie zdążymy — powiedziała cicho."
    assert redact(text) == text


def test_json_output_stays_parseable_after_redaction(emit: Emit) -> None:
    register_secret("value-with-quotes-and-\\-backslash")
    record = emit('said "value-with-quotes-and-\\-backslash" loudly')
    assert isinstance(record["message"], str)
    assert record["level"] == "info"
    assert record["logger"] == "test.redaction"
    assert str(record["ts"]).endswith("Z")


def test_exception_info_is_included() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.exc")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    try:
        try:
            raise ValueError("boom")
        except ValueError:
            logger.error("it failed", exc_info=True)
        payload = json.loads(stream.getvalue().strip())
        assert "ValueError: boom" in str(payload["exc"])
    finally:
        logger.handlers = []


def test_configure_logging_replaces_handlers_and_silences_access_logs(tmp_path: Path) -> None:
    configure_logging("INFO", log_file=tmp_path / "engine.log", json_output=True)
    try:
        assert logging.getLogger("uvicorn.access").disabled is True
        assert len(logging.getLogger().handlers) == 2
        logging.getLogger("test").info("hello from the engine")
        written = (tmp_path / "engine.log").read_text(encoding="utf-8").strip()
        assert json.loads(written)["message"] == "hello from the engine"
    finally:
        configure_logging("WARNING", json_output=False)


def test_configure_logging_is_idempotent(tmp_path: Path) -> None:
    configure_logging("INFO", json_output=True)
    configure_logging("INFO", json_output=True)
    try:
        assert len(logging.getLogger().handlers) == 1
    finally:
        configure_logging("WARNING", json_output=False)


def test_formatter_without_json_is_still_redacted() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(SecretRedactionFilter())
    logger = logging.getLogger("test.plain")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    register_secret("plain-text-secret")
    try:
        logger.info("leaking plain-text-secret here")
        assert "plain-text-secret" not in stream.getvalue()
        assert REDACTED in stream.getvalue()
    finally:
        logger.handlers = []


def test_json_formatter_promotes_extra_keys() -> None:
    record = logging.LogRecord("t", logging.INFO, "f.py", 1, "msg", None, None)
    record.error_code = "ebook.drm_detected"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["error_code"] == "ebook.drm_detected"
    assert "args" not in payload
    assert "msg" not in payload
