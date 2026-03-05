"""Tests for SyntheticInterviewRunner — 15 tests, zero network calls."""

import pytest
from unittest.mock import patch, MagicMock

from backend.interview.synthetic_runner import (
    DEFAULT_MAX_TURNS_PER_PHASE,
    InterviewRunResult,
    SyntheticInterviewRunner,
    TurnResult,
)
from backend.models.candidate_profile import (
    CandidatePersona,
    CandidateProfile,
    CommunicationStyle,
    SkillLevel,
)
from backend.models.session import InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(
    skill_level: SkillLevel = SkillLevel.MID,
    scenario_id: str = "url-shortener",
) -> CandidateProfile:
    """Build a minimal CandidateProfile for testing."""
    persona = CandidatePersona(
        name="Test Candidate",
        background="software engineer",
        years_of_experience=5,
        communication_style=CommunicationStyle.STRUCTURED,
    )
    return CandidateProfile(
        persona=persona,
        overall_skill_level=skill_level,
        scenario_id=scenario_id,
    )


def _make_runner(
    skill_level: SkillLevel = SkillLevel.MID,
    session_id: str = "test-session-001",
    max_turns_per_phase: dict = None,
) -> SyntheticInterviewRunner:
    """Build a SyntheticInterviewRunner for testing."""
    profile = _make_profile(skill_level=skill_level)
    return SyntheticInterviewRunner(
        profile=profile,
        session_id=session_id,
        max_turns_per_phase=max_turns_per_phase,
    )


# ---------------------------------------------------------------------------
# Tests — Initialization
# ---------------------------------------------------------------------------

def test_runner_initialization():
    """Runner initializes with correct session and profile data."""
    runner = _make_runner(session_id="init-test")

    assert runner.session.session_id == "init-test"
    assert runner.current_phase == InterviewPhase.INTRO
    assert runner.total_turns == 0


def test_runner_session_has_correct_scenario():
    """Runner's session stores the scenario from the profile."""
    runner = _make_runner()

    assert runner.session.scenario == "url-shortener"


# ---------------------------------------------------------------------------
# Tests — record_turn
# ---------------------------------------------------------------------------

def test_record_turn_stores_messages():
    """record_turn adds messages to session state conversation history."""
    runner = _make_runner()
    runner.record_turn(
        interviewer_message="Tell me about yourself.",
        candidate_response="I'm a software engineer with 5 years of experience.",
    )

    history = runner.session.state.conversation_history
    assert len(history) == 2
    assert history[0].role == "assistant"
    assert history[0].content == "Tell me about yourself."
    assert history[1].role == "user"
    assert history[1].content == "I'm a software engineer with 5 years of experience."


def test_record_turn_increments_turn_count():
    """record_turn increments the total turn count."""
    runner = _make_runner()
    runner.record_turn("Question 1?", "Answer 1.")
    runner.record_turn("Question 2?", "Answer 2.")

    assert runner.total_turns == 2


def test_record_turn_returns_turn_result():
    """record_turn returns a TurnResult with correct metadata."""
    runner = _make_runner()
    result = runner.record_turn("What is your experience?", "I have 5 years.")

    assert isinstance(result, TurnResult)
    assert result.turn_number == 1
    assert result.phase == "intro"
    assert result.interviewer_message == "What is your experience?"
    assert result.candidate_response == "I have 5 years."


def test_record_turn_tracks_phase():
    """TurnResult records the phase at time of recording."""
    runner = _make_runner()
    runner.record_turn("Intro question?", "Intro answer.")
    runner.advance_to_next_phase()  # Move to SCOPE
    result = runner.record_turn("Scope question?", "Scope answer.")

    assert result.phase == "scope"


# ---------------------------------------------------------------------------
# Tests — Phase advancement
# ---------------------------------------------------------------------------

def test_should_advance_phase_false_initially():
    """should_advance_phase returns False when no turns taken."""
    runner = _make_runner()
    assert runner.should_advance_phase() is False


def test_should_advance_phase_true_after_max_turns():
    """should_advance_phase returns True after reaching max turns for phase."""
    runner = _make_runner(max_turns_per_phase={InterviewPhase.INTRO: 2})

    runner.record_turn("Q1?", "A1.")
    runner.record_turn("Q2?", "A2.")

    assert runner.should_advance_phase() is True


def test_advance_to_next_phase_succeeds():
    """advance_to_next_phase moves from INTRO to SCOPE."""
    runner = _make_runner()

    success = runner.advance_to_next_phase()

    assert success is True
    assert runner.current_phase == InterviewPhase.SCOPE


def test_advance_to_next_phase_progresses_through_all_phases():
    """advance_to_next_phase follows the full phase order."""
    runner = _make_runner()
    expected_phases = [
        InterviewPhase.SCOPE,
        InterviewPhase.ARCHITECTURE,
        InterviewPhase.DEEP_DIVE,
        InterviewPhase.FAILURE,
        InterviewPhase.TRADEOFFS,
        InterviewPhase.WRAP,
    ]

    for expected in expected_phases:
        success = runner.advance_to_next_phase()
        assert success is True
        assert runner.current_phase == expected


def test_advance_to_next_phase_returns_false_at_wrap():
    """advance_to_next_phase returns False when already at WRAP."""
    runner = _make_runner()

    # Advance through all phases to WRAP
    for _ in range(6):
        runner.advance_to_next_phase()

    assert runner.current_phase == InterviewPhase.WRAP
    assert runner.advance_to_next_phase() is False


# ---------------------------------------------------------------------------
# Tests — get_results
# ---------------------------------------------------------------------------

def test_get_results_not_completed_initially():
    """get_results shows completed=False before reaching WRAP."""
    runner = _make_runner()
    results = runner.get_results()

    assert isinstance(results, InterviewRunResult)
    assert results.completed is False
    assert results.total_turns == 0


def test_get_results_completed_after_wrap():
    """get_results shows completed=True when WRAP phase is reached."""
    runner = _make_runner()

    # Advance through all phases
    for _ in range(6):
        runner.advance_to_next_phase()

    results = runner.get_results()
    assert results.completed is True


def test_get_results_includes_turns():
    """get_results includes all recorded turns."""
    runner = _make_runner()
    runner.record_turn("Q1?", "A1.")
    runner.record_turn("Q2?", "A2.")

    results = runner.get_results()
    assert len(results.turns) == 2


def test_get_results_to_dict():
    """InterviewRunResult serializes to dict with all expected keys."""
    runner = _make_runner()
    runner.record_turn("Q1?", "A1.")

    result_dict = runner.get_results().to_dict()

    assert "session" in result_dict
    assert "profile" in result_dict
    assert "turns" in result_dict
    assert "phases_completed" in result_dict
    assert "total_turns" in result_dict
    assert "completed" in result_dict


# ---------------------------------------------------------------------------
# Tests — get_candidate_prompt and get_phase_summary
# ---------------------------------------------------------------------------

def test_get_candidate_prompt_returns_string():
    """get_candidate_prompt returns a non-empty prompt string."""
    runner = _make_runner()
    prompt = runner.get_candidate_prompt()

    assert isinstance(prompt, str)
    assert len(prompt) > 50
    assert "Test Candidate" in prompt


def test_get_phase_summary():
    """get_phase_summary returns turn counts per phase."""
    runner = _make_runner()
    runner.record_turn("Q1?", "A1.")
    runner.record_turn("Q2?", "A2.")
    runner.advance_to_next_phase()
    runner.record_turn("Q3?", "A3.")

    summary = runner.get_phase_summary()
    assert summary["intro"] == 2
    assert summary["scope"] == 1


# ---------------------------------------------------------------------------
# Tests — TurnResult and InterviewRunResult serialization
# ---------------------------------------------------------------------------

def test_turn_result_to_dict():
    """TurnResult serializes to dictionary with all fields."""
    turn = TurnResult(
        turn_number=3,
        phase="architecture",
        interviewer_message="Explain your database choice.",
        candidate_response="I chose PostgreSQL for strong consistency.",
    )
    result = turn.to_dict()

    assert result["turn_number"] == 3
    assert result["phase"] == "architecture"
    assert "PostgreSQL" in result["candidate_response"]


def test_get_transcript():
    """get_transcript formats turns as readable text."""
    runner = _make_runner()
    runner.record_turn("Tell me about yourself.", "I'm a software engineer.")
    runner.advance_to_next_phase()
    runner.record_turn("What scale?", "About a million users.")

    transcript = runner.get_results().get_transcript()

    assert "[INTERVIEWER]" in transcript
    assert "[CANDIDATE]" in transcript
    assert "(intro)" in transcript
    assert "(scope)" in transcript
