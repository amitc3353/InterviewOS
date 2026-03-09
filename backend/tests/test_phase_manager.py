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


# ---------------------------------------------------------------------------
# Tests: should_transition_phase with invalid phases (ValueError handling)
# ---------------------------------------------------------------------------

def test_should_transition_rejects_invalid_current_phase():
    """should_transition_phase returns False when current phase is invalid."""
    pm = PhaseManager("Design a URL shortener")
    state = SessionState(phase=InterviewPhase.SCOPE)
    # Forcibly set an invalid phase that isn't in PHASE_ORDER
    state.phase = "bogus_phase"

    result = pm.should_transition_phase(state, InterviewPhase.ARCHITECTURE)
    assert result is False


def test_should_transition_rejects_invalid_requested_phase():
    """should_transition_phase returns False when requested phase is invalid."""
    pm = PhaseManager("Design a URL shortener")
    state = SessionState(phase=InterviewPhase.SCOPE)

    result = pm.should_transition_phase(state, "nonexistent_phase")
    assert result is False


# ---------------------------------------------------------------------------
# Tests: get_next_phase with invalid phase (ValueError handling)
# ---------------------------------------------------------------------------

def test_get_next_phase_invalid_returns_intro():
    """get_next_phase with invalid phase defaults to INTRO."""
    pm = PhaseManager("Design a URL shortener")
    result = pm.get_next_phase("bogus")
    assert result == InterviewPhase.INTRO


def test_get_next_phase_wrap_stays_in_wrap():
    """get_next_phase from WRAP stays in WRAP (final phase)."""
    pm = PhaseManager("Design a URL shortener")
    result = pm.get_next_phase(InterviewPhase.WRAP)
    assert result == InterviewPhase.WRAP


def test_get_next_phase_normal_progression():
    """get_next_phase returns the correct next phase for valid phases."""
    pm = PhaseManager("Design a URL shortener")
    assert pm.get_next_phase(InterviewPhase.INTRO) == InterviewPhase.SCOPE
    assert pm.get_next_phase(InterviewPhase.SCOPE) == InterviewPhase.ARCHITECTURE
    assert pm.get_next_phase(InterviewPhase.DEEP_DIVE) == InterviewPhase.FAILURE


# ---------------------------------------------------------------------------
# Tests: _get_depth_guidance with mixed component formats
# ---------------------------------------------------------------------------

def test_depth_guidance_with_string_components():
    """_get_depth_guidance handles string components (not dicts) gracefully."""
    from backend.interview.scenario_loader import ScenarioMetadata
    metadata = ScenarioMetadata(
        id="test",
        name="Test Scenario",
        description="Test",
        archetype="distributed",
        complexity_notes="Complex stuff",
        scope_answers={},
        failure_scenarios=[],
        critical_components=["Component A", "Component B"],
        low_priority_components=["Low priority C"],
        scoring_benchmarks={},
        deep_dive_focus=[],
    )
    pm = PhaseManager("Test Scenario", scenario_metadata=metadata)
    guidance = pm._get_depth_guidance()

    assert "Component A" in guidance
    assert "Component B" in guidance


def test_depth_guidance_with_dict_components():
    """_get_depth_guidance handles dict components with name/why keys."""
    from backend.interview.scenario_loader import ScenarioMetadata
    metadata = ScenarioMetadata(
        id="test",
        name="Test Scenario",
        description="Test",
        archetype="distributed",
        complexity_notes="",
        scope_answers={},
        failure_scenarios=[],
        critical_components=[{"name": "Cache Layer", "why": "Performance critical"}],
        low_priority_components=[],
        scoring_benchmarks={},
        deep_dive_focus=[],
    )
    pm = PhaseManager("Test Scenario", scenario_metadata=metadata)
    guidance = pm._get_depth_guidance()

    assert "Cache Layer" in guidance
    assert "Performance critical" in guidance


def test_depth_guidance_with_dict_missing_keys():
    """_get_depth_guidance handles dicts missing 'name' or 'why' gracefully."""
    from backend.interview.scenario_loader import ScenarioMetadata
    metadata = ScenarioMetadata(
        id="test",
        name="Test Scenario",
        description="Test",
        archetype="distributed",
        complexity_notes="",
        scope_answers={},
        failure_scenarios=[],
        critical_components=[{"name": "Only Name"}, {}],
        low_priority_components=[],
        scoring_benchmarks={},
        deep_dive_focus=[],
    )
    pm = PhaseManager("Test Scenario", scenario_metadata=metadata)
    guidance = pm._get_depth_guidance()

    assert "Only Name" in guidance
    assert "Unknown" in guidance  # Empty dict defaults to "Unknown"


# ---------------------------------------------------------------------------
# Tests: _get_failure_scenarios_guidance with mixed formats
# ---------------------------------------------------------------------------

def test_failure_scenarios_with_string_entries():
    """_get_failure_scenarios_guidance handles string entries gracefully."""
    from backend.interview.scenario_loader import ScenarioMetadata
    metadata = ScenarioMetadata(
        id="test",
        name="Test Scenario",
        description="Test",
        archetype="distributed",
        complexity_notes="",
        scope_answers={},
        failure_scenarios=["Database goes down", "Network partition"],
        critical_components=[],
        low_priority_components=[],
        scoring_benchmarks={},
        deep_dive_focus=[],
    )
    pm = PhaseManager("Test Scenario", scenario_metadata=metadata)
    guidance = pm._get_failure_scenarios_guidance()

    assert "Database goes down" in guidance
    assert "Network partition" in guidance


def test_failure_scenarios_with_dict_entries():
    """_get_failure_scenarios_guidance handles dict entries with scenario/focus keys."""
    from backend.interview.scenario_loader import ScenarioMetadata
    metadata = ScenarioMetadata(
        id="test",
        name="Test Scenario",
        description="Test",
        archetype="distributed",
        complexity_notes="",
        scope_answers={},
        failure_scenarios=[
            {"scenario": "Region outage", "focus": "Failover mechanisms"},
            {"scenario": "Traffic spike"},  # Missing 'focus'
        ],
        critical_components=[],
        low_priority_components=[],
        scoring_benchmarks={},
        deep_dive_focus=[],
    )
    pm = PhaseManager("Test Scenario", scenario_metadata=metadata)
    guidance = pm._get_failure_scenarios_guidance()

    assert "Region outage" in guidance
    assert "Failover mechanisms" in guidance
    assert "Traffic spike" in guidance
