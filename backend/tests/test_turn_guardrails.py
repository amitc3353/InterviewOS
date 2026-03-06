"""Tests for PhaseManager._get_turn_guardrails — behavioral guardrails injected per-turn."""

import pytest
from datetime import datetime, timedelta

from backend.interview.phase_manager import PhaseManager
from backend.models.session import SessionState, InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state(
    phase: InterviewPhase = InterviewPhase.SCOPE,
    total_turns: int = 0,
    phase_turns: int = 0,
) -> SessionState:
    """Build a SessionState with specified phase and turn counts."""
    state = SessionState(phase=phase)
    state.total_turn_count = total_turns
    state.phase_turn_count = phase_turns
    return state


def _get_guardrails(state: SessionState, scenario: str = "Design a URL shortener") -> str:
    """Get guardrails text from PhaseManager for a given state."""
    pm = PhaseManager(scenario)
    return pm._get_turn_guardrails(state)


# ---------------------------------------------------------------------------
# Tests — Always-on guardrails
# ---------------------------------------------------------------------------

def test_word_check_always_present():
    """WORD CHECK guardrail is always present regardless of turn count."""
    state = _make_session_state(total_turns=0)
    guardrails = _get_guardrails(state)

    assert "WORD CHECK" in guardrails
    assert "60 words" in guardrails
    assert "30 words" in guardrails


def test_one_question_always_present():
    """ONE QUESTION ONLY guardrail is always present."""
    state = _make_session_state(total_turns=3)
    guardrails = _get_guardrails(state)

    assert "ONE QUESTION ONLY" in guardrails
    assert "question marks" in guardrails


def test_zero_praise_always_present():
    """ZERO PRAISE guardrail is always present."""
    state = _make_session_state(total_turns=1)
    guardrails = _get_guardrails(state)

    assert "ZERO PRAISE" in guardrails
    assert "Great" in guardrails
    assert "Excellent" in guardrails
    assert "Got it." in guardrails


def test_all_three_always_on_guardrails_present_at_turn_zero():
    """All three always-on guardrails present even at turn 0."""
    state = _make_session_state(total_turns=0)
    guardrails = _get_guardrails(state)

    assert "WORD CHECK" in guardrails
    assert "ONE QUESTION ONLY" in guardrails
    assert "ZERO PRAISE" in guardrails


# ---------------------------------------------------------------------------
# Tests — Conditional guardrails
# ---------------------------------------------------------------------------

def test_brevity_alert_absent_before_10_turns():
    """BREVITY ALERT should NOT appear before 10 total turns."""
    state = _make_session_state(total_turns=9)
    guardrails = _get_guardrails(state)

    assert "BREVITY ALERT" not in guardrails


def test_brevity_alert_present_at_10_turns():
    """BREVITY ALERT should appear at exactly 10 total turns."""
    state = _make_session_state(total_turns=10)
    guardrails = _get_guardrails(state)

    assert "BREVITY ALERT" in guardrails
    assert "10 turns" in guardrails


def test_brevity_alert_present_at_25_turns():
    """BREVITY ALERT should appear at 25 total turns with correct count."""
    state = _make_session_state(total_turns=25)
    guardrails = _get_guardrails(state)

    assert "BREVITY ALERT" in guardrails
    assert "25 turns" in guardrails


def test_silence_rule_absent_before_7_phase_turns():
    """SILENCE RULE should NOT appear before 7 phase turns."""
    state = _make_session_state(phase_turns=6)
    guardrails = _get_guardrails(state)

    assert "SILENCE RULE" not in guardrails


def test_silence_rule_present_at_7_phase_turns():
    """SILENCE RULE should appear at exactly 7 phase turns."""
    state = _make_session_state(phase_turns=7)
    guardrails = _get_guardrails(state)

    assert "SILENCE RULE" in guardrails
    assert "just react" in guardrails


def test_silence_rule_present_at_14_phase_turns():
    """SILENCE RULE should appear at 14 phase turns (multiple of 7)."""
    state = _make_session_state(phase_turns=14)
    guardrails = _get_guardrails(state)

    assert "SILENCE RULE" in guardrails


def test_silence_rule_absent_at_8_phase_turns():
    """SILENCE RULE should NOT appear at 8 phase turns (not multiple of 7)."""
    state = _make_session_state(phase_turns=8)
    guardrails = _get_guardrails(state)

    assert "SILENCE RULE" not in guardrails


def test_silence_rule_absent_at_zero_phase_turns():
    """SILENCE RULE should NOT appear at 0 phase turns (0 % 7 == 0 but guarded)."""
    state = _make_session_state(phase_turns=0)
    guardrails = _get_guardrails(state)

    assert "SILENCE RULE" not in guardrails


# ---------------------------------------------------------------------------
# Tests — Guardrails in dynamic context
# ---------------------------------------------------------------------------

def test_guardrails_included_in_dynamic_context():
    """Guardrails are embedded in get_dynamic_context output."""
    pm = PhaseManager("Design a URL shortener")
    state = _make_session_state(total_turns=15, phase_turns=7)

    context = pm.get_dynamic_context(state)

    # All always-on guardrails
    assert "WORD CHECK" in context
    assert "ONE QUESTION ONLY" in context
    assert "ZERO PRAISE" in context

    # Conditional: 15 > 10 so brevity alert present
    assert "BREVITY ALERT" in context

    # Conditional: 7 phase turns so silence rule present
    assert "SILENCE RULE" in context


def test_guardrails_in_dynamic_context_early_session():
    """Early session dynamic context has only the three always-on guardrails."""
    pm = PhaseManager("Design a URL shortener")
    state = _make_session_state(total_turns=3, phase_turns=2)

    context = pm.get_dynamic_context(state)

    assert "WORD CHECK" in context
    assert "ONE QUESTION ONLY" in context
    assert "ZERO PRAISE" in context
    assert "BREVITY ALERT" not in context
    assert "SILENCE RULE" not in context


# ---------------------------------------------------------------------------
# Tests — Different phases
# ---------------------------------------------------------------------------

def test_guardrails_work_across_all_phases():
    """Guardrails are generated for every interview phase."""
    pm = PhaseManager("Design a URL shortener")

    for phase in InterviewPhase:
        state = _make_session_state(phase=phase, total_turns=5)
        guardrails = pm._get_turn_guardrails(state)

        # Always-on guardrails present for every phase
        assert "WORD CHECK" in guardrails
        assert "ONE QUESTION ONLY" in guardrails
        assert "ZERO PRAISE" in guardrails
