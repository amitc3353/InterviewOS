"""Tests for SessionState and InterviewSession — constraint overwrite protection."""
import logging
from datetime import datetime
from unittest.mock import patch

import pytest

from backend.models.session import (
    InterviewPhase,
    InterviewSession,
    Message,
    SessionState,
    PHASE_ORDER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state() -> SessionState:
    """Build a minimal SessionState for testing."""
    return SessionState()


def _make_interview_session() -> InterviewSession:
    """Build a minimal InterviewSession for testing."""
    return InterviewSession(
        session_id="test-session-123",
        scenario="Design a URL shortener"
    )


# ---------------------------------------------------------------------------
# Tests: add_locked_constraint
# ---------------------------------------------------------------------------

def test_add_locked_constraint_first_constraint_stored():
    """First constraint is stored correctly."""
    state = _make_session_state()

    state.add_locked_constraint("database", "PostgreSQL")

    assert "database" in state.locked_constraints
    assert state.locked_constraints["database"] == "PostgreSQL"


def test_add_locked_constraint_duplicate_key_keeps_original(caplog):
    """Duplicate key logs warning and keeps original value."""
    state = _make_session_state()

    # Add first constraint
    state.add_locked_constraint("database", "PostgreSQL")

    # Try to add duplicate with different value
    with caplog.at_level(logging.WARNING):
        state.add_locked_constraint("database", "MySQL")

    # Should keep original value
    assert state.locked_constraints["database"] == "PostgreSQL"

    # Should log warning with both values
    assert len(caplog.records) == 1
    warning_msg = caplog.records[0].message
    assert "database" in warning_msg
    assert "PostgreSQL" in warning_msg
    assert "MySQL" in warning_msg
    assert "Keeping original" in warning_msg


def test_add_locked_constraint_different_keys_both_stored():
    """Different keys are both stored correctly."""
    state = _make_session_state()

    state.add_locked_constraint("database", "PostgreSQL")
    state.add_locked_constraint("cache", "Redis")

    assert len(state.locked_constraints) == 2
    assert state.locked_constraints["database"] == "PostgreSQL"
    assert state.locked_constraints["cache"] == "Redis"


def test_add_locked_constraint_multiple_duplicates_all_ignored(caplog):
    """Multiple attempts to overwrite the same key all get ignored."""
    state = _make_session_state()

    state.add_locked_constraint("database", "PostgreSQL")

    with caplog.at_level(logging.WARNING):
        state.add_locked_constraint("database", "MySQL")
        state.add_locked_constraint("database", "MongoDB")

    # Should still have original value
    assert state.locked_constraints["database"] == "PostgreSQL"

    # Should have logged two warnings
    assert len(caplog.records) == 2


def test_lock_constraint_backward_compatibility():
    """Legacy lock_constraint method still works and uses new protection."""
    state = _make_session_state()

    # Use legacy method
    state.lock_constraint("database", "PostgreSQL")

    assert state.locked_constraints["database"] == "PostgreSQL"


def test_lock_constraint_backward_compatibility_with_duplicate(caplog):
    """Legacy lock_constraint method also prevents overwrites."""
    state = _make_session_state()

    state.lock_constraint("database", "PostgreSQL")

    with caplog.at_level(logging.WARNING):
        state.lock_constraint("database", "MySQL")

    # Should keep original value
    assert state.locked_constraints["database"] == "PostgreSQL"

    # Should log warning
    assert len(caplog.records) == 1


# ---------------------------------------------------------------------------
# Tests: SessionState other methods
# ---------------------------------------------------------------------------

def test_add_message_increments_turn_count():
    """add_message increments turn counts correctly."""
    state = _make_session_state()

    assert state.total_turn_count == 0
    assert state.phase_turn_count == 0

    state.add_message("user", "Hello")
    assert state.total_turn_count == 1
    assert state.phase_turn_count == 1

    state.add_message("assistant", "Hi there")
    assert state.total_turn_count == 1  # Only user messages increment
    assert state.phase_turn_count == 1

    state.add_message("user", "How are you?")
    assert state.total_turn_count == 2
    assert state.phase_turn_count == 2


def test_get_recent_history():
    """get_recent_history returns last N messages."""
    state = _make_session_state()

    for i in range(10):
        state.add_message("user", f"Message {i}")

    recent = state.get_recent_history(window_size=3)
    assert len(recent) == 3
    assert recent[0].content == "Message 7"
    assert recent[2].content == "Message 9"


def test_advance_phase_forward_succeeds():
    """advance_phase allows forward movement."""
    state = _make_session_state()

    assert state.phase == InterviewPhase.INTRO

    success = state.advance_phase(InterviewPhase.SCOPE)
    assert success
    assert state.phase == InterviewPhase.SCOPE
    assert state.phase_turn_count == 0  # Reset on phase change


def test_advance_phase_backward_blocked():
    """advance_phase blocks backward movement."""
    state = _make_session_state()
    state.phase = InterviewPhase.ARCHITECTURE

    success = state.advance_phase(InterviewPhase.SCOPE)
    assert not success
    assert state.phase == InterviewPhase.ARCHITECTURE  # Unchanged


def test_advance_phase_same_phase_blocked():
    """advance_phase blocks staying in same phase."""
    state = _make_session_state()

    success = state.advance_phase(InterviewPhase.INTRO)
    assert not success
    assert state.phase == InterviewPhase.INTRO


def test_has_constraint_category():
    """has_constraint_category checks prefix correctly."""
    state = _make_session_state()

    state.add_locked_constraint("database:primary", "PostgreSQL")
    state.add_locked_constraint("database:cache", "Redis")
    state.add_locked_constraint("qps", "10000")

    assert state.has_constraint_category("database")
    assert state.has_constraint_category("qps")
    assert not state.has_constraint_category("storage")


# ---------------------------------------------------------------------------
# Tests: InterviewSession
# ---------------------------------------------------------------------------

def test_interview_session_to_dict():
    """to_dict serializes session correctly."""
    session = _make_interview_session()
    session.state.add_message("user", "Hello")
    session.state.add_locked_constraint("database", "PostgreSQL")

    data = session.to_dict()

    assert data["session_id"] == "test-session-123"
    assert data["scenario"] == "Design a URL shortener"
    assert data["phase"] == "intro"
    assert data["locked_constraints"]["database"] == "PostgreSQL"
    assert len(data["conversation_history"]) == 1
    assert data["total_turns"] == 1
