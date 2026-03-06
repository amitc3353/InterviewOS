"""Tests for SessionState memory profiling — get_memory_stats, log_memory_profile, periodic logging."""

import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.models.session import SessionState, InterviewPhase, Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state(session_id: str = "test-mem-123") -> SessionState:
    """Build a minimal SessionState for testing."""
    return SessionState(session_id=session_id)


def _add_messages(state: SessionState, count: int, content: str = "Test message") -> None:
    """Add N user+assistant message pairs to the session."""
    for i in range(count):
        state.conversation_history.append(
            Message(role="user", content=f"{content} {i}")
        )
        state.conversation_history.append(
            Message(role="assistant", content=f"Response {i}")
        )


# ---------------------------------------------------------------------------
# Tests — get_memory_stats
# ---------------------------------------------------------------------------

def test_get_memory_stats_empty_session():
    """get_memory_stats returns zeroes for empty conversation history."""
    state = _make_session_state()
    stats = state.get_memory_stats()

    assert stats["message_count"] == 0
    assert stats["total_chars"] == 0
    assert stats["estimated_bytes"] == 0
    assert stats["avg_message_chars"] == 0


def test_get_memory_stats_with_messages():
    """get_memory_stats returns correct counts for populated history."""
    state = _make_session_state()
    state.conversation_history.append(Message(role="user", content="Hello"))
    state.conversation_history.append(Message(role="assistant", content="Hi there"))

    stats = state.get_memory_stats()

    assert stats["message_count"] == 2
    assert stats["total_chars"] == len("Hello") + len("Hi there")
    assert stats["estimated_bytes"] > 0
    assert stats["avg_message_chars"] == (len("Hello") + len("Hi there")) / 2


def test_get_memory_stats_estimated_bytes_uses_sys_getsizeof():
    """estimated_bytes uses sys.getsizeof for accurate Python object size."""
    state = _make_session_state()
    content = "A" * 1000
    state.conversation_history.append(Message(role="user", content=content))

    stats = state.get_memory_stats()

    expected_bytes = sys.getsizeof(content)
    assert stats["estimated_bytes"] == expected_bytes


def test_get_memory_stats_avg_chars_rounded():
    """avg_message_chars is rounded to 1 decimal place."""
    state = _make_session_state()
    state.conversation_history.append(Message(role="user", content="abc"))
    state.conversation_history.append(Message(role="assistant", content="de"))

    stats = state.get_memory_stats()

    # (3 + 2) / 2 = 2.5
    assert stats["avg_message_chars"] == 2.5


def test_get_memory_stats_large_session():
    """get_memory_stats handles 100+ messages correctly."""
    state = _make_session_state()
    _add_messages(state, 50)  # 100 messages total

    stats = state.get_memory_stats()

    assert stats["message_count"] == 100
    assert stats["total_chars"] > 0
    assert stats["estimated_bytes"] > 0
    assert stats["avg_message_chars"] > 0


# ---------------------------------------------------------------------------
# Tests — log_memory_profile
# ---------------------------------------------------------------------------

def test_log_memory_profile_debug_level_under_50mb():
    """log_memory_profile logs at debug level when under 50MB threshold."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.debug = MagicMock()
        mock_logger.warning = MagicMock()

        state = _make_session_state(session_id="session-mem-1")
        state.conversation_history.append(Message(role="user", content="Hello"))

        state.log_memory_profile()

        assert mock_logger.debug.called
        assert not mock_logger.warning.called

        call_args = mock_logger.debug.call_args
        assert call_args.kwargs['event_type'] == 'memory_profile'
        assert call_args.kwargs['session_id'] == "session-mem-1"
        assert 'message_count' in call_args.kwargs
        assert 'total_chars' in call_args.kwargs
        assert 'estimated_bytes' in call_args.kwargs
        assert 'estimated_mb' in call_args.kwargs
        assert 'avg_message_chars' in call_args.kwargs


def test_log_memory_profile_warning_level_over_50mb():
    """log_memory_profile logs at warning level when over 50MB threshold."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.debug = MagicMock()
        mock_logger.warning = MagicMock()

        state = _make_session_state(session_id="session-mem-2")

        # Create huge messages to exceed 50MB threshold
        # sys.getsizeof("A" * 1_000_000) ≈ 1MB, so we need ~55 of them
        huge_content = "A" * 1_000_000
        for _ in range(55):
            state.conversation_history.append(Message(role="user", content=huge_content))

        state.log_memory_profile()

        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args
        assert call_args.kwargs['event_type'] == 'memory_profile'
        assert call_args.kwargs['level'] == 'warning'
        assert call_args.kwargs['estimated_mb'] > 50


def test_log_memory_profile_includes_session_context():
    """log_memory_profile includes session_id and turn_number."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        state = _make_session_state(session_id="session-ctx")
        state.total_turn_count = 15
        state.conversation_history.append(Message(role="user", content="test"))

        state.log_memory_profile()

        call_args = mock_logger.debug.call_args
        assert call_args.kwargs['session_id'] == "session-ctx"
        assert call_args.kwargs['turn_number'] == 15


# ---------------------------------------------------------------------------
# Tests — Periodic memory logging in add_message
# ---------------------------------------------------------------------------

def test_add_message_triggers_memory_log_every_10_messages():
    """add_message triggers log_memory_profile every 10 messages."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        state = _make_session_state()

        # Add 10 messages (mix of user and assistant)
        for i in range(5):
            state.add_message("user", f"Message {i}")
            state.add_message("assistant", f"Response {i}")

        # After 10 messages, log_memory_profile should have been called
        # Check for memory_profile event_type in debug calls
        memory_profile_calls = [
            call for call in mock_logger.debug.call_args_list
            if call.kwargs.get('event_type') == 'memory_profile'
        ]
        assert len(memory_profile_calls) == 1


def test_add_message_does_not_trigger_at_non_10_boundary():
    """add_message does NOT trigger log_memory_profile at 5 messages."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        state = _make_session_state()

        # Add 5 messages only
        for i in range(5):
            state.add_message("user", f"Message {i}")

        # Check: no memory_profile events
        memory_profile_calls = [
            call for call in mock_logger.debug.call_args_list
            if call.kwargs.get('event_type') == 'memory_profile'
        ]
        assert len(memory_profile_calls) == 0


def test_add_message_triggers_memory_log_at_20_messages():
    """add_message triggers log_memory_profile at 20 messages (second boundary)."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        state = _make_session_state()

        # Add 20 messages
        for i in range(10):
            state.add_message("user", f"Message {i}")
            state.add_message("assistant", f"Response {i}")

        # Should have triggered at 10 and 20
        memory_profile_calls = [
            call for call in mock_logger.debug.call_args_list
            if call.kwargs.get('event_type') == 'memory_profile'
        ]
        assert len(memory_profile_calls) == 2


# ---------------------------------------------------------------------------
# Tests — 45+ minute session simulation
# ---------------------------------------------------------------------------

def test_memory_stats_simulated_45_min_session():
    """Simulate a 45-minute session and verify memory stays reasonable.

    Assumes ~2 turns per minute (user + assistant) = ~90 messages per 45 min.
    Average message ~200 chars. Total should be well under 100MB.
    """
    state = _make_session_state(session_id="session-45min")
    state.session_start_time = datetime.now() - timedelta(minutes=45)

    # Simulate 90 messages (45 min * 2 messages/min)
    for i in range(45):
        user_msg = f"Turn {i}: I would use a distributed hash table with consistent hashing for partition management, and add read replicas for horizontal scaling of read queries."
        assistant_msg = f"Turn {i}: What happens when a node fails and the hash ring needs rebalancing?"
        state.conversation_history.append(Message(role="user", content=user_msg))
        state.conversation_history.append(Message(role="assistant", content=assistant_msg))

    stats = state.get_memory_stats()

    # 90 messages
    assert stats["message_count"] == 90

    # Memory should be well under 100MB (typically < 1MB for text conversations)
    estimated_mb = stats["estimated_bytes"] / (1024 * 1024)
    assert estimated_mb < 100, f"Memory usage {estimated_mb:.2f}MB exceeds 100MB limit"

    # Sanity check: should be < 10MB for 90 messages of ~150 chars each
    assert estimated_mb < 10, f"Memory usage {estimated_mb:.2f}MB unexpectedly high"
