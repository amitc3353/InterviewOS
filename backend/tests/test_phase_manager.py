"""Tests for PhaseManager time budget enforcement — 5 tests, zero network calls."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from backend.interview.phase_manager import PhaseManager
from backend.models.session import SessionState, InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state(phase: InterviewPhase, elapsed_seconds: float = 0) -> SessionState:
    """
    Build a SessionState with specified phase and elapsed time.

    Args:
        phase: Current interview phase
        elapsed_seconds: How long the phase has been running

    Returns:
        SessionState with mocked phase_start_time
    """
    state = SessionState(phase=phase)
    # Set phase_start_time to simulate elapsed time
    state.phase_start_time = datetime.now() - timedelta(seconds=elapsed_seconds)
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_phase_advances_when_time_limit_exceeded():
    """When phase exceeds time budget, auto-advance to next phase."""
    pm = PhaseManager("Design a URL shortener")

    # SCOPE phase with 11 minutes elapsed (budget is 10 min = 600s)
    state = _make_session_state(InterviewPhase.SCOPE, elapsed_seconds=660)

    # Verify initial phase
    assert state.phase == InterviewPhase.SCOPE

    # Check time budget enforcement
    was_advanced = pm.check_and_enforce_time_budget(state)

    # Should advance to ARCHITECTURE
    assert was_advanced is True
    assert state.phase == InterviewPhase.ARCHITECTURE
    assert state.phase_turn_count == 0  # Reset on phase change


def test_no_advance_when_under_time_limit():
    """When phase is under time budget, do not advance."""
    pm = PhaseManager("Design a URL shortener")

    # SCOPE phase with 5 minutes elapsed (budget is 10 min = 600s)
    state = _make_session_state(InterviewPhase.SCOPE, elapsed_seconds=300)

    # Verify initial phase
    assert state.phase == InterviewPhase.SCOPE

    # Check time budget enforcement
    was_advanced = pm.check_and_enforce_time_budget(state)

    # Should NOT advance
    assert was_advanced is False
    assert state.phase == InterviewPhase.SCOPE


def test_wrap_phase_does_not_crash_when_time_exceeded():
    """WRAP phase (final phase) doesn't crash when time budget exceeded."""
    pm = PhaseManager("Design a URL shortener")

    # WRAP phase with 5 minutes elapsed (budget is 2 min = 120s)
    state = _make_session_state(InterviewPhase.WRAP, elapsed_seconds=300)

    # Verify initial phase
    assert state.phase == InterviewPhase.WRAP

    # Check time budget enforcement - should not crash
    was_advanced = pm.check_and_enforce_time_budget(state)

    # Should NOT advance (it's the final phase)
    assert was_advanced is False
    assert state.phase == InterviewPhase.WRAP


def test_get_dynamic_context_enforces_time_budget():
    """get_dynamic_context() calls time budget enforcement before generating context."""
    pm = PhaseManager("Design a URL shortener")

    # ARCHITECTURE phase with 16 minutes elapsed (budget is 15 min = 900s)
    state = _make_session_state(InterviewPhase.ARCHITECTURE, elapsed_seconds=960)

    # Verify initial phase
    assert state.phase == InterviewPhase.ARCHITECTURE

    # Call get_dynamic_context (should auto-advance)
    context = pm.get_dynamic_context(state)

    # Should have advanced to DEEP_DIVE
    assert state.phase == InterviewPhase.DEEP_DIVE
    # Context should reflect new phase
    assert "DEEP_DIVE" in context or "deep_dive" in context


def test_multiple_phases_with_different_time_budgets():
    """Verify different phases have different time budgets."""
    pm = PhaseManager("Design a URL shortener")

    # Test INTRO (1 min budget)
    state_intro = _make_session_state(InterviewPhase.INTRO, elapsed_seconds=90)
    assert pm.check_and_enforce_time_budget(state_intro) is True
    assert state_intro.phase == InterviewPhase.SCOPE

    # Test DEEP_DIVE (10 min budget)
    state_deep_dive = _make_session_state(InterviewPhase.DEEP_DIVE, elapsed_seconds=605)
    assert pm.check_and_enforce_time_budget(state_deep_dive) is True
    assert state_deep_dive.phase == InterviewPhase.FAILURE

    # Test TRADEOFFS (5 min budget)
    state_tradeoffs = _make_session_state(InterviewPhase.TRADEOFFS, elapsed_seconds=310)
    assert pm.check_and_enforce_time_budget(state_tradeoffs) is True
    assert state_tradeoffs.phase == InterviewPhase.WRAP


def test_time_budget_exactly_at_limit():
    """Phase exactly at time budget should not advance (edge case)."""
    pm = PhaseManager("Design a URL shortener")

    # Use a fixed datetime to avoid timing drift between setting phase_start_time
    # and the check_and_enforce_time_budget call (which also calls datetime.now())
    fixed_now = datetime(2024, 3, 15, 10, 10, 0)  # Fixed point in time
    state = SessionState(phase=InterviewPhase.SCOPE)

    with patch("backend.models.session.datetime") as mock_dt:
        mock_dt.now = lambda: fixed_now
        # Set phase_start_time exactly 600s before fixed_now
        state.phase_start_time = fixed_now - timedelta(seconds=600)

        # Verify initial phase
        assert state.phase == InterviewPhase.SCOPE

        # Check time budget enforcement
        was_advanced = pm.check_and_enforce_time_budget(state)

    # Should NOT advance (only exceeds if > budget, not >=)
    assert was_advanced is False
    assert state.phase == InterviewPhase.SCOPE
