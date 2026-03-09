"""Tests for ScoringEngine — scoring logic + API retry resilience, zero network calls."""
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# Tests: _call_claude retry logic
# ---------------------------------------------------------------------------

def _mock_api_response(raw_json: dict) -> MagicMock:
    """Build a mock Anthropic API response with content[0].text."""
    response = MagicMock()
    response.content = [MagicMock()]
    response.content[0].text = json.dumps(raw_json)
    return response


def _mock_config():
    """Build a minimal config for _call_claude tests."""
    config = MagicMock()
    config.anthropic_api_key = "test-key"
    config.llm_model = "claude-sonnet-4-20250514"
    return config


@pytest.mark.asyncio
async def test_call_claude_success_no_retry():
    """Successful API call returns parsed JSON without retrying."""
    expected = _make_mock_claude_response({dim: 3 for dim in DIMENSION_WEIGHTS})
    mock_response = _mock_api_response(expected)

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        engine = ScoringEngine()
        result = await engine._call_claude("test prompt", _mock_config())

    assert result == expected
    assert mock_client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_call_claude_retries_on_429():
    """429 rate limit triggers retry with backoff."""
    expected = _make_mock_claude_response({dim: 4 for dim in DIMENSION_WEIGHTS})
    mock_response = _mock_api_response(expected)

    rate_limit_err = Exception("Rate limited")
    rate_limit_err.status_code = 429

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[rate_limit_err, mock_response]
    )

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        with patch("backend.interview.scoring_engine.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            engine = ScoringEngine()
            result = await engine._call_claude("test prompt", _mock_config())

    assert result == expected
    assert mock_client.messages.create.call_count == 2
    mock_sleep.assert_called_once_with(1.0)  # backoff_base * 2^0


@pytest.mark.asyncio
async def test_call_claude_retries_on_502():
    """502 server error triggers retry."""
    expected = _make_mock_claude_response({dim: 3 for dim in DIMENSION_WEIGHTS})
    mock_response = _mock_api_response(expected)

    server_err = Exception("Bad gateway")
    server_err.status_code = 502

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[server_err, mock_response]
    )

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        with patch("backend.interview.scoring_engine.asyncio.sleep", new_callable=AsyncMock):
            engine = ScoringEngine()
            result = await engine._call_claude("test prompt", _mock_config())

    assert result == expected
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_call_claude_raises_after_max_retries():
    """Exhausting retries on transient errors raises the last exception."""
    server_err = Exception("Server overloaded")
    server_err.status_code = 529

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[server_err, server_err, server_err]
    )

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        with patch("backend.interview.scoring_engine.asyncio.sleep", new_callable=AsyncMock):
            engine = ScoringEngine()
            with pytest.raises(Exception, match="Server overloaded"):
                await engine._call_claude("test prompt", _mock_config())

    assert mock_client.messages.create.call_count == 3


@pytest.mark.asyncio
async def test_call_claude_non_retryable_error_raises_immediately():
    """Non-retryable errors (e.g. 401) are raised without retry."""
    auth_err = Exception("Unauthorized")
    auth_err.status_code = 401

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=auth_err)

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        engine = ScoringEngine()
        with pytest.raises(Exception, match="Unauthorized"):
            await engine._call_claude("test prompt", _mock_config())

    assert mock_client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_call_claude_retries_on_json_parse_failure():
    """JSON parse failure triggers retry, second attempt succeeds."""
    expected = _make_mock_claude_response({dim: 3 for dim in DIMENSION_WEIGHTS})

    bad_response = MagicMock()
    bad_response.content = [MagicMock()]
    bad_response.content[0].text = "not valid json {"

    good_response = _mock_api_response(expected)

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[bad_response, good_response]
    )

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        engine = ScoringEngine()
        result = await engine._call_claude("test prompt", _mock_config())

    assert result == expected
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_call_claude_strips_markdown_fences():
    """Markdown fences around JSON are stripped before parsing."""
    expected = _make_mock_claude_response({dim: 5 for dim in DIMENSION_WEIGHTS})

    fenced_response = MagicMock()
    fenced_response.content = [MagicMock()]
    fenced_response.content[0].text = f"```json\n{json.dumps(expected)}\n```"

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=fenced_response)

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        engine = ScoringEngine()
        result = await engine._call_claude("test prompt", _mock_config())

    assert result == expected


# ---------------------------------------------------------------------------
# Tests: empty response content handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_claude_retries_on_empty_content():
    """Empty response.content triggers retry, second attempt succeeds."""
    expected = _make_mock_claude_response({dim: 3 for dim in DIMENSION_WEIGHTS})

    empty_response = MagicMock()
    empty_response.content = []  # Empty content

    good_response = _mock_api_response(expected)

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=[empty_response, good_response]
    )

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        engine = ScoringEngine()
        result = await engine._call_claude("test prompt", _mock_config())

    assert result == expected
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_call_claude_raises_on_persistent_empty_content():
    """Empty response.content on all attempts raises RuntimeError."""
    empty_response = MagicMock()
    empty_response.content = []

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=empty_response)

    with patch("backend.interview.scoring_engine.anthropic.AsyncAnthropic", return_value=mock_client):
        engine = ScoringEngine()
        with pytest.raises(RuntimeError, match="empty response content"):
            await engine._call_claude("test prompt", _mock_config())

    assert mock_client.messages.create.call_count == 3


# ---------------------------------------------------------------------------
# Tests: _parse_scorecard robustness (missing dimensions, score clamping)
# ---------------------------------------------------------------------------

def test_parse_scorecard_missing_dimension_uses_default():
    """Missing dimension in raw JSON defaults to score 3 with fallback rationale."""
    # Only provide 3 of 5 dimensions
    raw = {
        "dimensions": {
            "requirements_gathering": _make_dimension_data(4),
            "system_architecture": _make_dimension_data(5),
            "communication": _make_dimension_data(4),
            # technical_depth and scalability_reliability missing
        },
        "narrative": "Partial scoring data.",
    }
    engine = ScoringEngine()
    session = _make_session()
    scorecard = engine._parse_scorecard(raw, session)

    # Missing dimensions should default to score 3
    assert scorecard.dimensions["technical_depth"].score == 3
    assert scorecard.dimensions["technical_depth"].label == "Solid"
    assert "parsing error" in scorecard.dimensions["technical_depth"].rationale

    assert scorecard.dimensions["scalability_reliability"].score == 3

    # Present dimensions should be scored normally
    assert scorecard.dimensions["requirements_gathering"].score == 4
    assert scorecard.dimensions["system_architecture"].score == 5


def test_parse_scorecard_score_clamped_to_valid_range():
    """Scores outside 1-5 range are clamped."""
    raw = {
        "dimensions": {
            "requirements_gathering": {"score": 0, "rationale": "Low"},
            "system_architecture": {"score": 10, "rationale": "High"},
            "technical_depth": {"score": -1, "rationale": "Negative"},
            "scalability_reliability": {"score": 5, "rationale": "Max"},
            "communication": {"score": 1, "rationale": "Min"},
        },
        "narrative": "Edge case scoring.",
    }
    engine = ScoringEngine()
    session = _make_session()
    scorecard = engine._parse_scorecard(raw, session)

    assert scorecard.dimensions["requirements_gathering"].score == 1  # clamped from 0
    assert scorecard.dimensions["system_architecture"].score == 5    # clamped from 10
    assert scorecard.dimensions["technical_depth"].score == 1        # clamped from -1
    assert scorecard.dimensions["scalability_reliability"].score == 5
    assert scorecard.dimensions["communication"].score == 1


def test_parse_scorecard_missing_narrative_uses_default():
    """Missing narrative field uses fallback text."""
    raw = {
        "dimensions": {dim: _make_dimension_data(3) for dim in DIMENSION_WEIGHTS},
        # No "narrative" key
    }
    engine = ScoringEngine()
    session = _make_session()
    scorecard = engine._parse_scorecard(raw, session)

    assert scorecard.narrative == "Narrative not available"


def test_parse_scorecard_empty_dimensions_all_default():
    """Completely empty dimensions dict defaults all to score 3."""
    raw = {
        "dimensions": {},
        "narrative": "No dimensions.",
    }
    engine = ScoringEngine()
    session = _make_session()
    scorecard = engine._parse_scorecard(raw, session)

    for dim_key in DIMENSION_WEIGHTS:
        assert scorecard.dimensions[dim_key].score == 3
        assert scorecard.dimensions[dim_key].label == "Solid"

    # Overall score should be 3.0 (all 3s)
    assert scorecard.overall_score == 3.0


def test_parse_scorecard_malformed_dimension_data():
    """Dimension with wrong type (e.g. string instead of dict) defaults to 3."""
    raw = {
        "dimensions": {
            "requirements_gathering": "not a dict",
            "system_architecture": _make_dimension_data(4),
            "technical_depth": _make_dimension_data(4),
            "scalability_reliability": _make_dimension_data(4),
            "communication": _make_dimension_data(4),
        },
        "narrative": "Mostly valid.",
    }
    engine = ScoringEngine()
    session = _make_session()
    scorecard = engine._parse_scorecard(raw, session)

    # Malformed dimension defaults to 3
    assert scorecard.dimensions["requirements_gathering"].score == 3
    # Others are fine
    assert scorecard.dimensions["system_architecture"].score == 4
