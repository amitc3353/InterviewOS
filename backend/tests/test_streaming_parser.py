"""Tests for StreamingResponseParser — all 8 must pass."""
import pytest
from backend.interview.response_parser import StreamingResponseParser


def _feed_and_flush(text: str) -> tuple:
    """Helper: feed entire string at once, flush, return (spoken_output, parser)."""
    parser = StreamingResponseParser()
    out = parser.feed(text) or ""
    final = parser.flush() or ""
    combined = (out + " " + final).strip()
    return combined, parser


def test_normal_ack_and_question():
    out, p = _feed_and_flush("[PHASE:scope][ACK:Got it.][Q:What about latency?][LISTEN:P99 target]")
    assert "Got it." in out
    assert "What about latency?" in out
    assert "P99 target" not in out        # LISTEN must not appear
    assert "LISTEN" not in out
    phase, _ = p.get_state_updates()
    assert phase == "scope"


def test_skip_acknowledgment():
    out, p = _feed_and_flush("[PHASE:scope][Q:What about latency?][LISTEN:P99][FOLLOWUP:Give me a number]")
    assert "What about latency?" in out
    assert "P99" not in out
    assert "Give me a number" not in out  # FOLLOWUP must not appear


def test_just_react_no_question():
    out, p = _feed_and_flush("[PHASE:architecture][ACK:Hmm.][LISTEN:Waiting for elaboration]")
    assert "Hmm." in out
    assert "Waiting for elaboration" not in out
    assert p.get_spoken_text() == "Hmm."


def test_phase_transition_with_summary():
    out, p = _feed_and_flush(
        "[PHASE:architecture][SUMMARY:Alright — 10K writes.][Q:High-level approach?][LOCK:scale_tps=10000]"
    )
    assert "Alright — 10K writes." in out
    assert "High-level approach?" in out
    phase, constraints = p.get_state_updates()
    assert phase == "architecture"
    assert constraints == {"scale_tps": "10000"}


def test_multiple_locks():
    _, p = _feed_and_flush(
        "[PHASE:scope][ACK:Right.][Q:What else?][LOCK:latency=500ms][LOCK:consistency=eventual]"
    )
    _, constraints = p.get_state_updates()
    assert constraints == {"latency": "500ms", "consistency": "eventual"}


def test_tags_spanning_chunks():
    """Tags split across two chunks must be parsed correctly."""
    parser = StreamingResponseParser()
    r1 = parser.feed("[PHASE:scope][ACK:Got")   # partial [ACK:Got it.] tag
    r2 = parser.feed(" it.][Q:What about?]")    # completes ACK + full Q
    parser.flush()
    spoken = parser.get_spoken_text()
    assert "Got it." in spoken
    assert "What about?" in spoken


def test_internal_tags_never_spoken():
    out, _ = _feed_and_flush(
        "[PHASE:scope][Q:What database?][LISTEN:SQL vs NoSQL][FOLLOWUP:Why that choice?]"
    )
    assert "SQL vs NoSQL" not in out
    assert "Why that choice?" not in out
    assert "What database?" in out


def test_json_fallback():
    """If Claude accidentally returns JSON, parser falls back gracefully."""
    json_response = (
        '{"phase": "scope", "interviewer_says": "Got it.", "question": "What about scale?",'
        ' "update_locked_constraints": null}'
    )
    parser = StreamingResponseParser()
    parser.feed(json_response)
    parser.flush()
    spoken = parser.get_spoken_text()
    # Either the ack or question (or both) must appear
    assert "Got it." in spoken or "What about scale?" in spoken
    phase, _ = parser.get_state_updates()
    assert phase == "scope"


def test_context_tag():
    """CONTEXT tag should be spoken (like ACK/Q)."""
    out, p = _feed_and_flush(
        "[PHASE:failure][CONTEXT:Your database region just went down.][Q:What breaks first?]"
    )
    assert "database region just went down" in out
    assert "What breaks first?" in out
    phase, _ = p.get_state_updates()
    assert phase == "failure"


def test_context_suppressed_by_summary():
    """CONTEXT must be suppressed if SUMMARY already spoken (same rule as ACK)."""
    out, p = _feed_and_flush(
        "[PHASE:architecture][SUMMARY:10K writes, fraud first.][CONTEXT:Extra context.][Q:Approach?]"
    )
    assert "10K writes" in out
    assert "Approach?" in out
    assert "Extra context" not in out   # Must be suppressed


def test_context_without_ack():
    """CONTEXT alone before Q is the standard pattern (no ACK needed)."""
    out, p = _feed_and_flush(
        "[PHASE:scope][CONTEXT:About a million DAU, mostly reads — 100:1 ratio.][Q:What else?]"
    )
    assert "million DAU" in out
    assert "What else?" in out
    assert "CONTEXT" not in out         # Tag name must not leak


def test_no_tag_response_spoken_as_fallback():
    """If LLM returns raw text with no tags, speak it rather than silencing the interview."""
    raw = "Hold on — what does checking the data store look like exactly?"
    out, p = _feed_and_flush(raw)
    assert "checking the data store" in out
    assert p.get_spoken_text() == raw


def test_trailing_stray_text_after_tags_discarded():
    """Trailing untagged text after valid tags should still be discarded (existing behaviour)."""
    out, p = _feed_and_flush("[PHASE:scope][Q:What about scale?] some trailing noise")
    assert "What about scale?" in out
    assert "trailing noise" not in out
