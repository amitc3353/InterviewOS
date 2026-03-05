"""Tests for structured logging in phase_manager.py — phase transitions and prompt generation."""

from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import pytest

from backend.models.session import SessionState, InterviewPhase
from backend.interview.phase_manager import PhaseManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state(
    session_id: str = "test-session-123",
    turn_number: int = 5,
    phase: InterviewPhase = InterviewPhase.SCOPE
) -> SessionState:
    """Create a SessionState with session_id and turn_number."""
    state = SessionState(session_id=session_id, phase=phase)
    state.total_turn_count = turn_number
    return state


# ---------------------------------------------------------------------------
# Tests — Phase Transition Check Logging
# ---------------------------------------------------------------------------

def test_should_transition_phase_invalid_logs_debug():
    """Invalid phase request logs phase_transition_check with rejected_invalid."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        manager = PhaseManager("Design a payment gateway")
        state = _make_session_state(session_id="session-abc", turn_number=10, phase=InterviewPhase.SCOPE)

        # Try invalid phase (string instead of enum)
        result = manager.should_transition_phase(state, "invalid_phase")

        assert result is False

        # Verify logging
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args

        assert call_args.kwargs['event_type'] == 'phase_transition_check'
        assert call_args.kwargs['session_id'] == "session-abc"
        assert call_args.kwargs['turn_number'] == 10
        assert call_args.kwargs['result'] == 'rejected_invalid'


def test_should_transition_phase_backward_logs_rejected():
    """Backward phase transition logs phase_transition_check with rejected_monotonic."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        manager = PhaseManager("Design a URL shortener")
        state = _make_session_state(session_id="session-xyz", turn_number=20, phase=InterviewPhase.DEEP_DIVE)

        # Try to go backward
        result = manager.should_transition_phase(state, InterviewPhase.SCOPE)

        assert result is False

        # Verify logging
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args

        assert call_args.kwargs['event_type'] == 'phase_transition_check'
        assert call_args.kwargs['session_id'] == "session-xyz"
        assert call_args.kwargs['turn_number'] == 20
        assert call_args.kwargs['current_phase'] == 'deep_dive'
        assert call_args.kwargs['requested_phase'] == 'scope'
        assert call_args.kwargs['result'] == 'rejected_monotonic'


def test_should_transition_scope_to_architecture_logs_constraints():
    """Scope→Architecture transition check logs with constraint count."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        manager = PhaseManager("Design a chat application")
        state = _make_session_state(session_id="session-123", turn_number=5, phase=InterviewPhase.SCOPE)
        state.phase_turn_count = 4
        state.locked_constraints = {"scale": "1M users", "latency": "< 100ms"}

        result = manager.should_transition_phase(state, InterviewPhase.ARCHITECTURE)

        assert result is True  # 4 turns + 2 constraints = allowed

        # Verify logging
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args

        assert call_args.kwargs['event_type'] == 'phase_transition_check'
        assert call_args.kwargs['session_id'] == "session-123"
        assert call_args.kwargs['turn_number'] == 5
        assert call_args.kwargs['phase_turn_count'] == 4
        assert call_args.kwargs['locked_constraints_count'] == 2
        assert call_args.kwargs['result'] == 'allowed'


def test_should_transition_min_turns_blocked_logs_debug():
    """Insufficient turns logs phase_transition_check with rejected_min_turns."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        manager = PhaseManager("Design a file storage system")
        state = _make_session_state(session_id="session-456", turn_number=10, phase=InterviewPhase.ARCHITECTURE)
        state.phase_turn_count = 3  # Needs 8 turns minimum

        result = manager.should_transition_phase(state, InterviewPhase.DEEP_DIVE)

        assert result is False

        # Verify logging
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args

        assert call_args.kwargs['event_type'] == 'phase_transition_check'
        assert call_args.kwargs['session_id'] == "session-456"
        assert call_args.kwargs['turn_number'] == 10
        assert call_args.kwargs['phase_turn_count'] == 3
        assert call_args.kwargs['min_turns_required'] == 8
        assert call_args.kwargs['result'] == 'rejected_min_turns'


def test_should_transition_allowed_logs_success():
    """Allowed phase transition logs phase_transition_check with allowed."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        manager = PhaseManager("Design a recommendation engine")
        state = _make_session_state(session_id="session-789", turn_number=25, phase=InterviewPhase.DEEP_DIVE)
        state.phase_turn_count = 8  # More than minimum

        result = manager.should_transition_phase(state, InterviewPhase.FAILURE)

        assert result is True

        # Verify logging
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args

        assert call_args.kwargs['event_type'] == 'phase_transition_check'
        assert call_args.kwargs['session_id'] == "session-789"
        assert call_args.kwargs['turn_number'] == 25
        assert call_args.kwargs['result'] == 'allowed'


# ---------------------------------------------------------------------------
# Tests — Time Budget Enforcement Logging
# ---------------------------------------------------------------------------

def test_check_time_budget_timeout_logs_warning():
    """Phase timeout logs phase_timeout event before auto-advancing."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.warning = MagicMock()
        mock_logger.info = MagicMock()

        manager = PhaseManager("Design a caching system")
        state = _make_session_state(session_id="session-time-1", turn_number=15, phase=InterviewPhase.SCOPE)

        # Set phase start time to 15 minutes ago (exceeds 10 min budget)
        state.phase_start_time = datetime.now() - timedelta(minutes=15)

        result = manager.check_and_enforce_time_budget(state)

        assert result is True  # Phase was advanced

        # Verify timeout warning was logged
        assert mock_logger.warning.call_count >= 1
        warning_call = mock_logger.warning.call_args_list[0]

        assert warning_call.kwargs['event_type'] == 'phase_timeout'
        assert warning_call.kwargs['session_id'] == "session-time-1"
        assert warning_call.kwargs['turn_number'] == 15
        assert warning_call.kwargs['phase'] == 'scope'
        assert warning_call.kwargs['next_phase'] == 'architecture'
        assert warning_call.kwargs['phase_elapsed_seconds'] >= 600  # At least 10 minutes


def test_check_time_budget_final_phase_logs_warning():
    """Final phase timeout logs warning but does not advance."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.warning = MagicMock()

        manager = PhaseManager("Design a notification system")
        state = _make_session_state(session_id="session-time-2", turn_number=40, phase=InterviewPhase.WRAP)

        # Set phase start time to 5 minutes ago (exceeds 2 min budget)
        state.phase_start_time = datetime.now() - timedelta(minutes=5)

        result = manager.check_and_enforce_time_budget(state)

        assert result is False  # No advancement (final phase)
        assert state.phase == InterviewPhase.WRAP

        # Verify warning was logged
        assert mock_logger.warning.called
        call_args = mock_logger.warning.call_args

        assert call_args.kwargs['event_type'] == 'phase_timeout'
        assert call_args.kwargs['session_id'] == "session-time-2"
        assert call_args.kwargs['phase'] == 'wrap'
        assert 'final phase' in call_args.args[0]


def test_check_time_budget_auto_advance_logs_info():
    """Auto-advance logs phase_transition info event."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.warning = MagicMock()
        mock_logger.info = MagicMock()

        manager = PhaseManager("Design a search engine")
        state = _make_session_state(session_id="session-time-3", turn_number=12, phase=InterviewPhase.ARCHITECTURE)

        # Set phase start time to 20 minutes ago (exceeds 15 min budget)
        state.phase_start_time = datetime.now() - timedelta(minutes=20)

        result = manager.check_and_enforce_time_budget(state)

        assert result is True

        # Verify auto-advance info was logged
        assert mock_logger.info.called
        call_args = mock_logger.info.call_args

        assert call_args.kwargs['event_type'] == 'phase_transition'
        assert call_args.kwargs['session_id'] == "session-time-3"
        assert call_args.kwargs['turn_number'] == 12
        assert call_args.kwargs['from_phase'] == 'architecture'
        assert call_args.kwargs['to_phase'] == 'deep_dive'
        assert call_args.kwargs['trigger'] == 'time_budget'


# ---------------------------------------------------------------------------
# Tests — Prompt Generation Logging
# ---------------------------------------------------------------------------

def test_get_dynamic_context_logs_debug():
    """get_dynamic_context logs debug event with phase and constraint count."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        manager = PhaseManager("Design a video streaming service")
        state = _make_session_state(session_id="session-prompt-1", turn_number=8, phase=InterviewPhase.ARCHITECTURE)
        state.phase_turn_count = 5
        state.locked_constraints = {"cdn": "CloudFront", "encoding": "H.264"}

        context = manager.get_dynamic_context(state)

        assert context  # Should return non-empty string

        # Verify logging
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args

        assert call_args.kwargs['event_type'] == 'dynamic_context_generate'
        assert call_args.kwargs['session_id'] == "session-prompt-1"
        assert call_args.kwargs['turn_number'] == 8
        assert call_args.kwargs['phase'] == 'architecture'
        assert call_args.kwargs['phase_turn_count'] == 5
        assert call_args.kwargs['constraints_count'] == 2


def test_get_system_prompt_logs_debug():
    """get_system_prompt logs debug event with session context."""
    with patch('backend.interview.phase_manager.logger') as mock_logger:
        mock_logger.debug = MagicMock()

        manager = PhaseManager("Design an e-commerce platform")
        state = _make_session_state(session_id="session-prompt-2", turn_number=3, phase=InterviewPhase.INTRO)

        prompt = manager.get_system_prompt(state)

        assert prompt  # Should return non-empty string

        # Verify logging
        assert mock_logger.debug.called
        call_args = mock_logger.debug.call_args

        assert call_args.kwargs['event_type'] == 'system_prompt_generate'
        assert call_args.kwargs['session_id'] == "session-prompt-2"
        assert call_args.kwargs['turn_number'] == 3
        assert call_args.kwargs['phase'] == 'intro'
