# Structured Logging Guide

## Overview

InterviewOS uses a structured logging system designed for seamless integration with Sentry/GlitchTip error tracking. The system provides:

- **Dual-format output**: JSON for production (GlitchTip/Sentry) or human-readable console for development
- **Required fields**: All logs include `timestamp`, `level`, `event_type`, `message`
- **Interview context**: Automatic inclusion of `session_id`, `turn_number`, `phase` when available
- **Async logging**: Non-blocking async methods prevent voice loop latency in real-time scenarios
- **Sentry integration**: ERROR/CRITICAL logs automatically sent to Sentry/GlitchTip with full context

## Key Features

### Structured JSON Format

Production logs use JSON format for easy parsing and querying:

```json
{
  "timestamp": "2026-03-04T10:15:30.123456",
  "level": "ERROR",
  "event_type": "llm_timeout",
  "message": "LLM request timed out after 12s",
  "session_id": "abc123def456",
  "turn_number": 7,
  "phase": "architecture",
  "extra": {
    "retry_count": 2,
    "elapsed_ms": 12000
  }
}
```

### Console Format for Development

Development logs use human-readable format:

```
[ERROR] llm_timeout | session=abc123de turn=7 | LLM request timed out after 12s
```

### Severity Levels

Standard Python logging levels:

- **DEBUG**: Detailed diagnostic information (disabled in production)
- **INFO**: General informational messages (session start, phase transitions)
- **WARNING**: Warning messages (non-critical issues, fallbacks used)
- **ERROR**: Error messages (recoverable failures, retries triggered)
- **CRITICAL**: Critical failures (unrecoverable errors, session termination)

## Setup

### 1. Configure Logging Mode

Add to your `.env` file:

```bash
# Logging configuration
LOG_LEVEL=INFO              # DEBUG/INFO/WARNING/ERROR/CRITICAL
LOG_FORMAT=console          # "console" for dev, "json" for production
```

For production environments (with GlitchTip/Sentry):

```bash
LOG_LEVEL=INFO
LOG_FORMAT=json
SENTRY_DSN=https://your-key@your-glitchtip-instance.com/project-id
SENTRY_ENABLED=true
```

### 2. Initialize Logging

In your application entry point (e.g., `backend/run_interview.py`):

```python
from backend.structured_logging import configure_logging, LogLevel

# Configure logging on startup
configure_logging(
    level=LogLevel.INFO,
    format_mode="json",  # or "console"
    include_timestamp=True
)
```

### 3. Get a Logger

In your modules:

```python
from backend.structured_logging import get_logger

logger = get_logger(__name__)
```

## Usage

### Basic Logging

```python
from backend.structured_logging import get_logger

logger = get_logger(__name__)

# Simple logs
logger.info("Interview session started")
logger.warning("Constraint conflict detected")
logger.error("LLM request failed")
```

### Logging with Context

```python
# Include session context
logger.info(
    "Phase transition complete",
    event_type="phase_transition",
    session_id=session_id,
    turn_number=5,
    phase="architecture"
)

# Include extra fields
logger.error(
    "LLM timeout",
    event_type="llm_timeout",
    session_id=session_id,
    turn_number=10,
    retry_count=2,
    elapsed_ms=12000
)
```

### Global Session Context

Set session-level context once to include in all logs:

```python
from backend.structured_logging import set_global_context, clear_global_context

# Set global context at session start
set_global_context(session_id="abc123def456")

# All subsequent logs automatically include session_id
logger.info("User turn received")  # Includes session_id automatically

# Clear at session end
clear_global_context()
```

### Async Logging (Prevents Voice Loop Latency)

Use async methods in real-time voice scenarios to prevent I/O blocking:

```python
# Async logging methods
await logger.info_async(
    "Turn completed",
    session_id=session_id,
    turn_number=turn_number,
    latency_ms=450
)

await logger.error_async(
    "STT timeout",
    event_type="stt_timeout",
    session_id=session_id,
    elapsed_seconds=5.2
)
```

Available async methods:
- `debug_async()`
- `info_async()`
- `warning_async()`
- `error_async()`
- `critical_async()`

### Logging Exceptions

```python
try:
    result = await llm_client.generate()
except Exception as e:
    logger.error(
        f"LLM generation failed: {e}",
        event_type="llm_error",
        session_id=session_id,
        exc_info=True  # Includes full stack trace
    )
```

## Sentry/GlitchTip Integration

### Automatic Error Tracking

ERROR and CRITICAL level logs are automatically sent to Sentry/GlitchTip when configured:

```python
# This log is sent to Sentry with full context
logger.error(
    "Failed to parse LLM response",
    event_type="parse_error",
    session_id=session_id,
    turn_number=8,
    phase="deep_dive",
    response_fragment="malformed JSON"
)
```

### Sentry Tags

All ERROR/CRITICAL logs include these Sentry tags for filtering:

- `session_id`: Session identifier
- `turn_number`: Turn number in interview
- `phase`: Interview phase
- `event_type`: Event category

### Sentry Context

Extra fields are added as Sentry context:

```python
logger.error(
    "LLM retry exhausted",
    session_id=session_id,
    retry_count=3,          # → Sentry context
    total_latency_ms=36000  # → Sentry context
)
```

## Best Practices

### 1. Use Appropriate Log Levels

```python
# DEBUG: Detailed diagnostics (disabled in production)
logger.debug("Received transcript chunk", chunk_length=128)

# INFO: Normal operation events
logger.info("Phase advanced to architecture", session_id=session_id)

# WARNING: Recoverable issues
logger.warning("Using fallback TTS provider", reason="primary_unavailable")

# ERROR: Failures requiring attention
logger.error("LLM timeout, retrying", retry_count=2)

# CRITICAL: Severe failures
logger.critical("Session terminated", reason="unrecoverable_error")
```

### 2. Include Event Types

Use descriptive event types for categorization:

```python
logger.info("...", event_type="session_start")
logger.error("...", event_type="llm_timeout")
logger.warning("...", event_type="constraint_conflict")
```

### 3. Use Async Methods in Voice Loop

Always use async methods in real-time voice scenarios:

```python
async def llm_node(user_text: str):
    # Don't block the voice loop with I/O
    await logger.info_async(
        "Processing user turn",
        session_id=session_id,
        turn_number=turn_number
    )

    # ... LLM processing ...
```

### 4. Set Global Context Early

Set session context once at the start:

```python
# In agent initialization
from backend.structured_logging import set_global_context

set_global_context(session_id=session.session_id)

# Now all logs automatically include session_id
logger.info("Session initialized")  # session_id included
```

### 5. Include Relevant Extra Fields

Add fields that help debugging:

```python
logger.error(
    "STT timeout",
    event_type="stt_timeout",
    session_id=session_id,
    timeout_seconds=5.0,
    audio_duration_ms=4800,
    retry_attempt=1
)
```

## Event Type Categories

Recommended event type naming conventions:

### Session Events
- `session_start`
- `session_end`
- `session_error`

### Phase Events
- `phase_transition`
- `phase_timeout`
- `phase_skip`

### LLM Events
- `llm_request`
- `llm_response`
- `llm_timeout`
- `llm_error`
- `llm_retry`

### STT/TTS Events
- `stt_start`
- `stt_complete`
- `stt_timeout`
- `tts_start`
- `tts_complete`
- `tts_error`

### Constraint Events
- `constraint_added`
- `constraint_conflict`
- `constraint_summary`

### Turn Events
- `turn_start`
- `turn_complete`
- `turn_timeout`
- `user_silence`

## Testing

### Running Tests

```bash
# Run structured logging tests
pytest backend/tests/test_structured_logging.py -v

# Run with coverage
pytest backend/tests/test_structured_logging.py --cov=backend.structured_logging -v
```

### Test Coverage

The test suite includes:
- JSON format validation
- Console format validation
- All log levels (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- Session context handling
- Global context management
- Async logging methods
- Extra fields handling
- Exception logging
- Sentry integration (mocked)

## Migration from Standard Logging

### Before (Standard Logging)

```python
import logging

logger = logging.getLogger(__name__)

logger.info(f"Session started: {session_id}")
logger.error(f"LLM timeout on turn {turn_number}")
```

### After (Structured Logging)

```python
from backend.structured_logging import get_logger, set_global_context

logger = get_logger(__name__)

# Set global context once
set_global_context(session_id=session_id)

# Structured logs with event types
logger.info("Session started", event_type="session_start")

await logger.error_async(
    "LLM timeout",
    event_type="llm_timeout",
    turn_number=turn_number
)
```

## Performance Impact

- **Initialization**: Negligible one-time setup cost
- **Synchronous logging**: ~0.1ms overhead for JSON serialization
- **Asynchronous logging**: Non-blocking, runs in executor thread
- **Sentry integration**: Only triggered for ERROR/CRITICAL (rare events)
- **Voice loop latency**: Zero impact when using async methods

## Troubleshooting

### Logs not in JSON format

**Check configuration:**
```python
configure_logging(format_mode="json")  # Not "console"
```

### Session ID missing from logs

**Set global context:**
```python
from backend.structured_logging import set_global_context
set_global_context(session_id=session_id)
```

Or include explicitly:
```python
logger.info("Message", session_id=session_id)
```

### Errors not appearing in Sentry

1. **Verify Sentry is configured**: Check `SENTRY_DSN` in `.env`
2. **Check log level**: Only ERROR/CRITICAL are sent to Sentry
3. **Verify Sentry initialization**: See `SENTRY_INTEGRATION.md`

### Import errors

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Example: Complete Integration

```python
"""Example interview agent with structured logging."""

from backend.structured_logging import get_logger, set_global_context, configure_logging, LogLevel
from backend.config import AgentConfig

# Configure logging on startup
configure_logging(
    level=LogLevel.INFO,
    format_mode="json",
    include_timestamp=True
)

logger = get_logger(__name__)

class InterviewAgent:
    def __init__(self, config: AgentConfig, scenario: str):
        self.session_id = str(uuid.uuid4())

        # Set global context for all logs in this session
        set_global_context(session_id=self.session_id)

        logger.info(
            "Interview agent initialized",
            event_type="session_start",
            scenario=scenario
        )

    async def handle_user_turn(self, user_text: str, turn_number: int):
        # Use async logging in voice loop
        await logger.info_async(
            "Processing user turn",
            event_type="turn_start",
            turn_number=turn_number,
            text_length=len(user_text)
        )

        try:
            response = await self.generate_response(user_text)

            await logger.info_async(
                "Turn completed",
                event_type="turn_complete",
                turn_number=turn_number,
                response_length=len(response)
            )

            return response

        except Exception as e:
            await logger.error_async(
                f"Turn failed: {e}",
                event_type="turn_error",
                turn_number=turn_number,
                exc_info=True
            )
            raise
```

## Next Steps

- Review `SENTRY_INTEGRATION.md` for Sentry/GlitchTip setup
- Review `GLITCHTIP_ALERTS.md` for alerting configuration
- Add structured logging to new modules using `get_logger(__name__)`
- Use async methods in real-time voice scenarios
- Monitor logs in GlitchTip dashboard with JSON query filters
