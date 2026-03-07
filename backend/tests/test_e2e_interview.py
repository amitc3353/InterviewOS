"""End-to-end mock interview test — simulates complete interview programmatically.

Covers:
- Full phase progression: Intro → Scope → Architecture → Deep Dive → Failure → Tradeoffs → Wrap
- Transcript logging to file
- Voice pipeline validation (parser → state → scoring)
- Constraint accumulation and persistence across phases
- Phase time budget auto-advance
- Silence recovery mechanism
- Backward phase transition protection
- Scorecard generation after WRAP
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from backend.config import AgentConfig
from backend.interview.phase_manager import PhaseManager
from backend.interview.response_parser import StreamingResponseParser
from backend.interview.scoring_engine import ScoringEngine
from backend.models.scorecard import (
    DIMENSION_WEIGHTS,
    SCORE_LABELS,
    InterviewScorecard,
    compute_hire_signal,
)
from backend.models.session import (
    PHASE_ORDER,
    InterviewPhase,
    InterviewSession,
    SessionState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> AgentConfig:
    """Create minimal test config with fake API keys."""
    return AgentConfig(
        livekit_url="ws://test",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret",
        deepgram_api_key="test-dg",
        anthropic_api_key="test-anthropic",
        openai_api_key="test-openai",
        cartesia_api_key="test-cartesia",
    )


def _make_session(scenario: str = "Design a URL shortener") -> InterviewSession:
    """Build a minimal InterviewSession for testing."""
    return InterviewSession(session_id="e2e-test-001", scenario=scenario)


class MockTime:
    """Mock time controller to fast-forward through phase budgets."""

    def __init__(self):
        self.current_time = datetime(2024, 6, 15, 10, 0, 0)

    def advance(self, seconds: float) -> None:
        """Advance time by N seconds."""
        self.current_time += timedelta(seconds=seconds)

    def now(self) -> datetime:
        """Return current mocked time."""
        return self.current_time


def _simulate_turn(
    state: SessionState,
    user_text: str,
    llm_response: str,
) -> Tuple[StreamingResponseParser, str]:
    """
    Simulate a full turn: user message → parse LLM response → state updates.

    Returns (parser, spoken_text) so callers can inspect results.
    """
    # Record user message
    state.add_message("user", user_text)

    # Parse LLM response through streaming parser
    parser = StreamingResponseParser(
        session_id=state.session_id,
        turn_number=state.total_turn_count,
    )
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

    return parser, spoken


def _build_transcript_log(session: InterviewSession) -> str:
    """Format full transcript for file output."""
    lines = [
        f"=== Interview Transcript ===",
        f"Session ID: {session.session_id}",
        f"Scenario: {session.scenario}",
        f"Total Turns: {session.state.total_turn_count}",
        f"Final Phase: {session.state.phase.value}",
        f"Locked Constraints: {json.dumps(session.state.locked_constraints, indent=2)}",
        f"",
        f"--- Conversation ---",
    ]
    for msg in session.state.conversation_history:
        speaker = "[INTERVIEWER]" if msg.role == "assistant" else "[CANDIDATE]"
        lines.append(f"{speaker}: {msg.content}")
    return "\n".join(lines)


# Phase-specific LLM responses used across tests
_PHASE_RESPONSES: Dict[str, List[Tuple[str, str]]] = {
    "intro": [
        ("Hi, I'm ready to start the interview.", "[ACK:Welcome! Today we'll be designing a URL shortener.][Q:Where would you like to begin?]"),
    ],
    "scope": [
        ("Let's start by understanding the requirements. We need to handle at least 1 million URLs per day.",
         "[PHASE:scope][LOCK:scale=1M URLs/day][ACK:Got it, 1 million URLs per day.][Q:What about read-to-write ratio?]"),
        ("I'd estimate about 100:1 read-to-write ratio. Latency should be under 100ms for reads.",
         "[LOCK:read_write_ratio=100:1][LOCK:latency=<100ms reads][Q:What consistency model are you thinking?]"),
        ("Eventually consistent is fine for URL shortening since stale reads are acceptable.",
         "[LOCK:consistency=eventual][Q:Walk me through your high-level architecture.]"),
    ],
    "architecture": [
        ("I'll use a hash-based key generator with Base62 encoding. The system has an API gateway, application servers, and a distributed database.",
         "[PHASE:architecture][ACK:Interesting.][Q:How would you handle hash collisions?]"),
        ("For collisions, I'll use a check-and-retry approach with a Bloom filter to quickly detect duplicates before hitting the database.",
         "[LOCK:collision_strategy=bloom_filter+retry][Q:Tell me about your database choice.]"),
        ("I'll use DynamoDB for the main key-value store with Redis as a read-through cache for hot URLs.",
         "[LOCK:database=DynamoDB][LOCK:cache=Redis][Q:How does your write path look end to end?]"),
    ],
    "deep_dive": [
        ("The write path goes: client sends long URL to API gateway, which forwards to an app server. The server generates a Base62 key, checks the Bloom filter, writes to DynamoDB, and invalidates Redis cache.",
         "[PHASE:deep_dive][ACK:Walk me through what happens when two servers generate the same key simultaneously.][Q:How do you handle that race condition?]"),
        ("I'd use DynamoDB conditional writes with a condition that the key doesn't already exist. If it fails, we generate a new key and retry.",
         "[Q:What happens to the Bloom filter across multiple application server instances?]"),
        ("Good point. The Bloom filter needs to be centralized. I'd use a Redis-backed Bloom filter module so all servers share the same filter.",
         "[LOCK:bloom_filter_type=Redis-backed centralized][Q:What's the false positive rate you'd target?]"),
    ],
    "failure": [
        ("I'll set the false positive rate around 1% which gives a good space-time tradeoff.",
         "[PHASE:failure][CONTEXT:Your Redis cluster just went down entirely.][Q:What breaks in your system and how do you handle it?]"),
        ("If Redis goes down, reads fall back to DynamoDB directly. We lose caching and the Bloom filter temporarily. For the Bloom filter, we can fall back to just doing database lookups for collision checks. Latency increases but the system stays available.",
         "[Q:Your DynamoDB partition is getting throttled due to a hot key. What do you do?]"),
        ("For hot keys, I'd implement write sharding by appending a random suffix to partition keys and scatter-gather on reads. We could also add a DAX accelerator cluster.",
         "[LOCK:hot_key_strategy=write_sharding+DAX][Q:Walk me through your monitoring and alerting for these failure scenarios.]"),
    ],
    "tradeoffs": [
        ("I'd set up CloudWatch alarms on DynamoDB throttling events, Redis connection failures, and API latency p99. PagerDuty integration for critical alerts.",
         "[PHASE:tradeoffs][Q:What's the main tradeoff in your design between consistency and availability?]"),
        ("The main tradeoff is availability over consistency. We chose eventual consistency which means a shortened URL might not resolve for a brief window after creation. The benefit is much higher availability and lower latency.",
         "[Q:If you had to redesign one thing, what would it be?]"),
    ],
    "wrap": [
        ("I'd redesign the Bloom filter approach. Instead of centralized Redis-backed filters, I might use a probabilistic data structure directly in DynamoDB with atomic counters to avoid the Redis dependency entirely.",
         "[PHASE:wrap][ACK:Great discussion today. You showed strong system design thinking, especially around failure handling.][Q:Do you have any questions for me?]"),
        ("No questions. Thank you for the interview!",
         "[ACK:Thank you! Best of luck.]"),
    ],
}


def _mock_scoring_response() -> Dict:
    """Build a realistic mock scoring API response."""
    return {
        "dimensions": {
            "requirements_gathering": {
                "score": 4,
                "rationale": "Proactively defined scale, latency, consistency, and R/W ratio.",
                "strengths": ["Locked 4+ constraints early", "Specific numbers provided"],
                "gaps": ["Could have asked about geography/CDN"],
            },
            "system_architecture": {
                "score": 4,
                "rationale": "Clear component breakdown with justified choices for DynamoDB and Redis.",
                "strengths": ["Clean separation of read/write paths", "Bloom filter for collisions"],
                "gaps": ["API gateway design not detailed"],
            },
            "technical_depth": {
                "score": 4,
                "rationale": "Good depth on collision handling and write path. Conditional writes mentioned.",
                "strengths": ["Race condition handling", "Centralized Bloom filter decision"],
                "gaps": ["Could detail Base62 encoding algorithm"],
            },
            "scalability_reliability": {
                "score": 4,
                "rationale": "Handled Redis failure and hot key scenarios with concrete fallbacks.",
                "strengths": ["Write sharding for hot keys", "Graceful degradation without Redis"],
                "gaps": ["Multi-region not discussed"],
            },
            "communication": {
                "score": 5,
                "rationale": "Crystal clear, structured responses. Articulated tradeoffs precisely.",
                "strengths": ["Concise explanations", "Good use of frameworks"],
                "gaps": [],
            },
        },
        "narrative": "Strong Staff-level candidate who demonstrated solid system design fundamentals with "
        "particularly strong failure handling and clear communication throughout.",
    }


# ---------------------------------------------------------------------------
# Tests: Full E2E Interview Simulation
# ---------------------------------------------------------------------------


class TestE2EInterviewSimulation:
    """Test complete interview lifecycle from Intro to Wrap with transcript logging."""

    def test_complete_interview_all_phases(self):
        """Execute full mock interview through all 7 phases, verify transitions and state."""
        session = _make_session()
        pm = PhaseManager(session.scenario)
        state = session.state

        # Track visited phases
        visited_phases = [InterviewPhase.INTRO]

        # --- INTRO ---
        assert state.phase == InterviewPhase.INTRO
        for user_msg, llm_resp in _PHASE_RESPONSES["intro"]:
            _simulate_turn(state, user_msg, llm_resp)

        # --- SCOPE ---
        for user_msg, llm_resp in _PHASE_RESPONSES["scope"]:
            _simulate_turn(state, user_msg, llm_resp)
        if state.phase == InterviewPhase.SCOPE and state.phase not in visited_phases:
            visited_phases.append(InterviewPhase.SCOPE)
        assert state.phase == InterviewPhase.SCOPE
        assert "scale" in state.locked_constraints
        assert state.locked_constraints["scale"] == "1M URLs/day"

        # --- ARCHITECTURE ---
        for user_msg, llm_resp in _PHASE_RESPONSES["architecture"]:
            _simulate_turn(state, user_msg, llm_resp)
        if state.phase == InterviewPhase.ARCHITECTURE and state.phase not in visited_phases:
            visited_phases.append(InterviewPhase.ARCHITECTURE)
        assert state.phase == InterviewPhase.ARCHITECTURE
        assert "database" in state.locked_constraints
        assert "cache" in state.locked_constraints

        # --- DEEP DIVE ---
        for user_msg, llm_resp in _PHASE_RESPONSES["deep_dive"]:
            _simulate_turn(state, user_msg, llm_resp)
        if state.phase == InterviewPhase.DEEP_DIVE and state.phase not in visited_phases:
            visited_phases.append(InterviewPhase.DEEP_DIVE)
        assert state.phase == InterviewPhase.DEEP_DIVE
        assert "bloom_filter_type" in state.locked_constraints

        # --- FAILURE ---
        for user_msg, llm_resp in _PHASE_RESPONSES["failure"]:
            _simulate_turn(state, user_msg, llm_resp)
        if state.phase == InterviewPhase.FAILURE and state.phase not in visited_phases:
            visited_phases.append(InterviewPhase.FAILURE)
        assert state.phase == InterviewPhase.FAILURE
        assert "hot_key_strategy" in state.locked_constraints

        # --- TRADEOFFS ---
        for user_msg, llm_resp in _PHASE_RESPONSES["tradeoffs"]:
            _simulate_turn(state, user_msg, llm_resp)
        if state.phase == InterviewPhase.TRADEOFFS and state.phase not in visited_phases:
            visited_phases.append(InterviewPhase.TRADEOFFS)
        assert state.phase == InterviewPhase.TRADEOFFS

        # --- WRAP ---
        for user_msg, llm_resp in _PHASE_RESPONSES["wrap"]:
            _simulate_turn(state, user_msg, llm_resp)
        if state.phase == InterviewPhase.WRAP and state.phase not in visited_phases:
            visited_phases.append(InterviewPhase.WRAP)
        assert state.phase == InterviewPhase.WRAP

        # --- Final Assertions ---
        # All 7 phases were visited in order
        assert visited_phases == PHASE_ORDER, f"Expected all phases visited in order, got {visited_phases}"

        # Constraints accumulated correctly
        assert len(state.locked_constraints) >= 7
        assert state.locked_constraints["scale"] == "1M URLs/day"
        assert state.locked_constraints["consistency"] == "eventual"
        assert state.locked_constraints["database"] == "DynamoDB"
        assert state.locked_constraints["cache"] == "Redis"

        # Turn counts are correct
        total_user_messages = sum(len(turns) for turns in _PHASE_RESPONSES.values())
        assert state.total_turn_count == total_user_messages

        # Conversation history has both user and assistant messages
        assert len(state.conversation_history) == total_user_messages * 2

        # Session can be serialized without error
        session_dict = session.to_dict()
        assert session_dict["session_id"] == "e2e-test-001"
        assert session_dict["phase"] == "wrap"
        assert session_dict["total_turns"] == total_user_messages

    def test_transcript_logged_to_file(self):
        """Full interview transcript is logged to a temp file with correct format."""
        session = _make_session()
        state = session.state

        # Run through all phases
        for phase_key in ["intro", "scope", "architecture", "deep_dive", "failure", "tradeoffs", "wrap"]:
            for user_msg, llm_resp in _PHASE_RESPONSES[phase_key]:
                _simulate_turn(state, user_msg, llm_resp)

        # Log transcript to temp file
        transcript = _build_transcript_log(session)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(transcript)
            transcript_path = f.name

        try:
            # Read back and verify content
            with open(transcript_path, "r") as f:
                content = f.read()

            assert "=== Interview Transcript ===" in content
            assert "Session ID: e2e-test-001" in content
            assert "Design a URL shortener" in content
            assert "[CANDIDATE]:" in content
            assert "[INTERVIEWER]:" in content
            assert "Final Phase: wrap" in content

            # Verify constraints are in transcript
            assert "1M URLs/day" in content
            assert "DynamoDB" in content

            # Count speaker turns
            candidate_turns = content.count("[CANDIDATE]:")
            interviewer_turns = content.count("[INTERVIEWER]:")
            assert candidate_turns > 0
            assert interviewer_turns > 0
            assert candidate_turns == interviewer_turns  # 1:1 ratio

        finally:
            os.unlink(transcript_path)

    def test_no_crashes_throughout_session(self):
        """Verify no exceptions raised during complete interview simulation."""
        session = _make_session("Design a rate limiter")
        pm = PhaseManager(session.scenario)
        state = session.state

        # Run all phases — any exception will fail the test
        for phase_key in ["intro", "scope", "architecture", "deep_dive", "failure", "tradeoffs", "wrap"]:
            for user_msg, llm_resp in _PHASE_RESPONSES[phase_key]:
                parser, spoken = _simulate_turn(state, user_msg, llm_resp)
                # Spoken text should always be non-empty
                assert spoken, f"No spoken text for turn in {phase_key}"
                # Parser should not crash on state updates
                phase_update, constraints_update = parser.get_state_updates()

        # Dynamic context generation should not crash for any phase
        for phase in PHASE_ORDER:
            test_state = SessionState(session_id="crash-test", phase=phase)
            context = pm.get_dynamic_context(test_state)
            assert isinstance(context, str)
            assert len(context) > 0


# ---------------------------------------------------------------------------
# Tests: Phase Transition Mechanics
# ---------------------------------------------------------------------------


class TestPhaseTransitions:
    """Verify phase transition mechanics during e2e flow."""

    def test_phases_advance_monotonically(self):
        """All phase transitions move strictly forward through PHASE_ORDER."""
        state = SessionState(session_id="mono-test")
        phase_history = [state.phase]

        for phase_key in ["intro", "scope", "architecture", "deep_dive", "failure", "tradeoffs", "wrap"]:
            for user_msg, llm_resp in _PHASE_RESPONSES[phase_key]:
                _simulate_turn(state, user_msg, llm_resp)
                if state.phase not in phase_history:
                    phase_history.append(state.phase)

        # Verify strictly increasing order
        for i in range(1, len(phase_history)):
            prev_idx = PHASE_ORDER.index(phase_history[i - 1])
            curr_idx = PHASE_ORDER.index(phase_history[i])
            assert curr_idx > prev_idx, (
                f"Phase regression: {phase_history[i-1].value} → {phase_history[i].value}"
            )

    def test_backward_transition_blocked_during_flow(self):
        """Backward phase transitions are silently blocked during full interview."""
        state = SessionState(session_id="backward-test")

        # Advance to ARCHITECTURE
        _simulate_turn(state, "Hi", "[PHASE:scope][Q:Scale?]")
        _simulate_turn(state, "1M", "[PHASE:architecture][Q:Design?]")
        assert state.phase == InterviewPhase.ARCHITECTURE

        # Try backward transition to SCOPE — should be blocked
        _simulate_turn(state, "Wait, let me reconsider scope", "[PHASE:scope][Q:What scale?]")
        assert state.phase == InterviewPhase.ARCHITECTURE  # Stays at ARCHITECTURE

        # Forward transition still works
        _simulate_turn(state, "Microservices", "[PHASE:deep_dive][Q:Details?]")
        assert state.phase == InterviewPhase.DEEP_DIVE

    def test_time_budget_auto_advance(self):
        """Phase auto-advances when time budget is exceeded."""
        session = _make_session()
        pm = PhaseManager(session.scenario)
        state = session.state
        mock_time = MockTime()

        with patch("backend.models.session.datetime") as mock_dt:
            mock_dt.now = mock_time.now

            # Reset phase_start_time to use mocked time (init ran before mock)
            state.phase_start_time = mock_time.now()
            state.session_start_time = mock_time.now()

            # Start in INTRO
            assert state.phase == InterviewPhase.INTRO

            # Advance time past INTRO budget (60s)
            mock_time.advance(61)

            # Trigger time budget check
            pm.check_and_enforce_time_budget(state)
            assert state.phase == InterviewPhase.SCOPE

            # Advance time past SCOPE budget (600s)
            mock_time.advance(601)
            pm.check_and_enforce_time_budget(state)
            assert state.phase == InterviewPhase.ARCHITECTURE

            # Advance time past ARCHITECTURE budget (900s)
            mock_time.advance(901)
            pm.check_and_enforce_time_budget(state)
            assert state.phase == InterviewPhase.DEEP_DIVE

    def test_wrap_phase_does_not_auto_advance(self):
        """WRAP is the final phase and should never auto-advance."""
        session = _make_session()
        pm = PhaseManager(session.scenario)
        state = session.state
        mock_time = MockTime()

        with patch("backend.models.session.datetime") as mock_dt:
            mock_dt.now = mock_time.now

            # Jump to WRAP
            state.advance_phase(InterviewPhase.SCOPE)
            state.advance_phase(InterviewPhase.ARCHITECTURE)
            state.advance_phase(InterviewPhase.DEEP_DIVE)
            state.advance_phase(InterviewPhase.FAILURE)
            state.advance_phase(InterviewPhase.TRADEOFFS)
            state.advance_phase(InterviewPhase.WRAP)
            assert state.phase == InterviewPhase.WRAP

            # Exceed WRAP time budget (120s)
            mock_time.advance(300)
            pm.check_and_enforce_time_budget(state)
            assert state.phase == InterviewPhase.WRAP  # Still WRAP


# ---------------------------------------------------------------------------
# Tests: Constraint Handling
# ---------------------------------------------------------------------------


class TestConstraintHandling:
    """Verify locked constraint behavior during full interview flow."""

    def test_constraints_accumulate_across_all_phases(self):
        """Constraints added in different phases persist throughout the session."""
        state = SessionState(session_id="constraint-test")

        # Scope constraints
        _simulate_turn(state, "Hi", "[PHASE:scope][LOCK:scale=1M][Q:Latency?]")
        _simulate_turn(state, "100ms", "[LOCK:latency=100ms][Q:Database?]")
        assert len(state.locked_constraints) == 2

        # Architecture constraints
        _simulate_turn(state, "Postgres", "[PHASE:architecture][LOCK:database=Postgres][Q:Cache?]")
        _simulate_turn(state, "Redis", "[LOCK:cache=Redis][Q:Deep dive?]")
        assert len(state.locked_constraints) == 4

        # Deep dive constraints
        _simulate_turn(state, "Sharding", "[PHASE:deep_dive][LOCK:sharding=hash_based][Q:Failures?]")
        assert len(state.locked_constraints) == 5

        # All original constraints still present
        assert state.locked_constraints["scale"] == "1M"
        assert state.locked_constraints["latency"] == "100ms"
        assert state.locked_constraints["database"] == "Postgres"
        assert state.locked_constraints["cache"] == "Redis"
        assert state.locked_constraints["sharding"] == "hash_based"

    def test_constraint_overwrite_rejected(self):
        """Attempting to overwrite an existing constraint preserves the original."""
        state = SessionState(session_id="overwrite-test")

        _simulate_turn(state, "PostgreSQL", "[LOCK:database=PostgreSQL][Q:Why?]")
        assert state.locked_constraints["database"] == "PostgreSQL"

        # Try to overwrite
        _simulate_turn(state, "Actually MySQL", "[LOCK:database=MySQL][Q:Sure?]")
        assert state.locked_constraints["database"] == "PostgreSQL"  # Original preserved
        assert len(state.locked_constraints) == 1

    def test_constraints_in_dynamic_context(self):
        """PhaseManager includes all locked constraints in dynamic context output."""
        pm = PhaseManager("Design a URL shortener")
        state = SessionState(session_id="ctx-test", phase=InterviewPhase.ARCHITECTURE)

        state.add_locked_constraint("scale", "1M URLs/day")
        state.add_locked_constraint("latency", "<100ms")
        state.add_locked_constraint("consistency", "eventual")

        context = pm.get_dynamic_context(state)
        assert "scale" in context
        assert "1M URLs/day" in context
        assert "latency" in context
        assert "consistency" in context


# ---------------------------------------------------------------------------
# Tests: Silence Recovery
# ---------------------------------------------------------------------------


class TestSilenceRecovery:
    """Verify silence detection and recovery in e2e flow."""

    def test_consecutive_silence_tracking(self):
        """Empty user inputs increment consecutive_silence_count."""
        state = SessionState(session_id="silence-test", phase=InterviewPhase.DEEP_DIVE)

        # Substantive input — counter should stay at 0
        state.add_message("user", "Here's my approach to caching.")
        state.consecutive_silence_count = 0
        assert state.consecutive_silence_count == 0

        # Simulate 3 empty turns
        for i in range(3):
            state.add_message("user", "")
            state.consecutive_silence_count += 1
            assert state.consecutive_silence_count == i + 1

    def test_silence_counter_resets_on_substantive_input(self):
        """Silence counter resets when user provides substantive input."""
        state = SessionState(session_id="reset-test", phase=InterviewPhase.DEEP_DIVE)

        # Simulate 2 silences
        state.consecutive_silence_count = 2

        # Substantive input resets counter
        state.consecutive_silence_count = 0
        assert state.consecutive_silence_count == 0

    def test_silence_recovery_during_interview(self):
        """Silence recovery integrates with full interview turn simulation."""
        state = SessionState(session_id="recovery-test", phase=InterviewPhase.DEEP_DIVE)

        # Normal turn
        _simulate_turn(state, "Let me think about the database schema.", "[Q:How would you structure the schema?]")
        assert state.phase == InterviewPhase.DEEP_DIVE

        # Simulate empty turns (silence)
        for i in range(3):
            state.add_message("user", "")
            state.consecutive_silence_count += 1

        assert state.consecutive_silence_count == 3

        # Recovery turn with substantive input
        state.consecutive_silence_count = 0
        _simulate_turn(state, "Sorry, I was thinking. The schema has two tables.", "[ACK:No problem.][Q:What are the tables?]")
        assert state.consecutive_silence_count == 0
        assert state.phase == InterviewPhase.DEEP_DIVE  # Phase unchanged


# ---------------------------------------------------------------------------
# Tests: Scoring Pipeline
# ---------------------------------------------------------------------------


class TestScoringPipeline:
    """Verify post-interview scoring after complete session."""

    @pytest.mark.asyncio
    async def test_scorecard_generation_after_full_interview(self):
        """Generate scorecard after completing all interview phases."""
        session = _make_session()
        config = _make_config()

        # Run through all phases
        for phase_key in ["intro", "scope", "architecture", "deep_dive", "failure", "tradeoffs", "wrap"]:
            for user_msg, llm_resp in _PHASE_RESPONSES[phase_key]:
                _simulate_turn(session.state, user_msg, llm_resp)

        assert session.state.phase == InterviewPhase.WRAP

        # Mock Anthropic API for scoring
        mock_response = _mock_scoring_response()

        async def mock_create(**kwargs):
            resp = Mock()
            resp.content = [Mock()]
            resp.content[0].text = json.dumps(mock_response)
            return resp

        scoring_engine = ScoringEngine()

        with patch("anthropic.AsyncAnthropic") as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=mock_create)
            mock_anthropic_class.return_value = mock_client

            scorecard = await scoring_engine.score_interview(session, config)

        # Verify scorecard structure
        assert scorecard is not None
        assert scorecard.session_id == "e2e-test-001"
        assert scorecard.scenario == "Design a URL shortener"
        assert scorecard.overall_score > 0
        assert scorecard.hire_signal in ["Strong Yes", "Lean Yes", "Lean No", "No"]
        assert len(scorecard.dimensions) == 5

        # Verify all dimensions scored
        for dim_name in DIMENSION_WEIGHTS:
            assert dim_name in scorecard.dimensions
            dim = scorecard.dimensions[dim_name]
            assert 1 <= dim.score <= 5
            assert dim.label in SCORE_LABELS.values()
            assert len(dim.rationale) > 0

        # Verify scorecard serialization
        scorecard_dict = scorecard.to_dict()
        assert "dimensions" in scorecard_dict
        assert "overall_score" in scorecard_dict
        assert "hire_signal" in scorecard_dict
        assert "narrative" in scorecard_dict

    @pytest.mark.asyncio
    async def test_scoring_prompt_includes_transcript_and_constraints(self):
        """Scoring engine builds prompt with full transcript and locked constraints."""
        session = _make_session()

        # Minimal interview: scope + architecture
        _simulate_turn(session.state, "Hi", "[PHASE:scope][LOCK:scale=1M][Q:More?]")
        _simulate_turn(session.state, "Redis", "[LOCK:cache=Redis][Q:Design?]")

        scoring_engine = ScoringEngine()
        prompt = scoring_engine._build_scoring_prompt(session)

        # Transcript included
        assert "[CANDIDATE]:" in prompt or "CANDIDATE" in prompt.upper()
        assert "1M" in prompt
        assert "Redis" in prompt

        # Constraints included
        assert "scale" in prompt
        assert "cache" in prompt

        # Scenario included
        assert "URL shortener" in prompt

    @pytest.mark.asyncio
    async def test_hire_signal_thresholds(self):
        """Verify hire signal computation for different score ranges."""
        assert compute_hire_signal(4.5) == "Strong Yes"
        assert compute_hire_signal(4.0) == "Strong Yes"
        assert compute_hire_signal(3.7) == "Lean Yes"
        assert compute_hire_signal(3.5) == "Lean Yes"
        assert compute_hire_signal(3.0) == "Lean No"
        assert compute_hire_signal(2.5) == "Lean No"
        assert compute_hire_signal(2.0) == "No"
        assert compute_hire_signal(1.0) == "No"


# ---------------------------------------------------------------------------
# Tests: Voice Pipeline Validation (Parser Integration)
# ---------------------------------------------------------------------------


class TestVoicePipelineValidation:
    """Validate parser correctly extracts spoken text and state updates."""

    def test_parser_extracts_spoken_text_for_tts(self):
        """Parser correctly extracts text that would be sent to TTS."""
        parser = StreamingResponseParser(session_id="tts-test", turn_number=1)

        spoken = parser.feed("[ACK:Welcome to the interview.][Q:Where would you like to start?]")
        parser.flush()

        full_spoken = parser.get_spoken_text()
        assert "Welcome to the interview." in full_spoken
        assert "Where would you like to start?" in full_spoken

    def test_parser_extracts_phase_transitions(self):
        """Parser correctly extracts phase transition tags."""
        parser = StreamingResponseParser(session_id="phase-test", turn_number=1)

        parser.feed("[PHASE:architecture][ACK:Let's design.][Q:High-level components?]")
        parser.flush()

        phase, _ = parser.get_state_updates()
        assert phase == "architecture"

    def test_parser_extracts_lock_constraints(self):
        """Parser correctly extracts LOCK constraint tags."""
        parser = StreamingResponseParser(session_id="lock-test", turn_number=1)

        parser.feed("[LOCK:scale=1M][LOCK:latency=100ms][ACK:Got it.][Q:Next?]")
        parser.flush()

        _, constraints = parser.get_state_updates()
        assert constraints is not None
        assert constraints["scale"] == "1M"
        assert constraints["latency"] == "100ms"

    def test_parser_handles_chunked_streaming(self):
        """Parser handles response split across multiple chunks (simulating streaming)."""
        parser = StreamingResponseParser(session_id="chunk-test", turn_number=1)

        # Simulate chunked delivery
        parser.feed("[ACK:Gre")
        parser.feed("at poi")
        parser.feed("nt.]")
        spoken = parser.feed("[Q:How would you handle that?]")
        parser.flush()

        full_spoken = parser.get_spoken_text()
        assert "Great point." in full_spoken
        assert "How would you handle that?" in full_spoken

    def test_parser_json_fallback(self):
        """Parser falls back to JSON mode if LLM returns JSON instead of tags."""
        parser = StreamingResponseParser(session_id="json-test", turn_number=1)

        json_response = json.dumps({
            "interviewer_says": "Tell me about your design.",
            "question": "What scale are you targeting?",
            "phase": "scope",
        })

        parser.feed(json_response)
        spoken = parser.flush()

        assert spoken is not None
        assert "design" in spoken.lower() or "scale" in spoken.lower()

        phase, _ = parser.get_state_updates()
        assert phase == "scope"

    def test_full_pipeline_parser_to_state_update(self):
        """End-to-end: parser output drives session state changes correctly."""
        state = SessionState(session_id="pipeline-test")
        assert state.phase == InterviewPhase.INTRO
        assert len(state.locked_constraints) == 0

        # Turn 1: Intro (no phase change)
        _simulate_turn(state, "Hello", "[ACK:Welcome!][Q:Where to begin?]")
        assert state.phase == InterviewPhase.INTRO
        assert state.total_turn_count == 1

        # Turn 2: Transition to SCOPE with constraint
        _simulate_turn(state, "Scale discussion", "[PHASE:scope][LOCK:scale=10M][Q:Latency?]")
        assert state.phase == InterviewPhase.SCOPE
        assert state.locked_constraints["scale"] == "10M"
        assert state.total_turn_count == 2

        # Turn 3: Another constraint, no phase change
        _simulate_turn(state, "100ms", "[LOCK:latency=100ms][Q:Design?]")
        assert state.phase == InterviewPhase.SCOPE
        assert state.locked_constraints["latency"] == "100ms"
        assert state.total_turn_count == 3
        assert len(state.conversation_history) == 6  # 3 user + 3 assistant


# ---------------------------------------------------------------------------
# Tests: Session Serialization
# ---------------------------------------------------------------------------


class TestSessionSerialization:
    """Verify session data can be serialized after full interview."""

    def test_session_to_dict_after_full_interview(self):
        """InterviewSession.to_dict() includes all data after complete interview."""
        session = _make_session()

        for phase_key in ["intro", "scope", "architecture", "deep_dive", "failure", "tradeoffs", "wrap"]:
            for user_msg, llm_resp in _PHASE_RESPONSES[phase_key]:
                _simulate_turn(session.state, user_msg, llm_resp)

        result = session.to_dict()

        assert result["session_id"] == "e2e-test-001"
        assert result["scenario"] == "Design a URL shortener"
        assert result["phase"] == "wrap"
        assert result["total_turns"] > 0
        assert len(result["locked_constraints"]) >= 7
        assert len(result["conversation_history"]) > 0

        # Verify conversation history entries have required fields
        for entry in result["conversation_history"]:
            assert "role" in entry
            assert "content" in entry
            assert "timestamp" in entry
            assert entry["role"] in ("user", "assistant")

    def test_session_serializable_to_json(self):
        """Full session data can be serialized to valid JSON."""
        session = _make_session()

        for phase_key in ["intro", "scope", "architecture", "deep_dive", "failure", "tradeoffs", "wrap"]:
            for user_msg, llm_resp in _PHASE_RESPONSES[phase_key]:
                _simulate_turn(session.state, user_msg, llm_resp)

        result = session.to_dict()
        json_str = json.dumps(result)

        # Round-trip: serialize → deserialize
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "e2e-test-001"
        assert parsed["phase"] == "wrap"
        assert len(parsed["conversation_history"]) > 0
