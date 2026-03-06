"""Tests for SessionState and InterviewSession — constraint overwrite, elapsed time, initialization."""
import logging
from datetime import datetime, timedelta
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


# ---------------------------------------------------------------------------
# Tests: SessionState initialization and defaults
# ---------------------------------------------------------------------------

def test_session_state_default_initialization():
    """SessionState initializes with correct defaults."""
    state = SessionState()

    assert state.session_id == ""
    assert state.phase == InterviewPhase.INTRO
    assert state.locked_constraints == {}
    assert state.conversation_history == []
    assert state.phase_turn_count == 0
    assert state.total_turn_count == 0
    assert state.last_constraint_summary_turn == 0
    assert state.consecutive_silence_count == 0


def test_session_state_custom_initialization():
    """SessionState can be initialized with custom values."""
    state = SessionState(
        session_id="custom-id",
        phase=InterviewPhase.ARCHITECTURE,
    )

    assert state.session_id == "custom-id"
    assert state.phase == InterviewPhase.ARCHITECTURE


# ---------------------------------------------------------------------------
# Tests: Elapsed time calculations
# ---------------------------------------------------------------------------

def test_elapsed_seconds():
    """elapsed_seconds returns total session time."""
    state = SessionState()
    state.session_start_time = datetime.now() - timedelta(seconds=120)

    elapsed = state.elapsed_seconds()

    # Allow 1 second tolerance for test execution time
    assert 119 <= elapsed <= 122


def test_phase_elapsed_seconds():
    """phase_elapsed_seconds returns time in current phase."""
    state = SessionState()
    state.phase_start_time = datetime.now() - timedelta(seconds=60)

    elapsed = state.phase_elapsed_seconds()

    # Allow 1 second tolerance for test execution time
    assert 59 <= elapsed <= 62


def test_phase_elapsed_resets_on_advance():
    """phase_elapsed_seconds resets when advancing to a new phase."""
    state = SessionState()
    state.phase_start_time = datetime.now() - timedelta(seconds=300)

    # Verify significant time has passed
    assert state.phase_elapsed_seconds() >= 299

    # Advance phase
    state.advance_phase(InterviewPhase.SCOPE)

    # Phase start time should be reset to ~now
    assert state.phase_elapsed_seconds() < 2


# ---------------------------------------------------------------------------
# Tests: Message dataclass
# ---------------------------------------------------------------------------

def test_message_creation():
    """Message dataclass stores role and content."""
    msg = Message(role="user", content="Hello world")

    assert msg.role == "user"
    assert msg.content == "Hello world"
    assert isinstance(msg.timestamp, datetime)


def test_message_timestamp_auto_generated():
    """Message timestamp is auto-generated if not provided."""
    before = datetime.now()
    msg = Message(role="assistant", content="Hi")
    after = datetime.now()

    assert before <= msg.timestamp <= after


# ---------------------------------------------------------------------------
# Tests: InterviewSession
# ---------------------------------------------------------------------------

def test_interview_session_post_init_propagates_session_id():
    """InterviewSession.__post_init__ propagates session_id to state."""
    session = InterviewSession(session_id="abc-123", scenario="Design X")

    assert session.state.session_id == "abc-123"


def test_interview_session_post_init_skips_if_state_has_id():
    """If state already has a session_id, post_init doesn't overwrite it."""
    state = SessionState(session_id="existing-id")
    session = InterviewSession(session_id="new-id", scenario="Design X", state=state)

    assert session.state.session_id == "existing-id"


def test_interview_session_to_dict_empty():
    """to_dict works on a fresh session with no messages or constraints."""
    session = InterviewSession(session_id="empty-123", scenario="Test")

    data = session.to_dict()

    assert data["session_id"] == "empty-123"
    assert data["scenario"] == "Test"
    assert data["phase"] == "intro"
    assert data["locked_constraints"] == {}
    assert data["conversation_history"] == []
    assert data["total_turns"] == 0
    assert data["scorecard"] is None


def test_interview_session_to_dict_includes_timing():
    """to_dict includes session timing information."""
    session = InterviewSession(session_id="timing-test", scenario="Test")

    data = session.to_dict()

    assert "session_start_time" in data
    assert "elapsed_seconds" in data
    assert isinstance(data["elapsed_seconds"], float)


# ---------------------------------------------------------------------------
# Tests: get_recent_history edge cases
# ---------------------------------------------------------------------------

def test_get_recent_history_fewer_messages_than_window():
    """get_recent_history returns all messages when fewer than window_size."""
    state = _make_session_state()
    state.add_message("user", "Hello")
    state.add_message("assistant", "Hi")

    recent = state.get_recent_history(window_size=10)
    assert len(recent) == 2


def test_get_recent_history_empty():
    """get_recent_history returns empty list when no messages exist."""
    state = _make_session_state()

    recent = state.get_recent_history()
    assert len(recent) == 0


# ---------------------------------------------------------------------------
# Tests: Phase order
# ---------------------------------------------------------------------------

def test_phase_order_all_phases():
    """PHASE_ORDER contains all 7 phases in correct sequence."""
    assert len(PHASE_ORDER) == 7
    assert PHASE_ORDER[0] == InterviewPhase.INTRO
    assert PHASE_ORDER[1] == InterviewPhase.SCOPE
    assert PHASE_ORDER[2] == InterviewPhase.ARCHITECTURE
    assert PHASE_ORDER[3] == InterviewPhase.DEEP_DIVE
    assert PHASE_ORDER[4] == InterviewPhase.FAILURE
    assert PHASE_ORDER[5] == InterviewPhase.TRADEOFFS
    assert PHASE_ORDER[6] == InterviewPhase.WRAP


def test_advance_phase_skip_forward():
    """advance_phase allows skipping phases (e.g., INTRO → ARCHITECTURE)."""
    state = _make_session_state()

    success = state.advance_phase(InterviewPhase.ARCHITECTURE)
    assert success
    assert state.phase == InterviewPhase.ARCHITECTURE


def test_advance_phase_full_traversal():
    """advance_phase can traverse all phases from INTRO to WRAP."""
    state = _make_session_state()

    for phase in PHASE_ORDER[1:]:  # Skip INTRO (already there)
        success = state.advance_phase(phase)
        assert success
        assert state.phase == phase

    # Should now be at WRAP
    assert state.phase == InterviewPhase.WRAP
