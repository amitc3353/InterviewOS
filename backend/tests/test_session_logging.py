"""Tests for structured logging in session.py — constraint additions and phase transitions."""

from unittest.mock import MagicMock, patch

import pytest

from backend.models.session import SessionState, InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state(session_id: str = "test-session-123", turn_number: int = 5) -> SessionState:
    """Create a SessionState with session_id and turn_number."""
    state = SessionState(session_id=session_id)
    state.total_turn_count = turn_number
    return state


# ---------------------------------------------------------------------------
# Tests — Constraint Addition Logging
# ---------------------------------------------------------------------------

def test_add_locked_constraint_logs_constraint_added():
    """Adding a new constraint logs constraint_added event with session_id and turn_number."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.info = MagicMock()

        state = _make_session_state(session_id="session-abc", turn_number=7)
        state.add_locked_constraint("database", "PostgreSQL")

        # Verify logging
        assert mock_logger.info.called
        call_args = mock_logger.info.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'constraint_added'
        assert call_args.kwargs['session_id'] == "session-abc"
        assert call_args.kwargs['turn_number'] == 7
        assert call_args.kwargs['constraint_key'] == "database"
        assert call_args.kwargs['constraint_value'] == "PostgreSQL"
        assert call_args.kwargs['total_constraints'] == 1


def test_add_locked_constraint_conflict_logs_warning():
    """Adding duplicate constraint logs constraint_conflict event with old and new values."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.warning = MagicMock()
        mock_logger.info = MagicMock()

        state = _make_session_state(session_id="session-xyz", turn_number=10)
        state.add_locked_constraint("cache", "Redis")  # First addition
        state.add_locked_constraint("cache", "Memcached")  # Conflict

        # Verify conflict logging (second call)
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'constraint_conflict'
        assert call_args.kwargs['session_id'] == "session-xyz"
        assert call_args.kwargs['turn_number'] == 10
        assert call_args.kwargs['constraint_key'] == "cache"
        assert call_args.kwargs['existing_value'] == "Redis"
        assert call_args.kwargs['attempted_value'] == "Memcached"
        assert call_args.kwargs['action'] == "keeping_original"

        # Verify original value was kept
        assert state.locked_constraints["cache"] == "Redis"


def test_add_locked_constraint_includes_total_count():
    """Constraint addition logs include total_constraints count."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.info = MagicMock()

        state = _make_session_state()
        state.add_locked_constraint("storage", "S3")
        state.add_locked_constraint("compute", "EC2")

        # Check second call (should have count=2)
        assert mock_logger.info.call_count == 2
        second_call = mock_logger.info.call_args_list[1]

        assert second_call.kwargs['total_constraints'] == 2


# ---------------------------------------------------------------------------
# Tests — Phase Transition Logging
# ---------------------------------------------------------------------------

def test_advance_phase_success_logs_phase_transition():
    """Successful phase transition logs phase_transition event with old and new phase."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.info = MagicMock()

        state = _make_session_state(session_id="session-123", turn_number=15)
        state.phase = InterviewPhase.SCOPE

        success = state.advance_phase(InterviewPhase.ARCHITECTURE)

        assert success is True
        assert state.phase == InterviewPhase.ARCHITECTURE

        # Verify logging
        assert mock_logger.info.called
        call_args = mock_logger.info.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'phase_transition'
        assert call_args.kwargs['session_id'] == "session-123"
        assert call_args.kwargs['turn_number'] == 15
        assert call_args.kwargs['old_phase'] == "scope"
        assert call_args.kwargs['new_phase'] == "architecture"
        assert 'phase_elapsed_seconds' in call_args.kwargs


def test_advance_phase_backward_blocked_logs_warning():
    """Backward phase transition logs phase_blocked event with reason."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.warning = MagicMock()

        state = _make_session_state(session_id="session-456", turn_number=20)
        state.phase = InterviewPhase.DEEP_DIVE

        # Try to go backward
        success = state.advance_phase(InterviewPhase.SCOPE)

        assert success is False
        assert state.phase == InterviewPhase.DEEP_DIVE  # Phase unchanged

        # Verify logging
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'phase_blocked'
        assert call_args.kwargs['session_id'] == "session-456"
        assert call_args.kwargs['turn_number'] == 20
        assert call_args.kwargs['current_phase'] == "deep_dive"
        assert call_args.kwargs['requested_phase'] == "scope"
        assert call_args.kwargs['reason'] == "monotonic_enforcement"


def test_advance_phase_same_phase_blocked():
    """Advancing to same phase logs phase_blocked event."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.warning = MagicMock()

        state = _make_session_state(session_id="session-789", turn_number=12)
        state.phase = InterviewPhase.ARCHITECTURE

        # Try to stay in same phase
        success = state.advance_phase(InterviewPhase.ARCHITECTURE)

        assert success is False

        # Verify logging
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args

        assert call_args.kwargs['event_type'] == 'phase_blocked'
        assert call_args.kwargs['current_phase'] == "architecture"
        assert call_args.kwargs['requested_phase'] == "architecture"


def test_advance_phase_invalid_phase_logs_warning():
    """Invalid phase request logs phase_invalid event."""
    with patch('backend.models.session.logger') as mock_logger:
        mock_logger.warning = MagicMock()

        state = _make_session_state(session_id="session-999", turn_number=3)

        # Try to advance to invalid phase (string instead of enum)
        success = state.advance_phase("invalid_phase")

        assert success is False

        # Verify logging
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args

        assert call_args.kwargs['event_type'] == 'phase_invalid'
        assert call_args.kwargs['session_id'] == "session-999"
        assert call_args.kwargs['turn_number'] == 3
