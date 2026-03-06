"""Tests for _JsonResponseParser and StreamingResponseParser JSON fallback — 10 tests, zero network calls."""

import pytest
from backend.interview.response_parser import StreamingResponseParser, _JsonResponseParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_json_parser() -> _JsonResponseParser:
    """Build a minimal _JsonResponseParser for testing."""
    return _JsonResponseParser(session_id="test-123", turn_number=1)


def _feed_and_flush(text: str) -> tuple:
    """Helper: feed entire string at once, flush, return (spoken_output, parser)."""
    parser = StreamingResponseParser()
    out = parser.feed(text) or ""
    final = parser.flush() or ""
    combined = (out + " " + final).strip()
    return combined, parser


# ---------------------------------------------------------------------------
# Tests: _JsonResponseParser.parse() — direct JSON parsing
# ---------------------------------------------------------------------------

def test_json_parse_valid_response():
    """Valid JSON with all fields is parsed correctly."""
    parser = _make_json_parser()
    raw = '{"phase": "scope", "interviewer_says": "Got it.", "question": "What about scale?", "update_locked_constraints": null}'

    spoken, phase, constraints = parser.parse(raw)

    assert "Got it." in spoken
    assert "What about scale?" in spoken
    assert phase == "scope"
    assert constraints is None


def test_json_parse_with_constraints():
    """JSON response with update_locked_constraints extracts constraints."""
    parser = _make_json_parser()
    raw = '{"phase": "scope", "interviewer_says": "Noted.", "question": "What else?", "update_locked_constraints": {"scale": "1M", "latency": "100ms"}}'

    spoken, phase, constraints = parser.parse(raw)

    assert "Noted." in spoken
    assert "What else?" in spoken
    assert phase == "scope"
    assert constraints == {"scale": "1M", "latency": "100ms"}


def test_json_parse_constraint_summary_takes_priority():
    """constraint_summary field takes priority over interviewer_says."""
    parser = _make_json_parser()
    raw = '{"phase": "architecture", "constraint_summary": "Alright — 10K writes per second.", "interviewer_says": "Got it.", "question": "How would you design this?"}'

    spoken, phase, constraints = parser.parse(raw)

    assert "10K writes per second" in spoken
    assert "How would you design this?" in spoken
    # constraint_summary is used instead of interviewer_says
    assert "Got it." not in spoken
    assert phase == "architecture"


def test_json_parse_question_only():
    """JSON with only a question field (no interviewer_says) still works."""
    parser = _make_json_parser()
    raw = '{"phase": "deep_dive", "question": "Can you explain the caching layer?"}'

    spoken, phase, constraints = parser.parse(raw)

    assert "caching layer" in spoken
    assert phase == "deep_dive"
    assert constraints is None


def test_json_parse_empty_fields():
    """JSON with empty string fields produces no spoken text."""
    parser = _make_json_parser()
    raw = '{"phase": "scope", "interviewer_says": "", "question": ""}'

    spoken, phase, constraints = parser.parse(raw)

    assert spoken == ""
    assert phase == "scope"


# ---------------------------------------------------------------------------
# Tests: _JsonResponseParser._fallback_parse() — malformed JSON
# ---------------------------------------------------------------------------

def test_fallback_markdown_code_block():
    """Markdown code block with JSON is parsed correctly."""
    parser = _make_json_parser()
    raw = 'Here is my response:\n```json\n{"phase": "scope", "interviewer_says": "Interesting.", "question": "Tell me more."}\n```\nThat is all.'

    spoken, phase, constraints = parser.parse(raw)

    assert "Interesting." in spoken
    assert "Tell me more." in spoken
    assert phase == "scope"


def test_fallback_regex_extraction():
    """Malformed JSON still extracts interviewer_says and question via regex."""
    parser = _make_json_parser()
    raw = '{ broken JSON here "interviewer_says": "I see.", "question": "What scale?" }'

    spoken, phase, constraints = parser.parse(raw)

    assert "I see." in spoken
    assert "What scale?" in spoken
    assert phase is None  # Can't extract phase from truly broken JSON
    assert constraints is None


def test_fallback_completely_unparseable():
    """Completely unparseable response returns truncated raw text."""
    parser = _make_json_parser()
    raw = "This is just plain text with no JSON structure at all."

    spoken, phase, constraints = parser.parse(raw)

    # Should return the raw text as fallback (truncated to 200 chars)
    assert "just plain text" in spoken
    assert phase is None
    assert constraints is None


def test_fallback_regex_extracts_phase():
    """Regex fallback extracts phase from malformed JSON."""
    parser = _make_json_parser()
    raw = '{ invalid "phase": "architecture", "question": "How do you handle failover?" }'

    spoken, phase, constraints = parser.parse(raw)

    assert "How do you handle failover?" in spoken
    assert phase == "architecture"


# ---------------------------------------------------------------------------
# Tests: StreamingResponseParser JSON mode integration
# ---------------------------------------------------------------------------

def test_streaming_parser_json_mode_with_constraints():
    """StreamingResponseParser correctly handles JSON response with constraints."""
    json_response = '{"phase": "scope", "interviewer_says": "Got it.", "question": "What about scale?", "update_locked_constraints": {"database": "PostgreSQL"}}'

    parser = StreamingResponseParser(session_id="test-456", turn_number=2)
    result = parser.feed(json_response)
    # In JSON mode, feed() returns None (buffers everything)
    assert result is None

    final = parser.flush()
    assert final is not None
    assert "Got it." in final or "What about scale?" in final

    phase, constraints = parser.get_state_updates()
    assert phase == "scope"
    assert constraints == {"database": "PostgreSQL"}
