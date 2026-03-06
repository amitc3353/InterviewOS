"""Tests for interview flow — phase transitions, locked constraints, end-to-end turn processing."""

from datetime import datetime, timedelta

import pytest

from backend.interview.phase_manager import PhaseManager
from backend.interview.response_parser import StreamingResponseParser
from backend.models.session import (
    InterviewPhase,
    InterviewSession,
    SessionState,
    PHASE_ORDER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_state(phase: InterviewPhase = InterviewPhase.INTRO,
                        elapsed_seconds: float = 0) -> SessionState:
    """Build a SessionState with specified phase and elapsed time."""
    state = SessionState(session_id="flow-test-123", phase=phase)
    state.phase_start_time = datetime.now() - timedelta(seconds=elapsed_seconds)
    return state


def _simulate_turn(state: SessionState, user_text: str, llm_response: str) -> StreamingResponseParser:
    """
    Simulate a full turn: user message → LLM response → state updates.

    Returns the parser so callers can inspect spoken text and state updates.
    """
    # Record user message
    state.add_message("user", user_text)

    # Parse LLM response
    parser = StreamingResponseParser(session_id=state.session_id, turn_number=state.total_turn_count)
    parser.feed(llm_response)
    parser.flush()

    # Apply state updates from parser
    phase, constraints = parser.get_state_updates()
    if phase:
        try:
            new_phase = InterviewPhase(phase)
            state.advance_phase(new_phase)
        except ValueError:
            pass
    if constraints:
        for key, value in constraints.items():
            state.add_locked_constraint(key, value)

    # Record assistant response
    spoken = parser.get_spoken_text()
    if spoken:
        state.add_message("assistant", spoken)

    return parser


# ---------------------------------------------------------------------------
# Tests: Phase transitions via response parser
# ---------------------------------------------------------------------------

def test_phase_transition_from_parser_output():
    """[PHASE:X] tag in LLM response triggers phase transition via parser."""
    state = _make_session_state()
    assert state.phase == InterviewPhase.INTRO

    parser = _simulate_turn(
        state,
        "Hi, I'm ready.",
        "[PHASE:scope][ACK:Great, let's begin.][Q:What's the scale?]"
    )

    assert state.phase == InterviewPhase.SCOPE
    phase, _ = parser.get_state_updates()
    assert phase == "scope"


def test_multiple_phase_transitions_across_turns():
    """Multiple turns advance through phases correctly."""
    state = _make_session_state()

    # Turn 1: INTRO → SCOPE
    _simulate_turn(state, "Hello", "[PHASE:scope][ACK:Let's scope it.][Q:Scale?]")
    assert state.phase == InterviewPhase.SCOPE

    # Turn 2: SCOPE → ARCHITECTURE
    _simulate_turn(state, "1M users", "[PHASE:architecture][SUMMARY:1M users, got it.][Q:Architecture?]")
    assert state.phase == InterviewPhase.ARCHITECTURE

    # Turn 3: ARCHITECTURE → DEEP_DIVE
    _simulate_turn(state, "Microservices", "[PHASE:deep_dive][ACK:Nice.][Q:Explain caching?]")
    assert state.phase == InterviewPhase.DEEP_DIVE


def test_backward_phase_transition_blocked():
    """Parser outputting a backward phase does not regress state."""
    state = _make_session_state(phase=InterviewPhase.ARCHITECTURE)

    _simulate_turn(state, "Let me reconsider", "[PHASE:scope][Q:What about scale?]")

    # Should stay at ARCHITECTURE (backward blocked)
    assert state.phase == InterviewPhase.ARCHITECTURE


def test_same_phase_tag_does_not_duplicate_transition():
    """[PHASE:X] with same phase as current does nothing."""
    state = _make_session_state(phase=InterviewPhase.SCOPE)
    state.phase_turn_count = 3  # Set some turns

    _simulate_turn(state, "More about scale", "[PHASE:scope][Q:Tell me more.]")

    assert state.phase == InterviewPhase.SCOPE
    # phase_turn_count should NOT be reset (no transition happened)
    assert state.phase_turn_count == 4  # Incremented by user message


# ---------------------------------------------------------------------------
# Tests: Locked constraints accumulation
# ---------------------------------------------------------------------------

def test_constraints_accumulated_across_turns():
    """Constraints from multiple turns accumulate in session state."""
    state = _make_session_state(phase=InterviewPhase.SCOPE)

    _simulate_turn(state, "1M users", "[ACK:Got it.][LOCK:scale=1M users][Q:Latency?]")
    _simulate_turn(state, "Under 100ms", "[ACK:Noted.][LOCK:latency=100ms][Q:Consistency?]")
    _simulate_turn(state, "Eventually consistent", "[ACK:Sure.][LOCK:consistency=eventual][Q:Database?]")

    assert len(state.locked_constraints) == 3
    assert state.locked_constraints["scale"] == "1M users"
    assert state.locked_constraints["latency"] == "100ms"
    assert state.locked_constraints["consistency"] == "eventual"


def test_constraint_overwrite_protection_in_flow():
    """Duplicate constraint key is rejected during multi-turn flow."""
    state = _make_session_state(phase=InterviewPhase.SCOPE)

    _simulate_turn(state, "PostgreSQL", "[ACK:OK.][LOCK:database=PostgreSQL][Q:Why?]")
    _simulate_turn(state, "Actually MySQL", "[ACK:OK.][LOCK:database=MySQL][Q:Sure?]")

    # Original constraint preserved
    assert state.locked_constraints["database"] == "PostgreSQL"
    assert len(state.locked_constraints) == 1


def test_constraints_persist_across_phase_transitions():
    """Constraints added in earlier phases persist after phase transitions."""
    state = _make_session_state()

    # Add constraint in SCOPE
    _simulate_turn(state, "Hello", "[PHASE:scope][LOCK:scale=10K][Q:Architecture?]")
    assert state.locked_constraints["scale"] == "10K"

    # Advance to ARCHITECTURE
    _simulate_turn(state, "Microservices", "[PHASE:architecture][LOCK:pattern=microservices][Q:Details?]")

    # Both constraints should exist
    assert len(state.locked_constraints) == 2
    assert state.locked_constraints["scale"] == "10K"
    assert state.locked_constraints["pattern"] == "microservices"


# ---------------------------------------------------------------------------
# Tests: Turn counting and conversation history
# ---------------------------------------------------------------------------

def test_turn_counts_increment_correctly():
    """Turn counts track user messages across multiple turns."""
    state = _make_session_state(phase=InterviewPhase.SCOPE)

    _simulate_turn(state, "First message", "[ACK:OK.][Q:Next?]")
    _simulate_turn(state, "Second message", "[ACK:OK.][Q:More?]")
    _simulate_turn(state, "Third message", "[ACK:OK.][Q:Done?]")

    assert state.total_turn_count == 3
    assert state.phase_turn_count == 3
    # User + assistant messages
    assert len(state.conversation_history) == 6


def test_phase_turn_count_resets_on_transition():
    """Phase turn count resets when transitioning to a new phase."""
    state = _make_session_state(phase=InterviewPhase.SCOPE)

    _simulate_turn(state, "Message 1", "[ACK:OK.][Q:Next?]")
    _simulate_turn(state, "Message 2", "[ACK:OK.][Q:More?]")
    assert state.phase_turn_count == 2

    # Transition to ARCHITECTURE
    _simulate_turn(state, "Let's move on", "[PHASE:architecture][Q:Architecture?]")

    # User message incremented before transition, then reset by advance_phase,
    # but the user message for this turn already incremented it before advance
    # Actually: add_message increments first, then advance_phase resets to 0
    assert state.phase_turn_count == 0  # Reset by advance_phase
    assert state.total_turn_count == 3  # Total keeps going


# ---------------------------------------------------------------------------
# Tests: PhaseManager + SessionState integration
# ---------------------------------------------------------------------------

def test_phase_manager_dynamic_context_includes_constraints():
    """PhaseManager dynamic context includes locked constraints."""
    pm = PhaseManager("Design a URL shortener")
    state = _make_session_state(phase=InterviewPhase.SCOPE)
    state.add_locked_constraint("scale", "1M")
    state.add_locked_constraint("latency", "100ms")

    context = pm.get_dynamic_context(state)

    assert "scale" in context
    assert "1M" in context
    assert "latency" in context
    assert "100ms" in context


def test_phase_manager_auto_advance_during_flow():
    """PhaseManager auto-advances when time budget is exceeded during get_dynamic_context."""
    pm = PhaseManager("Design a URL shortener")
    state = _make_session_state(phase=InterviewPhase.INTRO, elapsed_seconds=90)

    # INTRO budget is 60s, 90s exceeds it
    context = pm.get_dynamic_context(state)

    assert state.phase == InterviewPhase.SCOPE
    assert "SCOPE" in context or "scope" in context


def test_full_interview_flow_intro_to_wrap():
    """End-to-end flow: traverse all phases from INTRO to WRAP with constraints."""
    state = _make_session_state()
    pm = PhaseManager("Design a URL shortener")

    # INTRO → SCOPE
    _simulate_turn(state, "Hi!", "[PHASE:scope][ACK:Welcome!][Q:What scale?]")
    assert state.phase == InterviewPhase.SCOPE

    # Add constraints in SCOPE
    _simulate_turn(state, "1M URLs/day", "[LOCK:scale=1M/day][ACK:Got it.][Q:Latency?]")
    _simulate_turn(state, "Under 200ms", "[LOCK:latency=200ms][Q:Let's design.]")

    # SCOPE → ARCHITECTURE
    _simulate_turn(state, "Let's architect", "[PHASE:architecture][SUMMARY:1M/day, 200ms.][Q:High-level?]")
    assert state.phase == InterviewPhase.ARCHITECTURE

    # ARCHITECTURE → DEEP_DIVE
    _simulate_turn(state, "Hash-based keys", "[PHASE:deep_dive][ACK:Interesting.][Q:Collisions?]")
    assert state.phase == InterviewPhase.DEEP_DIVE

    # DEEP_DIVE → FAILURE
    _simulate_turn(state, "Retry with new hash", "[PHASE:failure][CONTEXT:Redis goes down.][Q:What breaks?]")
    assert state.phase == InterviewPhase.FAILURE

    # FAILURE → TRADEOFFS
    _simulate_turn(state, "Fallback to DB", "[PHASE:tradeoffs][ACK:Good fallback.][Q:Trade-offs?]")
    assert state.phase == InterviewPhase.TRADEOFFS

    # TRADEOFFS → WRAP
    _simulate_turn(state, "Latency vs consistency", "[PHASE:wrap][ACK:Great discussion.][Q:Questions for me?]")
    assert state.phase == InterviewPhase.WRAP

    # Verify accumulated state
    assert state.locked_constraints["scale"] == "1M/day"
    assert state.locked_constraints["latency"] == "200ms"
    assert state.total_turn_count == 8
    assert len(state.conversation_history) == 16  # 8 user + 8 assistant messages


def test_no_phase_tag_keeps_current_phase():
    """LLM response without [PHASE:] tag does not change the current phase."""
    state = _make_session_state(phase=InterviewPhase.SCOPE)

    _simulate_turn(state, "More details", "[ACK:Tell me more.][Q:What else?]")

    assert state.phase == InterviewPhase.SCOPE
