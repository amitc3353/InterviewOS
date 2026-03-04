"""Structured logging with JSON format for Sentry/GlitchTip integration.

This module provides a dual-format logging approach:
- Console format for development (human-readable)
- JSON format for production (GlitchTip/Sentry integration)

All logs include required fields: session_id, turn_number, event_type, timestamp.
Async wrapper prevents voice loop latency in real-time interview scenarios.
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False


class LogLevel(Enum):
    """Standard Python logging levels."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


# Global context for session-level logging
_global_context: Dict[str, Any] = {}


def set_global_context(session_id: Optional[str] = None, **kwargs) -> None:
    """
    Set global logging context (session_id, etc.).

    Args:
        session_id: Unique session identifier
        **kwargs: Additional context fields
    """
    global _global_context
    if session_id is not None:
        _global_context["session_id"] = session_id
    _global_context.update(kwargs)


def clear_global_context() -> None:
    """Clear global logging context."""
    global _global_context
    _global_context = {}


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.

    Outputs logs in JSON format with required fields:
    - timestamp (ISO 8601)
    - level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    - event_type (logger name or custom event)
    - session_id (from context)
    - turn_number (from context)
    - message (log message)
    - extra fields (any additional data)
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Extract extra fields from record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info",
            ]:
                extra_fields[key] = value

        # Build structured log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "event_type": getattr(record, "event_type", record.name),
            "message": record.getMessage(),
        }

        # Add session_id from global context or record
        session_id = extra_fields.pop("session_id", None) or _global_context.get("session_id")
        if session_id:
            log_entry["session_id"] = session_id

        # Add turn_number from global context or record
        turn_number = extra_fields.pop("turn_number", None) or _global_context.get("turn_number")
        if turn_number is not None:
            log_entry["turn_number"] = turn_number

        # Add phase from global context or record
        phase = extra_fields.pop("phase", None) or _global_context.get("phase")
        if phase:
            log_entry["phase"] = phase

        # Add any remaining extra fields
        if extra_fields:
            log_entry["extra"] = extra_fields

        # Add exception info if present
        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable console formatter for development.

    Format: [LEVEL] event_type | session=XXX turn=N | message
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console."""
        # Extract extra fields
        session_id = getattr(record, "session_id", None) or _global_context.get("session_id")
        turn_number = getattr(record, "turn_number", None) or _global_context.get("turn_number")
        event_type = getattr(record, "event_type", record.name)

        # Build context string
        context_parts = []
        if session_id:
            # Truncate session_id for readability
            short_session_id = session_id[:8] if len(session_id) > 8 else session_id
            context_parts.append(f"session={short_session_id}")
        if turn_number is not None:
            context_parts.append(f"turn={turn_number}")

        context_str = " | ".join(context_parts) if context_parts else ""

        # Build final message
        parts = [f"[{record.levelname}]", event_type]
        if context_str:
            parts.append(context_str)
        parts.append(record.getMessage())

        result = " | ".join(parts)

        # Add exception info if present
        if record.exc_info:
            result += "\n" + self.formatException(record.exc_info)

        return result


class StructuredLogger:
    """
    Structured logger with dual-format support.

    Provides async logging methods to prevent voice loop latency.
    Integrates with Sentry/GlitchTip for error tracking.
    """

    def __init__(self, name: str, format_mode: str = "console"):
        """
        Initialize structured logger.

        Args:
            name: Logger name (typically module name)
            format_mode: "console" or "json"
        """
        self.name = name
        self.logger = logging.getLogger(name)
        self.format_mode = format_mode

    def _log(
        self,
        level: LogLevel,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        exc_info: bool = False,
        **extra_fields
    ) -> None:
        """
        Internal log method with structured fields.

        Args:
            level: Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
            message: Log message
            event_type: Event type/category (defaults to logger name)
            session_id: Session identifier
            turn_number: Turn number in interview
            phase: Interview phase
            exc_info: Include exception info
            **extra_fields: Additional fields to include
        """
        # Build extra dict for LogRecord
        extra = extra_fields.copy()
        if event_type:
            extra["event_type"] = event_type
        if session_id:
            extra["session_id"] = session_id
        if turn_number is not None:
            extra["turn_number"] = turn_number
        if phase:
            extra["phase"] = phase

        # Log with extra fields
        self.logger.log(level.value, message, exc_info=exc_info, extra=extra)

        # Also send to Sentry for ERROR/CRITICAL levels
        if level in (LogLevel.ERROR, LogLevel.CRITICAL) and SENTRY_AVAILABLE:
            try:
                # Set Sentry context
                if session_id:
                    sentry_sdk.set_tag("session_id", session_id)
                if turn_number is not None:
                    sentry_sdk.set_tag("turn_number", str(turn_number))
                if phase:
                    sentry_sdk.set_tag("phase", phase)
                if event_type:
                    sentry_sdk.set_tag("event_type", event_type)

                # Add extra context
                if extra_fields:
                    sentry_sdk.set_context("log_extra", extra_fields)

                # Capture message (not exception unless exc_info=True)
                if exc_info:
                    sentry_sdk.capture_exception()
                else:
                    sentry_sdk.capture_message(message, level=level.name.lower())
            except Exception:
                # Never let Sentry break logging
                pass

    async def _log_async(
        self,
        level: LogLevel,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        exc_info: bool = False,
        **extra_fields
    ) -> None:
        """
        Async log method to prevent blocking voice loop.

        Runs log operation in executor to avoid I/O blocking.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._log,
            level,
            message,
            event_type,
            session_id,
            turn_number,
            phase,
            exc_info,
            *(),  # No positional args
            **extra_fields
        )

    def debug(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        **extra_fields
    ) -> None:
        """Log DEBUG level message."""
        self._log(LogLevel.DEBUG, message, event_type, session_id, turn_number, phase, False, **extra_fields)

    async def debug_async(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        **extra_fields
    ) -> None:
        """Log DEBUG level message asynchronously."""
        await self._log_async(LogLevel.DEBUG, message, event_type, session_id, turn_number, phase, False, **extra_fields)

    def info(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        **extra_fields
    ) -> None:
        """Log INFO level message."""
        self._log(LogLevel.INFO, message, event_type, session_id, turn_number, phase, False, **extra_fields)

    async def info_async(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        **extra_fields
    ) -> None:
        """Log INFO level message asynchronously."""
        await self._log_async(LogLevel.INFO, message, event_type, session_id, turn_number, phase, False, **extra_fields)

    def warning(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        **extra_fields
    ) -> None:
        """Log WARNING level message."""
        self._log(LogLevel.WARNING, message, event_type, session_id, turn_number, phase, False, **extra_fields)

    async def warning_async(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        **extra_fields
    ) -> None:
        """Log WARNING level message asynchronously."""
        await self._log_async(LogLevel.WARNING, message, event_type, session_id, turn_number, phase, False, **extra_fields)

    def error(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        exc_info: bool = False,
        **extra_fields
    ) -> None:
        """Log ERROR level message."""
        self._log(LogLevel.ERROR, message, event_type, session_id, turn_number, phase, exc_info, **extra_fields)

    async def error_async(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        exc_info: bool = False,
        **extra_fields
    ) -> None:
        """Log ERROR level message asynchronously."""
        await self._log_async(LogLevel.ERROR, message, event_type, session_id, turn_number, phase, exc_info, **extra_fields)

    def critical(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        exc_info: bool = False,
        **extra_fields
    ) -> None:
        """Log CRITICAL level message."""
        self._log(LogLevel.CRITICAL, message, event_type, session_id, turn_number, phase, exc_info, **extra_fields)

    async def critical_async(
        self,
        message: str,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        phase: Optional[str] = None,
        exc_info: bool = False,
        **extra_fields
    ) -> None:
        """Log CRITICAL level message asynchronously."""
        await self._log_async(LogLevel.CRITICAL, message, event_type, session_id, turn_number, phase, exc_info, **extra_fields)


def get_logger(name: str, format_mode: Optional[str] = None) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)
        format_mode: "console" or "json" (defaults to configured mode)

    Returns:
        StructuredLogger instance
    """
    if format_mode is None:
        # Use configured format mode (set by configure_logging)
        format_mode = getattr(logging, "_structured_format_mode", "console")

    return StructuredLogger(name, format_mode)


def configure_logging(
    level: LogLevel = LogLevel.INFO,
    format_mode: str = "console",
    include_timestamp: bool = True
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Minimum log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
        format_mode: "console" (human-readable) or "json" (structured)
        include_timestamp: Include timestamp in console logs
    """
    # Store format mode for get_logger
    logging._structured_format_mode = format_mode

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level.value)

    # Remove existing handlers
    root_logger.handlers = []

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level.value)

    # Set formatter based on mode
    if format_mode == "json":
        formatter = StructuredFormatter()
    else:
        # Console mode with optional timestamp
        if include_timestamp:
            formatter = ConsoleFormatter(fmt="%(asctime)s - %(message)s")
        else:
            formatter = ConsoleFormatter(fmt="%(message)s")

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Log configuration
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={level.name}, format={format_mode}")
