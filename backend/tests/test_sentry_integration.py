"""Tests for Sentry SDK integration — config, context, and exception capture."""

import logging
from unittest.mock import MagicMock, patch, call

import pytest

from backend.config import AgentConfig
from backend.interview.sentry_context import (
    set_interview_context,
    update_turn_context,
    capture_exception_with_context,
)
from backend.models.session import SessionState, InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state() -> SessionState:
    """Build a minimal SessionState for testing."""
    state = SessionState()
    state.total_turn_count = 5
    state.phase_turn_count = 2
    state.phase = InterviewPhase.ARCHITECTURE
    state.add_locked_constraint("database", "PostgreSQL")
    return state


# ---------------------------------------------------------------------------
# Tests: AgentConfig.init_sentry()
# ---------------------------------------------------------------------------

@patch('backend.config.sentry_sdk')
def test_init_sentry_with_valid_dsn(mock_sentry):
    """init_sentry initializes Sentry when DSN is provided."""
    config = AgentConfig(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test_key",
        livekit_api_secret="test_secret",
        deepgram_api_key="test_deepgram",
        anthropic_api_key="test_anthropic",
        openai_api_key="test_openai",
        cartesia_api_key="test_cartesia",
        sentry_dsn="https://test@sentry.io/123",
        sentry_environment="development",
        sentry_enabled=True,
    )

    result = config.init_sentry()

    assert result is True
    mock_sentry.init.assert_called_once_with(
        dsn="https://test@sentry.io/123",
        environment="development",
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )


@patch('backend.config.sentry_sdk')
def test_init_sentry_without_dsn_skips_initialization(mock_sentry):
    """init_sentry skips initialization when DSN is not provided."""
    config = AgentConfig(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test_key",
        livekit_api_secret="test_secret",
        deepgram_api_key="test_deepgram",
        anthropic_api_key="test_anthropic",
        openai_api_key="test_openai",
        cartesia_api_key="test_cartesia",
        sentry_dsn=None,  # No DSN
        sentry_enabled=True,
    )

    result = config.init_sentry()

    assert result is False
    mock_sentry.init.assert_not_called()


@patch('backend.config.sentry_sdk')
def test_init_sentry_when_disabled_skips_initialization(mock_sentry):
    """init_sentry skips initialization when sentry_enabled is False."""
    config = AgentConfig(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test_key",
        livekit_api_secret="test_secret",
        deepgram_api_key="test_deepgram",
        anthropic_api_key="test_anthropic",
        openai_api_key="test_openai",
        cartesia_api_key="test_cartesia",
        sentry_dsn="https://test@sentry.io/123",
        sentry_enabled=False,  # Disabled
    )

    result = config.init_sentry()

    assert result is False
    mock_sentry.init.assert_not_called()


@patch('backend.config.sentry_sdk')
def test_init_sentry_handles_initialization_error(mock_sentry):
    """init_sentry handles Sentry initialization errors gracefully."""
    mock_sentry.init.side_effect = Exception("Sentry init failed")

    config = AgentConfig(
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test_key",
        livekit_api_secret="test_secret",
        deepgram_api_key="test_deepgram",
        anthropic_api_key="test_anthropic",
        openai_api_key="test_openai",
        cartesia_api_key="test_cartesia",
        sentry_dsn="https://test@sentry.io/123",
        sentry_enabled=True,
    )

    result = config.init_sentry()

    assert result is False  # Should return False on error
    mock_sentry.init.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: set_interview_context()
# ---------------------------------------------------------------------------

@patch('backend.interview.sentry_context.sentry_sdk')
def test_set_interview_context_with_state(mock_sentry):
    """set_interview_context sets all tags and context with state."""
    state = _make_session_state()
    session_id = "test-session-123"

    set_interview_context(session_id, state)

    # Check user context
    mock_sentry.set_user.assert_called_once_with({"id": session_id})

    # Check tags
    expected_tag_calls = [
        call("session_id", session_id),
        call("turn_number", "5"),
        call("phase", "architecture"),
        call("phase_turn_count", "2"),
    ]
    mock_sentry.set_tag.assert_has_calls(expected_tag_calls, any_order=True)

    # Check context
    mock_sentry.set_context.assert_called_once()
    context_call = mock_sentry.set_context.call_args
    assert context_call[0][0] == "interview_session"
    context_data = context_call[0][1]
    assert context_data["session_id"] == session_id
    assert context_data["total_turns"] == 5
    assert context_data["phase"] == "architecture"
    assert context_data["phase_turns"] == 2
    assert context_data["locked_constraints_count"] == 1


@patch('backend.interview.sentry_context.sentry_sdk')
def test_set_interview_context_without_state(mock_sentry):
    """set_interview_context works without state (session_id only)."""
    session_id = "test-session-456"

    set_interview_context(session_id, state=None)

    # Check user context
    mock_sentry.set_user.assert_called_once_with({"id": session_id})

    # Check tag (only session_id)
    mock_sentry.set_tag.assert_called_once_with("session_id", session_id)

    # Context should not be called (no state)
    mock_sentry.set_context.assert_not_called()


@patch('backend.interview.sentry_context.sentry_sdk')
def test_set_interview_context_handles_errors_gracefully(mock_sentry, caplog):
    """set_interview_context handles Sentry SDK errors without crashing."""
    mock_sentry.set_user.side_effect = Exception("Sentry error")

    with caplog.at_level(logging.WARNING):
        set_interview_context("test-session", None)

    # Should log warning
    assert len(caplog.records) == 1
    assert "Failed to set Sentry context" in caplog.records[0].message


# ---------------------------------------------------------------------------
# Tests: update_turn_context()
# ---------------------------------------------------------------------------

@patch('backend.interview.sentry_context.sentry_sdk')
def test_update_turn_context_updates_tags_and_context(mock_sentry):
    """update_turn_context updates turn-specific tags and context."""
    state = _make_session_state()

    update_turn_context(state)

    # Check tags
    expected_tag_calls = [
        call("turn_number", "5"),
        call("phase_turn_count", "2"),
    ]
    mock_sentry.set_tag.assert_has_calls(expected_tag_calls, any_order=True)

    # Check context
    mock_sentry.set_context.assert_called_once()
    context_call = mock_sentry.set_context.call_args
    assert context_call[0][0] == "interview_session"
    context_data = context_call[0][1]
    assert context_data["total_turns"] == 5
    assert context_data["phase_turns"] == 2


@patch('backend.interview.sentry_context.sentry_sdk')
def test_update_turn_context_handles_errors_gracefully(mock_sentry, caplog):
    """update_turn_context handles Sentry SDK errors without crashing."""
    mock_sentry.set_tag.side_effect = Exception("Sentry error")
    state = _make_session_state()

    with caplog.at_level(logging.WARNING):
        update_turn_context(state)

    # Should log warning
    assert len(caplog.records) == 1
    assert "Failed to update Sentry turn context" in caplog.records[0].message


# ---------------------------------------------------------------------------
# Tests: capture_exception_with_context()
# ---------------------------------------------------------------------------

@patch('backend.interview.sentry_context.sentry_sdk')
def test_capture_exception_with_context(mock_sentry):
    """capture_exception_with_context captures exception with full context."""
    state = _make_session_state()
    session_id = "test-session-789"
    test_exception = ValueError("Test error")

    capture_exception_with_context(
        exception=test_exception,
        session_id=session_id,
        state=state,
    )

    # Should set user context
    mock_sentry.set_user.assert_called()

    # Should capture the exception
    mock_sentry.capture_exception.assert_called_once_with(test_exception)


@patch('backend.interview.sentry_context.sentry_sdk')
def test_capture_exception_with_extra_context(mock_sentry):
    """capture_exception_with_context includes extra context."""
    state = _make_session_state()
    session_id = "test-session-abc"
    test_exception = RuntimeError("Test runtime error")
    extra_context = {"error_source": "llm_timeout", "retry_count": 3}

    capture_exception_with_context(
        exception=test_exception,
        session_id=session_id,
        state=state,
        extra_context=extra_context,
    )

    # Should set extra context
    context_calls = mock_sentry.set_context.call_args_list
    extra_context_call = [c for c in context_calls if c[0][0] == "extra"]
    assert len(extra_context_call) > 0
    assert extra_context_call[0][0][1] == extra_context

    # Should capture exception
    mock_sentry.capture_exception.assert_called_once_with(test_exception)


@patch('backend.interview.sentry_context.sentry_sdk')
def test_capture_exception_handles_errors_gracefully(mock_sentry, caplog):
    """capture_exception_with_context handles Sentry errors without crashing."""
    mock_sentry.capture_exception.side_effect = Exception("Sentry capture failed")
    test_exception = ValueError("Original error")

    with caplog.at_level(logging.WARNING):
        capture_exception_with_context(
            exception=test_exception,
            session_id="test-session",
            state=None,
        )

    # Should log warning
    assert len(caplog.records) == 1
    assert "Failed to capture exception in Sentry" in caplog.records[0].message


# ---------------------------------------------------------------------------
# Tests: Config from_env() with Sentry
# ---------------------------------------------------------------------------

@patch.dict('os.environ', {
    'LIVEKIT_URL': 'wss://test.livekit.cloud',
    'LIVEKIT_API_KEY': 'test_key',
    'LIVEKIT_API_SECRET': 'test_secret',
    'DEEPGRAM_API_KEY': 'test_deepgram',
    'ANTHROPIC_API_KEY': 'test_anthropic',
    'OPENAI_API_KEY': 'test_openai',
    'CARTESIA_API_KEY': 'test_cartesia',
    'SENTRY_DSN': 'https://test@sentry.io/123',
    'SENTRY_ENVIRONMENT': 'staging',
    'SENTRY_ENABLED': 'true',
})
def test_config_from_env_loads_sentry_settings():
    """from_env() loads Sentry configuration from environment."""
    config = AgentConfig.from_env()

    assert config.sentry_dsn == 'https://test@sentry.io/123'
    assert config.sentry_environment == 'staging'
    assert config.sentry_enabled is True


@patch.dict('os.environ', {
    'LIVEKIT_URL': 'wss://test.livekit.cloud',
    'LIVEKIT_API_KEY': 'test_key',
    'LIVEKIT_API_SECRET': 'test_secret',
    'DEEPGRAM_API_KEY': 'test_deepgram',
    'ANTHROPIC_API_KEY': 'test_anthropic',
    'OPENAI_API_KEY': 'test_openai',
    'CARTESIA_API_KEY': 'test_cartesia',
    'SENTRY_ENABLED': 'false',
})
def test_config_from_env_respects_sentry_disabled():
    """from_env() respects SENTRY_ENABLED=false."""
    config = AgentConfig.from_env()

    assert config.sentry_enabled is False


@patch.dict('os.environ', {
    'LIVEKIT_URL': 'wss://test.livekit.cloud',
    'LIVEKIT_API_KEY': 'test_key',
    'LIVEKIT_API_SECRET': 'test_secret',
    'DEEPGRAM_API_KEY': 'test_deepgram',
    'ANTHROPIC_API_KEY': 'test_anthropic',
    'OPENAI_API_KEY': 'test_openai',
    'CARTESIA_API_KEY': 'test_cartesia',
}, clear=True)
def test_config_from_env_defaults_when_sentry_not_set():
    """from_env() uses defaults when Sentry env vars are not set."""
    config = AgentConfig.from_env()

    assert config.sentry_dsn is None
    assert config.sentry_environment == 'production'
    assert config.sentry_enabled is True  # Enabled by default
