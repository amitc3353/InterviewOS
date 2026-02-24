"""Tests for ScoringEngine — 7 tests, zero network calls."""
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.scorecard import (
    DIMENSION_WEIGHTS,
    SCORE_LABELS,
    DimensionScore,
    InterviewScorecard,
    compute_hire_signal,
)
from backend.models.session import InterviewSession, InterviewPhase
from backend.interview.scoring_engine import ScoringEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(transcript_lines=None, locked_constraints=None) -> InterviewSession:
    """Build a minimal InterviewSession for testing."""
    session = InterviewSession(session_id="test-session-123", scenario="Design a URL shortener")
    if locked_constraints:
        for k, v in locked_constraints.items():
            session.state.lock_constraint(k, v)
    if transcript_lines:
        for role, content in transcript_lines:
            session.state.add_message(role, content)
    return session


def _make_dimension_data(score: int) -> dict:
    return {
        "score": score,
        "rationale": "Candidate demonstrated clear thinking.",
        "strengths": ["Good structure"],
        "gaps": ["Could be more specific"],
    }


def _make_mock_claude_response(scores: dict) -> dict:
    """Build a mock Claude JSON response dict given per-dimension scores."""
    return {
        "dimensions": {dim: _make_dimension_data(score) for dim, score in scores.items()},
        "narrative": "Overall a solid candidate with room to grow.",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dimension_score_labels():
    """score 1→'Critical Gap', 5→'Exceptional', all intermediates correct."""
    assert SCORE_LABELS[1] == "Critical Gap"
    assert SCORE_LABELS[2] == "Developing"
    assert SCORE_LABELS[3] == "Solid"
    assert SCORE_LABELS[4] == "Strong"
    assert SCORE_LABELS[5] == "Exceptional"


def test_hire_signal_thresholds():
    """Boundary values for all 4 hire signals."""
    assert compute_hire_signal(4.0) == "Strong Yes"
    assert compute_hire_signal(5.0) == "Strong Yes"
    assert compute_hire_signal(3.5) == "Lean Yes"
    assert compute_hire_signal(3.9) == "Lean Yes"
    assert compute_hire_signal(2.5) == "Lean No"
    assert compute_hire_signal(3.4) == "Lean No"
    assert compute_hire_signal(1.0) == "No"
    assert compute_hire_signal(2.4) == "No"


def test_weighted_average_calculation():
    """scores=[4,4,3,4,5] → correct weighted average."""
    # Map in DIMENSION_WEIGHTS order: requirements_gathering, system_architecture,
    # technical_depth, scalability_reliability, communication
    scores = {
        "requirements_gathering": 4,   # weight 0.15 → 0.60
        "system_architecture":     4,   # weight 0.25 → 1.00
        "technical_depth":         3,   # weight 0.25 → 0.75
        "scalability_reliability": 4,   # weight 0.25 → 1.00
        "communication":           5,   # weight 0.10 → 0.50
    }
    expected = round(
        4 * 0.15 + 4 * 0.25 + 3 * 0.25 + 4 * 0.25 + 5 * 0.10, 1
    )  # = 3.85 → rounds to 3.9

    engine = ScoringEngine()
    session = _make_session()
    raw = _make_mock_claude_response(scores)
    scorecard = engine._parse_scorecard(raw, session)

    assert scorecard.overall_score == expected


def test_scorecard_to_dict():
    """to_dict() round-trips correctly; all 5 dimensions present."""
    scores = {dim: 3 for dim in DIMENSION_WEIGHTS}
    engine = ScoringEngine()
    session = _make_session(locked_constraints={"scale": "10K rps"})
    raw = _make_mock_claude_response(scores)
    scorecard = engine._parse_scorecard(raw, session)

    d = scorecard.to_dict()
    assert d["session_id"] == "test-session-123"
    assert d["scenario"] == "Design a URL shortener"
    assert set(d["dimensions"].keys()) == set(DIMENSION_WEIGHTS.keys())
    assert d["locked_constraints"] == {"scale": "10K rps"}
    assert "overall_score" in d
    assert "hire_signal" in d
    assert "narrative" in d
    assert "generated_at" in d

    # Each dimension has required keys
    for dim_dict in d["dimensions"].values():
        assert "score" in dim_dict
        assert "label" in dim_dict
        assert "rationale" in dim_dict
        assert "strengths" in dim_dict
        assert "gaps" in dim_dict


def test_scoring_prompt_contains_transcript():
    """_build_scoring_prompt output includes [INTERVIEWER]: and [CANDIDATE]: lines."""
    session = _make_session(
        transcript_lines=[
            ("assistant", "Tell me about the scale requirements."),
            ("user", "We expect about 10K writes per second."),
        ]
    )
    engine = ScoringEngine()
    prompt = engine._build_scoring_prompt(session)

    assert "[INTERVIEWER]: Tell me about the scale requirements." in prompt
    assert "[CANDIDATE]: We expect about 10K writes per second." in prompt


def test_scoring_prompt_contains_constraints():
    """Prompt includes locked_constraints keys and values."""
    session = _make_session(
        locked_constraints={
            "scale_tps": "10000",
            "latency": "500ms",
        }
    )
    engine = ScoringEngine()
    prompt = engine._build_scoring_prompt(session)

    assert "scale_tps" in prompt
    assert "10000" in prompt
    assert "latency" in prompt
    assert "500ms" in prompt


@pytest.mark.asyncio
async def test_parse_mock_response():
    """Given a mock Claude JSON response, _parse_scorecard produces correct InterviewScorecard."""
    scores = {
        "requirements_gathering": 4,
        "system_architecture":     5,
        "technical_depth":         3,
        "scalability_reliability": 4,
        "communication":           4,
    }
    raw = _make_mock_claude_response(scores)
    session = _make_session(locked_constraints={"consistency": "eventual"})

    engine = ScoringEngine()
    scorecard = engine._parse_scorecard(raw, session)

    # Correct types
    assert isinstance(scorecard, InterviewScorecard)
    assert set(scorecard.dimensions.keys()) == set(DIMENSION_WEIGHTS.keys())

    # Per-dimension labels correct
    assert scorecard.dimensions["requirements_gathering"].label == "Strong"
    assert scorecard.dimensions["system_architecture"].label == "Exceptional"
    assert scorecard.dimensions["technical_depth"].label == "Solid"

    # Weighted average
    expected_overall = round(4 * 0.15 + 5 * 0.25 + 3 * 0.25 + 4 * 0.25 + 4 * 0.10, 1)
    assert scorecard.overall_score == expected_overall

    # Hire signal derived from computed overall, not delegated to Claude
    assert scorecard.hire_signal == compute_hire_signal(expected_overall)

    # Narrative
    assert scorecard.narrative == "Overall a solid candidate with room to grow."

    # Metadata
    assert scorecard.session_id == "test-session-123"
    assert scorecard.locked_constraints == {"consistency": "eventual"}
