# InterviewOS Structured Logging

This module provides structured logging with JSON format for Sentry/GlitchTip integration.

## Quick Start

### 1. Configure on Startup

```python
from backend.config import AgentConfig

config = AgentConfig.from_env()
config.init_logging()  # Initializes based on LOG_LEVEL and LOG_FORMAT
```

### 2. Get a Logger

```python
from backend.structured_logging import get_logger

logger = get_logger(__name__)
```

### 3. Log with Context

```python
# Set global session context
from backend.structured_logging import set_global_context

set_global_context(session_id=session_id)

# Log events
logger.info("Session started", event_type="session_start")

# Use async methods in voice loop
await logger.info_async(
    "Turn completed",
    event_type="turn_complete",
    turn_number=5,
    latency_ms=450
)
```

## Features

- **Dual Format**: JSON for production, console for development
- **Required Fields**: timestamp, level, event_type, message
- **Interview Context**: session_id, turn_number, phase
- **Async Logging**: Non-blocking methods for real-time scenarios
- **Sentry Integration**: ERROR/CRITICAL logs sent to Sentry/GlitchTip
- **Zero Voice Loop Latency**: Async methods run in executor

## Files

- `structured_logger.py` - Main implementation
- `example_usage.py` - Usage examples
- `__init__.py` - Public API exports
- `README.md` - This file

## Documentation

See `STRUCTURED_LOGGING.md` in the project root for comprehensive documentation.

## Testing

```bash
pytest backend/tests/test_structured_logging.py -v
```

## Configuration

Environment variables (in `.env`):

```bash
LOG_LEVEL=INFO          # DEBUG/INFO/WARNING/ERROR/CRITICAL
LOG_FORMAT=console      # "console" or "json"
```

## Example Output

### Console Format (Development)

```
[INFO] session_start | session=abc123de | Session initialized
[ERROR] llm_timeout | session=abc123de turn=7 | LLM request timed out
```

### JSON Format (Production)

```json
{
  "timestamp": "2026-03-04T10:15:30.123456",
  "level": "ERROR",
  "event_type": "llm_timeout",
  "message": "LLM request timed out",
  "session_id": "abc123def456",
  "turn_number": 7,
  "phase": "architecture",
  "extra": {
    "retry_count": 2,
    "elapsed_ms": 12000
  }
}
```
