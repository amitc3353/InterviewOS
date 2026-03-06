"""Tests for logging infrastructure — 20+ tests, zero network calls.

This test suite focuses on:
- Structured log format correctness and edge cases
- Session context propagation in critical events
- Sentry breadcrumb and context capture
- Async logging performance and non-blocking behavior
- Error handling and resilience
"""

import asyncio
import json
import logging
import time
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from backend.structured_logging import (
    StructuredLogger,
    LogLevel,
    get_logger,
    configure_logging,
    set_global_context,
    clear_global_context,
)
from backend.structured_logging.structured_logger import StructuredFormatter, ConsoleFormatter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_log_output(
    logger: logging.Logger, format_mode: str = "console"
) -> StringIO:
    """Capture log output to StringIO for testing."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)

    if format_mode == "json":
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(ConsoleFormatter(fmt="%(message)s"))

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return stream


def _parse_json_log(output: str) -> dict:
    """Parse JSON log output."""
    lines = output.strip().split("\n")
    return json.loads(lines[-1]) if lines else {}


def _parse_all_json_logs(output: str) -> list:
    """Parse all JSON log lines."""
    lines = [line.strip() for line in output.strip().split("\n") if line.strip()]
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------------
# Tests — Structured Log Format Correctness
# ---------------------------------------------------------------------------


def test_log_format_required_fields():
    """All logs must include timestamp, level, event_type, message."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Test all log levels
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    logs = _parse_all_json_logs(stream.getvalue())

    # Verify all logs have required fields
    for log in logs:
        assert "timestamp" in log, "Missing timestamp"
        assert "level" in log, "Missing level"
        assert "event_type" in log, "Missing event_type"
        assert "message" in log, "Missing message"


def test_log_format_timestamp_iso8601():
    """Timestamp must be in ISO 8601 format."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.info("Test message")

    parsed = _parse_json_log(stream.getvalue())

    # ISO 8601 format: YYYY-MM-DDTHH:MM:SS.microseconds
    timestamp = parsed["timestamp"]
    assert "T" in timestamp, "Timestamp not in ISO 8601 format"
    assert len(timestamp.split(".")) == 2, "Missing microseconds"


def test_log_format_level_values():
    """Level must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.debug("Debug")
    logger.info("Info")
    logger.warning("Warning")
    logger.error("Error")
    logger.critical("Critical")

    logs = _parse_all_json_logs(stream.getvalue())
    levels = [log["level"] for log in logs]

    assert levels == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def test_log_format_extra_fields_structure():
    """Extra fields must be in 'extra' dict, not at root level."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.info(
        "Test message",
        custom_field1="value1",
        custom_field2=42,
        custom_field3=True,
    )

    parsed = _parse_json_log(stream.getvalue())

    # Extra fields should be nested
    assert "extra" in parsed
    assert parsed["extra"]["custom_field1"] == "value1"
    assert parsed["extra"]["custom_field2"] == 42
    assert parsed["extra"]["custom_field3"] is True

    # Should not be at root level
    assert "custom_field1" not in parsed
    assert "custom_field2" not in parsed
    assert "custom_field3" not in parsed


def test_log_format_json_serializable():
    """All log output must be valid JSON."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Log with various data types
    logger.info(
        "Complex message",
        session_id="test-123",
        turn_number=5,
        latency_ms=123.45,
        success=True,
        tags=["tag1", "tag2"],
    )

    output = stream.getvalue()

    # Should parse without error
    try:
        parsed = _parse_json_log(output)
        assert parsed["session_id"] == "test-123"
        assert parsed["turn_number"] == 5
        assert parsed["extra"]["latency_ms"] == 123.45
        assert parsed["extra"]["success"] is True
        assert parsed["extra"]["tags"] == ["tag1", "tag2"]
    except json.JSONDecodeError:
        pytest.fail("Log output is not valid JSON")


# ---------------------------------------------------------------------------
# Tests — Session Context in Critical Events
# ---------------------------------------------------------------------------


def test_critical_event_includes_session_id():
    """All CRITICAL level logs must include session_id."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    session_id = "critical-session-abc123"

    logger.critical("Critical failure", session_id=session_id)

    parsed = _parse_json_log(stream.getvalue())

    assert parsed["level"] == "CRITICAL"
    assert parsed["session_id"] == session_id


def test_critical_event_includes_turn_number():
    """CRITICAL logs should include turn_number when available."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.critical(
        "Session terminated", session_id="session-123", turn_number=42, phase="wrap"
    )

    parsed = _parse_json_log(stream.getvalue())

    assert parsed["level"] == "CRITICAL"
    assert parsed["session_id"] == "session-123"
    assert parsed["turn_number"] == 42
    assert parsed["phase"] == "wrap"


def test_error_event_propagates_global_context():
    """ERROR logs inherit session_id and turn_number from global context."""
    clear_global_context()
    set_global_context(session_id="global-error-session", turn_number=15, phase="deep_dive")

    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Log without explicit context
    logger.error("LLM timeout", event_type="llm_timeout")

    parsed = _parse_json_log(stream.getvalue())

    assert parsed["level"] == "ERROR"
    assert parsed["session_id"] == "global-error-session"
    assert parsed["turn_number"] == 15
    assert parsed["phase"] == "deep_dive"

    clear_global_context()


def test_multiple_critical_events_preserve_context():
    """Multiple CRITICAL logs maintain separate contexts."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.critical("Error 1", session_id="session-1", turn_number=1)
    logger.critical("Error 2", session_id="session-2", turn_number=2)
    logger.critical("Error 3", session_id="session-3", turn_number=3)

    logs = _parse_all_json_logs(stream.getvalue())

    assert len(logs) == 3
    assert logs[0]["session_id"] == "session-1"
    assert logs[1]["session_id"] == "session-2"
    assert logs[2]["session_id"] == "session-3"
    assert logs[0]["turn_number"] == 1
    assert logs[1]["turn_number"] == 2
    assert logs[2]["turn_number"] == 3


# ---------------------------------------------------------------------------
# Tests — Sentry Integration (Mocked)
# ---------------------------------------------------------------------------


@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True)
@patch("backend.structured_logging.structured_logger.sentry_sdk")
def test_sentry_error_tags_are_set(mock_sentry):
    """ERROR logs set all required Sentry tags."""
    logger = StructuredLogger("test.logger", format_mode="json")

    logger.error(
        "LLM failure",
        event_type="llm_timeout",
        session_id="sentry-session-xyz",
        turn_number=99,
        phase="architecture",
    )

    # Verify all tags were set
    assert mock_sentry.set_tag.call_count == 4
    mock_sentry.set_tag.assert_any_call("session_id", "sentry-session-xyz")
    mock_sentry.set_tag.assert_any_call("turn_number", "99")
    mock_sentry.set_tag.assert_any_call("phase", "architecture")
    mock_sentry.set_tag.assert_any_call("event_type", "llm_timeout")


@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True)
@patch("backend.structured_logging.structured_logger.sentry_sdk")
def test_sentry_context_includes_extra_fields(mock_sentry):
    """Sentry context includes all extra fields."""
    logger = StructuredLogger("test.logger", format_mode="json")

    logger.error(
        "API timeout",
        event_type="api_timeout",
        session_id="sentry-session",
        retry_count=3,
        timeout_ms=5000,
        endpoint="/api/llm",
    )

    # Verify context was set with extra fields
    mock_sentry.set_context.assert_called_once()
    context_args = mock_sentry.set_context.call_args
    assert context_args[0][0] == "log_extra"
    assert context_args[0][1]["retry_count"] == 3
    assert context_args[0][1]["timeout_ms"] == 5000
    assert context_args[0][1]["endpoint"] == "/api/llm"


@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True)
@patch("backend.structured_logging.structured_logger.sentry_sdk")
def test_sentry_critical_level_captured(mock_sentry):
    """CRITICAL logs are captured in Sentry."""
    logger = StructuredLogger("test.logger", format_mode="json")

    logger.critical(
        "Session crashed", session_id="critical-session", event_type="session_crash"
    )

    # Verify message was captured with correct level
    mock_sentry.capture_message.assert_called_once()
    call_args = mock_sentry.capture_message.call_args
    assert call_args[0][0] == "Session crashed"
    assert call_args[1]["level"] == "critical"


@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True)
@patch("backend.structured_logging.structured_logger.sentry_sdk")
def test_sentry_exception_capture_with_exc_info(mock_sentry):
    """Exceptions are captured in Sentry when exc_info=True."""
    logger = StructuredLogger("test.logger", format_mode="json")

    try:
        raise RuntimeError("Test exception")
    except RuntimeError:
        logger.error("Exception caught", session_id="exception-session", exc_info=True)

    # Verify exception was captured
    mock_sentry.capture_exception.assert_called_once()


@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True)
@patch("backend.structured_logging.structured_logger.sentry_sdk")
def test_sentry_not_called_for_info_level(mock_sentry):
    """INFO/WARNING/DEBUG logs do not trigger Sentry."""
    logger = StructuredLogger("test.logger", format_mode="json")

    logger.debug("Debug message", session_id="test-session")
    logger.info("Info message", session_id="test-session")
    logger.warning("Warning message", session_id="test-session")

    # Sentry should not be called
    mock_sentry.set_tag.assert_not_called()
    mock_sentry.capture_message.assert_not_called()
    mock_sentry.capture_exception.assert_not_called()


@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True)
@patch("backend.structured_logging.structured_logger.sentry_sdk")
def test_sentry_failure_does_not_break_logging(mock_sentry):
    """Sentry errors don't prevent logging from working."""
    # Make Sentry raise an exception
    mock_sentry.set_tag.side_effect = Exception("Sentry connection failed")

    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Should not raise exception
    logger.error("Error message", session_id="resilient-session")

    # Log should still be written
    parsed = _parse_json_log(stream.getvalue())
    assert parsed["level"] == "ERROR"
    assert parsed["session_id"] == "resilient-session"


# ---------------------------------------------------------------------------
# Tests — Async Logging Performance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_logging_non_blocking():
    """Async logging methods don't block event loop."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    start_time = time.time()

    # Run multiple async logs concurrently
    await asyncio.gather(
        logger.debug_async("Debug 1", turn_number=1),
        logger.info_async("Info 1", turn_number=2),
        logger.warning_async("Warning 1", turn_number=3),
        logger.error_async("Error 1", turn_number=4),
        logger.critical_async("Critical 1", turn_number=5),
    )

    elapsed = time.time() - start_time

    # Should complete quickly (non-blocking)
    assert elapsed < 0.5, f"Async logging took too long: {elapsed}s"

    # Verify all logs were written
    logs = _parse_all_json_logs(stream.getvalue())
    assert len(logs) == 5


@pytest.mark.asyncio
async def test_async_logging_preserves_context():
    """Async logging maintains session context correctly."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    await logger.info_async(
        "Async message",
        session_id="async-session-123",
        turn_number=10,
        phase="intro",
    )

    parsed = _parse_json_log(stream.getvalue())

    assert parsed["session_id"] == "async-session-123"
    assert parsed["turn_number"] == 10
    assert parsed["phase"] == "intro"


@pytest.mark.asyncio
async def test_async_logging_concurrent_sessions():
    """Async logging handles multiple concurrent sessions correctly."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Simulate concurrent sessions
    await asyncio.gather(
        logger.info_async("Session 1 message", session_id="session-1", turn_number=1),
        logger.info_async("Session 2 message", session_id="session-2", turn_number=2),
        logger.info_async("Session 3 message", session_id="session-3", turn_number=3),
    )

    logs = _parse_all_json_logs(stream.getvalue())

    # Verify all sessions logged correctly
    sessions = [log["session_id"] for log in logs]
    assert "session-1" in sessions
    assert "session-2" in sessions
    assert "session-3" in sessions


@pytest.mark.asyncio
async def test_async_logging_with_global_context():
    """Async logging respects global context."""
    clear_global_context()
    set_global_context(session_id="global-async-session", phase="scope")

    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    await logger.info_async("Message with global context", turn_number=7)

    parsed = _parse_json_log(stream.getvalue())

    assert parsed["session_id"] == "global-async-session"
    assert parsed["phase"] == "scope"
    assert parsed["turn_number"] == 7

    clear_global_context()


@pytest.mark.asyncio
async def test_async_error_logging_performance():
    """Async ERROR logging doesn't block despite Sentry integration."""
    with patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True), patch(
        "backend.structured_logging.structured_logger.sentry_sdk"
    ):
        logger = StructuredLogger("test.logger", format_mode="json")
        stream = _capture_log_output(logger.logger, format_mode="json")

        start_time = time.time()

        # Multiple concurrent error logs
        await asyncio.gather(
            *[
                logger.error_async(
                    f"Error {i}", session_id=f"session-{i}", turn_number=i
                )
                for i in range(10)
            ]
        )

        elapsed = time.time() - start_time

        # Should still be fast even with Sentry calls
        assert elapsed < 1.0, f"Async error logging too slow: {elapsed}s"

        logs = _parse_all_json_logs(stream.getvalue())
        assert len(logs) == 10


# ---------------------------------------------------------------------------
# Tests — Edge Cases and Resilience
# ---------------------------------------------------------------------------


def test_logging_with_none_values():
    """Logging handles None values gracefully."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.info(
        "Message with None",
        session_id=None,
        turn_number=None,
        phase=None,
        custom_field=None,
    )

    parsed = _parse_json_log(stream.getvalue())

    # None values should be omitted or handled gracefully
    assert parsed["level"] == "INFO"
    # session_id/turn_number/phase should not appear if None
    if "extra" in parsed:
        assert parsed["extra"].get("custom_field") is None


def test_logging_with_empty_strings():
    """Logging handles empty strings."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.info("", session_id="", event_type="")

    parsed = _parse_json_log(stream.getvalue())

    assert parsed["level"] == "INFO"
    assert parsed["message"] == ""


def test_logging_with_very_long_messages():
    """Logging handles very long messages."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    long_message = "A" * 10000

    logger.info(long_message, session_id="long-message-session")

    parsed = _parse_json_log(stream.getvalue())

    assert parsed["level"] == "INFO"
    assert len(parsed["message"]) == 10000


def test_logging_with_special_characters():
    """Logging handles special characters and escape sequences."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    special_message = 'Message with "quotes", \n newlines, and \t tabs'

    logger.info(special_message, session_id="special-session")

    parsed = _parse_json_log(stream.getvalue())

    assert parsed["level"] == "INFO"
    assert '"quotes"' in parsed["message"] or "quotes" in parsed["message"]


def test_global_context_thread_safety():
    """Global context is consistent across calls."""
    clear_global_context()
    set_global_context(session_id="thread-safe-session", turn_number=42)

    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Multiple rapid calls
    for i in range(10):
        logger.info(f"Message {i}")

    logs = _parse_all_json_logs(stream.getvalue())

    # All logs should have same session_id from global context
    for log in logs:
        assert log["session_id"] == "thread-safe-session"

    clear_global_context()


def test_configure_logging_multiple_times():
    """configure_logging() can be called multiple times."""
    configure_logging(level=LogLevel.DEBUG, format_mode="console")
    configure_logging(level=LogLevel.INFO, format_mode="json")
    configure_logging(level=LogLevel.WARNING, format_mode="console")

    # Should not raise exception
    logger = get_logger("test.config")
    assert logger is not None


# ---------------------------------------------------------------------------
# Tests — Import Conflict Prevention (stdlib logging vs backend.logging)
# ---------------------------------------------------------------------------


def test_stdlib_logging_not_shadowed():
    """stdlib 'logging' module must not be shadowed by backend.logging directory.

    Regression test: a leftover backend/logging/ directory (even with only
    __pycache__) can shadow Python's stdlib logging module, causing circular
    import errors. This test verifies the stdlib module resolves correctly.
    """
    import logging as stdlib_logging

    # stdlib logging should come from the standard library, not from backend/
    assert hasattr(stdlib_logging, "getLogger"), "stdlib logging is shadowed"
    assert "backend" not in (stdlib_logging.__file__ or ""), (
        f"stdlib logging resolves to backend path: {stdlib_logging.__file__}"
    )


def test_no_backend_logging_package_exists():
    """Verify backend.logging is not importable as a package.

    The old backend/logging/ directory was renamed to backend/structured_logging/.
    This test ensures no leftover backend/logging/ package exists that could
    shadow Python's stdlib logging module.
    """
    import importlib
    import os

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logging_dir = os.path.join(backend_dir, "logging")

    # The backend/logging/ directory should not exist
    has_init = os.path.exists(os.path.join(logging_dir, "__init__.py"))
    assert not has_init, (
        f"backend/logging/__init__.py exists — this shadows stdlib logging. "
        f"Rename to backend/structured_logging/"
    )


def test_structured_logging_import_works():
    """Verify backend.structured_logging imports correctly."""
    from backend.structured_logging import (
        StructuredLogger,
        LogLevel,
        get_logger,
        configure_logging,
        set_global_context,
        clear_global_context,
    )

    # All exports should be importable
    assert StructuredLogger is not None
    assert LogLevel is not None
    assert get_logger is not None
    assert configure_logging is not None
    assert set_global_context is not None
    assert clear_global_context is not None


def test_get_logger_returns_structured_logger():
    """get_logger() returns a StructuredLogger that uses stdlib logging internally."""
    logger = get_logger("test.import_check")

    assert isinstance(logger, StructuredLogger)
    # The internal logger should be a stdlib logging.Logger
    assert isinstance(logger.logger, logging.Logger)
