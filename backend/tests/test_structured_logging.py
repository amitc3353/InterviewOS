"""Tests for structured logging — 15+ tests, zero network calls."""

import asyncio
import json
import logging
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

from backend.structured_logging.structured_logger import (
    StructuredLogger,
    LogLevel,
    StructuredFormatter,
    ConsoleFormatter,
    get_logger,
    configure_logging,
    set_global_context,
    clear_global_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capture_log_output(logger: logging.Logger, format_mode: str = "console") -> StringIO:
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


# ---------------------------------------------------------------------------
# Tests — StructuredFormatter
# ---------------------------------------------------------------------------

def test_structured_formatter_basic_fields():
    """StructuredFormatter includes timestamp, level, event_type, message."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None
    )

    output = formatter.format(record)
    parsed = json.loads(output)

    assert "timestamp" in parsed
    assert parsed["level"] == "INFO"
    assert parsed["event_type"] == "test.logger"
    assert parsed["message"] == "Test message"


def test_structured_formatter_with_session_context():
    """StructuredFormatter includes session_id and turn_number from record."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None
    )
    record.session_id = "test-session-123"
    record.turn_number = 5
    record.phase = "architecture"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["session_id"] == "test-session-123"
    assert parsed["turn_number"] == 5
    assert parsed["phase"] == "architecture"


def test_structured_formatter_with_extra_fields():
    """StructuredFormatter includes extra fields in 'extra' dict."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Error occurred",
        args=(),
        exc_info=None
    )
    record.error_code = "E123"
    record.component = "llm_node"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert "extra" in parsed
    assert parsed["extra"]["error_code"] == "E123"
    assert parsed["extra"]["component"] == "llm_node"


def test_structured_formatter_with_custom_event_type():
    """StructuredFormatter uses custom event_type if provided."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Phase transition",
        args=(),
        exc_info=None
    )
    record.event_type = "phase_transition"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["event_type"] == "phase_transition"


def test_structured_formatter_with_exception():
    """StructuredFormatter includes exception info."""
    formatter = StructuredFormatter()

    try:
        raise ValueError("Test exception")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Exception occurred",
            args=(),
            exc_info=exc_info
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exc_info" in parsed
        assert "ValueError: Test exception" in parsed["exc_info"]


# ---------------------------------------------------------------------------
# Tests — ConsoleFormatter
# ---------------------------------------------------------------------------

def test_console_formatter_basic_format():
    """ConsoleFormatter produces human-readable output."""
    formatter = ConsoleFormatter(fmt="%(message)s")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None
    )

    output = formatter.format(record)

    assert "[INFO]" in output
    assert "test.logger" in output
    assert "Test message" in output


def test_console_formatter_with_session_context():
    """ConsoleFormatter includes session and turn in output."""
    formatter = ConsoleFormatter(fmt="%(message)s")
    record = logging.LogRecord(
        name="interview.agent",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Phase advanced",
        args=(),
        exc_info=None
    )
    record.session_id = "abc123def456"
    record.turn_number = 3

    output = formatter.format(record)

    # Should truncate session_id to 8 chars
    assert "session=abc123de" in output
    assert "turn=3" in output
    assert "Phase advanced" in output


def test_console_formatter_with_custom_event_type():
    """ConsoleFormatter uses custom event_type."""
    formatter = ConsoleFormatter(fmt="%(message)s")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="Warning message",
        args=(),
        exc_info=None
    )
    record.event_type = "llm_timeout"

    output = formatter.format(record)

    assert "llm_timeout" in output


# ---------------------------------------------------------------------------
# Tests — StructuredLogger
# ---------------------------------------------------------------------------

def test_structured_logger_info():
    """StructuredLogger.info() logs INFO level message."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.info("Test info message", event_type="test_event")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test info message"
    assert parsed["event_type"] == "test_event"


def test_structured_logger_error_with_context():
    """StructuredLogger.error() includes session context."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.error(
        "Test error",
        event_type="llm_failure",
        session_id="session-123",
        turn_number=7,
        phase="deep_dive",
        error_code="E500"
    )

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["level"] == "ERROR"
    assert parsed["session_id"] == "session-123"
    assert parsed["turn_number"] == 7
    assert parsed["phase"] == "deep_dive"
    assert parsed["extra"]["error_code"] == "E500"


def test_structured_logger_debug():
    """StructuredLogger.debug() logs DEBUG level message."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.debug("Debug message", turn_number=1)

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["level"] == "DEBUG"
    assert parsed["turn_number"] == 1


def test_structured_logger_warning():
    """StructuredLogger.warning() logs WARNING level message."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.warning("Warning message", event_type="constraint_conflict")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["level"] == "WARNING"
    assert parsed["event_type"] == "constraint_conflict"


def test_structured_logger_critical():
    """StructuredLogger.critical() logs CRITICAL level message."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.critical("Critical failure", session_id="session-999")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["level"] == "CRITICAL"
    assert parsed["session_id"] == "session-999"


@pytest.mark.asyncio
async def test_structured_logger_async_methods():
    """StructuredLogger async methods don't block."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Run multiple async logs concurrently
    await asyncio.gather(
        logger.info_async("Message 1", turn_number=1),
        logger.warning_async("Message 2", turn_number=2),
        logger.error_async("Message 3", turn_number=3),
    )

    output = stream.getvalue()
    lines = [line for line in output.strip().split("\n") if line]

    # Should have 3 log lines
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_structured_logger_debug_async():
    """StructuredLogger.debug_async() works correctly."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    await logger.debug_async("Async debug", session_id="async-session")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["level"] == "DEBUG"
    assert parsed["session_id"] == "async-session"


# ---------------------------------------------------------------------------
# Tests — Global Context
# ---------------------------------------------------------------------------

def test_global_context_session_id():
    """set_global_context() sets session_id for all logs."""
    clear_global_context()
    set_global_context(session_id="global-session-123")

    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Log without explicit session_id
    logger.info("Message with global context")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["session_id"] == "global-session-123"

    clear_global_context()


def test_global_context_with_override():
    """Explicit session_id overrides global context."""
    clear_global_context()
    set_global_context(session_id="global-session")

    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Override with explicit session_id
    logger.info("Message", session_id="override-session")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["session_id"] == "override-session"

    clear_global_context()


def test_clear_global_context():
    """clear_global_context() removes all global context."""
    set_global_context(session_id="test-session", custom_field="value")
    clear_global_context()

    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.info("Message after clear")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert "session_id" not in parsed
    assert "custom_field" not in parsed.get("extra", {})


# ---------------------------------------------------------------------------
# Tests — Configuration
# ---------------------------------------------------------------------------

def test_configure_logging_json_mode():
    """configure_logging() sets JSON format."""
    configure_logging(level=LogLevel.INFO, format_mode="json")

    logger = get_logger("test.config")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.info("Test message")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test message"


def test_configure_logging_console_mode():
    """configure_logging() sets console format."""
    configure_logging(level=LogLevel.DEBUG, format_mode="console")

    logger = get_logger("test.config")

    # Verify format mode is stored
    assert logging._structured_format_mode == "console"


def test_get_logger_default_format():
    """get_logger() uses configured format mode."""
    configure_logging(format_mode="json")

    logger = get_logger("test.logger")

    assert logger.format_mode == "json"


# ---------------------------------------------------------------------------
# Tests — Sentry Integration
# ---------------------------------------------------------------------------

@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True)
@patch("backend.structured_logging.structured_logger.sentry_sdk")
def test_structured_logger_sentry_error_capture(mock_sentry):
    """ERROR level logs are sent to Sentry."""
    logger = StructuredLogger("test.logger", format_mode="json")

    logger.error(
        "Critical error",
        event_type="llm_timeout",
        session_id="sentry-session",
        turn_number=10,
        phase="architecture"
    )

    # Verify Sentry tags were set
    mock_sentry.set_tag.assert_any_call("session_id", "sentry-session")
    mock_sentry.set_tag.assert_any_call("turn_number", "10")
    mock_sentry.set_tag.assert_any_call("phase", "architecture")
    mock_sentry.set_tag.assert_any_call("event_type", "llm_timeout")

    # Verify message was captured
    mock_sentry.capture_message.assert_called_once()


@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", True)
@patch("backend.structured_logging.structured_logger.sentry_sdk")
def test_structured_logger_sentry_exception_capture(mock_sentry):
    """ERROR with exc_info=True captures exception in Sentry."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    logger.error(
        "Exception occurred",
        session_id="exception-session",
        exc_info=True
    )

    # Verify Sentry exception capture
    mock_sentry.capture_exception.assert_called_once()


@patch("backend.structured_logging.structured_logger.SENTRY_AVAILABLE", False)
def test_structured_logger_without_sentry():
    """Logging works when Sentry is not available."""
    logger = StructuredLogger("test.logger", format_mode="json")
    stream = _capture_log_output(logger.logger, format_mode="json")

    # Should not raise exception
    logger.error("Error without Sentry", session_id="no-sentry")

    output = stream.getvalue()
    parsed = _parse_json_log(output)

    assert parsed["level"] == "ERROR"
    assert parsed["session_id"] == "no-sentry"
