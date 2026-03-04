# Sentry Integration Guide

## Overview

InterviewOS now integrates with Sentry SDK (compatible with GlitchTip) for comprehensive error tracking and monitoring. All unhandled exceptions are automatically captured with rich interview context including session ID, turn number, phase, and session state.

## Features

- **Automatic exception capture**: All unhandled exceptions are sent to Sentry/GlitchTip
- **Rich context tagging**: Every error includes:
  - `session_id`: Unique interview session identifier
  - `turn_number`: Current turn in the interview
  - `phase`: Current interview phase (intro, scope, architecture, etc.)
  - `phase_turn_count`: Turn count within current phase
- **Session context**: Additional metadata including elapsed time, locked constraints count, etc.
- **Optional**: Can be disabled via environment variable

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs `sentry-sdk>=2.0.0` along with other dependencies.

### 2. Configure Environment

Add your Sentry/GlitchTip DSN to `.env`:

```bash
# Error tracking (optional - GlitchTip/Sentry DSN)
SENTRY_DSN=https://your-key@your-glitchtip-instance.com/project-id
SENTRY_ENVIRONMENT=production  # Optional, defaults to 'production'
SENTRY_ENABLED=true            # Optional, defaults to 'true'
```

To get your DSN:
- **GlitchTip**: Go to Project Settings → Client Keys (DSN)
- **Sentry**: Go to Settings → Projects → [Your Project] → Client Keys (DSN)

### 3. Run the Application

Sentry will be initialized automatically when you start the interview agent:

```bash
python backend/run_interview.py
```

You'll see a log message confirming Sentry initialization:
```
INFO - Sentry initialized for environment: production
```

## Testing the Integration

### Automated Tests

Run the test suite to verify Sentry integration:

```bash
pytest backend/tests/test_sentry_integration.py -v
```

Tests cover:
- Configuration loading from environment
- Sentry initialization with/without DSN
- Context setting with session state
- Turn context updates
- Exception capture with full context
- Error handling when Sentry SDK fails

### Manual End-to-End Test

Run the test script to send a test exception to your Sentry/GlitchTip dashboard:

```bash
python backend/test_sentry.py
```

This will:
1. Initialize Sentry with your configured DSN
2. Create a test session state
3. Set interview context
4. Raise and capture a test exception
5. Send it to your Sentry/GlitchTip dashboard

**Verify in Dashboard:**
- Look for event: `ValueError: Test exception from Sentry integration test`
- Check tags: `session_id`, `turn_number`, `phase`, `phase_turn_count`
- Check context sections: `interview_session`, `extra`

## Implementation Details

### Files Modified

- `requirements.txt`: Added `sentry-sdk>=2.0.0`
- `.env.example`: Added Sentry configuration variables
- `backend/config.py`: Added Sentry config fields and `init_sentry()` method
- `backend/run_interview.py`: Call `config.init_sentry()` on startup
- `backend/agents/interview_agent.py`:
  - Import sentry_context utilities
  - Set context on session start
  - Update context after each user turn

### Files Created

- `backend/interview/sentry_context.py`: Utility functions for managing Sentry context
  - `set_interview_context()`: Initialize context with session ID and state
  - `update_turn_context()`: Update context after each turn
  - `capture_exception_with_context()`: Manually capture exceptions with context
- `backend/tests/test_sentry_integration.py`: Comprehensive test suite (13 tests)
- `backend/test_sentry.py`: Manual end-to-end test script

### Context Tagging

Every error captured by Sentry includes:

**Tags:**
- `session_id`: Unique session identifier for grouping errors by session
- `turn_number`: Interview turn number when error occurred
- `phase`: Interview phase (intro, scope, architecture, deep_dive, failure, tradeoffs, wrap)
- `phase_turn_count`: Turn count within the current phase

**Context (interview_session):**
- `session_id`: Session identifier
- `total_turns`: Total number of turns in session
- `phase`: Current interview phase
- `phase_turns`: Turns in current phase
- `elapsed_seconds`: Total session duration
- `phase_elapsed_seconds`: Current phase duration
- `locked_constraints_count`: Number of locked constraints

### Error Handling

The Sentry integration is designed to **never** crash the application:

- If Sentry DSN is not configured, initialization is skipped silently
- If Sentry initialization fails, error is logged and app continues
- If context setting fails, warning is logged and app continues
- If exception capture fails, warning is logged and app continues

## Disabling Sentry

To disable Sentry entirely, set in `.env`:

```bash
SENTRY_ENABLED=false
```

Or remove the `SENTRY_DSN` environment variable.

## Performance Impact

- **Initialization**: One-time overhead on application startup (~10ms)
- **Context setting**: Negligible (<1ms per turn)
- **Exception capture**: Only occurs on errors, does not affect normal operation
- **Sampling**: Performance monitoring set to 10% of transactions to minimize overhead

## Troubleshooting

### Sentry not initializing

**Check logs for:**
```
INFO - Sentry DSN not configured, skipping error tracking
```

**Solution:** Add `SENTRY_DSN` to your `.env` file

### Errors not appearing in dashboard

1. **Verify DSN is correct**: Run `python backend/test_sentry.py`
2. **Check Sentry is enabled**: `SENTRY_ENABLED=true` in `.env`
3. **Check network**: Ensure your server can reach Sentry/GlitchTip
4. **Check logs**: Look for "Failed to initialize Sentry" or "Failed to capture exception"

### Import errors

**Error:** `No module named 'sentry_sdk'`

**Solution:** Install dependencies: `pip install -r requirements.txt`

## Next Steps

- Monitor your GlitchTip/Sentry dashboard for errors
- **[Set up alerts for critical errors](./GLITCHTIP_ALERTS.md)** ← See comprehensive alerting guide
- Use session_id tag to filter errors by session
- Use phase tag to identify which interview phase has most errors
- Configure issue assignment and notification rules

## GlitchTip Alerting

For detailed instructions on setting up GlitchTip alert rules with Discord webhook integration, see:

**[GLITCHTIP_ALERTS.md](./GLITCHTIP_ALERTS.md)**

This guide covers:
- Creating Discord webhooks for alerts
- Configuring GlitchTip alert rules with error rate thresholds
- Setting up webhook proxy for formatted Discord notifications
- Testing webhook delivery
- Troubleshooting common issues
