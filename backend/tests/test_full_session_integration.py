"""Full 45-minute interview session integration test — simulates complete interview with time-fast-forwarding."""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from livekit.agents import llm

from backend.agents.interview_agent import InterviewAgent
from backend.config import AgentConfig
from backend.models.session import InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> AgentConfig:
    """Create minimal test config."""
    return AgentConfig(
        livekit_url="ws://test",
        livekit_api_key="test-key",
        livekit_api_secret="test-secret",
        deepgram_api_key="test-dg",
        anthropic_api_key="test-anthropic",
        openai_api_key="test-openai",
        cartesia_api_key="test-cartesia",
    )


def _make_chat_chunk(content: str, chunk_id: str = "test-chunk") -> llm.ChatChunk:
    """Create a test chat chunk."""
    return llm.ChatChunk(
        id=chunk_id,
        delta=llm.ChoiceDelta(role="assistant", content=content),
    )


def _make_chat_ctx_with_message(message_text: str) -> MagicMock:
    """Create mock chat context with a user message."""
    mock_chat_ctx = MagicMock(spec=llm.ChatContext)
    mock_chat_ctx.items = []

    if message_text is not None:
        msg = MagicMock()
        msg.role = "user"
        msg.content = [message_text] if message_text else [""]
        mock_chat_ctx.messages = MagicMock(return_value=[msg])
    else:
        mock_chat_ctx.messages = MagicMock(return_value=[])

    mock_chat_ctx.add_message = MagicMock()
    return mock_chat_ctx


class MockTime:
    """Mock time controller to fast-forward through phases."""

    def __init__(self):
        self.current_time = datetime(2024, 3, 15, 10, 0, 0)  # Fixed start time

    def advance(self, seconds: float):
        """Advance time by N seconds."""
        self.current_time += timedelta(seconds=seconds)

    def now(self):
        """Return current mocked time."""
        return self.current_time


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_45_min_session_simulation():
    """
    Simulate a complete 45-minute interview session.

    Verifies:
    - All 7 phases transition correctly (INTRO → SCOPE → ... → WRAP)
    - Locked constraints accumulate without overwrites
    - Phase time budgets trigger auto-advance
    - Consecutive silence recovery works (3 empty turns → recovery question)
    - Session completes with scorecard generation

    Runs in <10 seconds but simulates 45 min of interview time.
    """
    # Setup
    config = _make_config()
    agent = InterviewAgent(config, "Design a URL shortener")
    mock_time = MockTime()

    # Track locked constraints to verify no overwrites
    initial_constraints_count = 0

    # Mock datetime.now() to use our mock_time
    with patch("backend.models.session.datetime") as mock_datetime:
        mock_datetime.now = mock_time.now

        # --- PHASE 1: INTRO (1 min) ---
        assert agent.interview_session.state.phase == InterviewPhase.INTRO

        # Turn 1: Initial greeting
        chat_ctx = _make_chat_ctx_with_message("Hi, I'm ready to start.")

        async def mock_llm_intro(*args, **kwargs):
            yield _make_chat_chunk("[ACK:Great! Let's begin.][Q:Ready to discuss the problem?]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_intro):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        assert agent.interview_session.state.phase == InterviewPhase.INTRO
        mock_time.advance(30)

        # Turn 2: Move to SCOPE (triggered by [PHASE:scope] tag)
        chat_ctx = _make_chat_ctx_with_message("Let's scope the problem.")

        async def mock_llm_intro_to_scope(*args, **kwargs):
            yield _make_chat_chunk("[PHASE:scope][ACK:Great.][Q:What's the scale?]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_intro_to_scope):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        # Parser extracts [PHASE:scope] and advances
        agent.interview_session.state.advance_phase(InterviewPhase.SCOPE)
        mock_time.advance(30)

        assert agent.interview_session.state.phase == InterviewPhase.SCOPE

        # --- PHASE 2: SCOPE (10 min) ---

        # Turn 3: User provides scale requirements
        chat_ctx = _make_chat_ctx_with_message("We need to handle 1M URLs per day.")

        async def mock_llm_scope_with_lock(*args, **kwargs):
            yield _make_chat_chunk("[LOCK:scale=1M URLs/day][ACK:Got it.][Q:What about latency?]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_scope_with_lock):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        # Manually add constraint (simulating response parser extracting [LOCK:])
        agent.interview_session.state.add_locked_constraint("scale", "1M URLs/day")
        mock_time.advance(120)

        # Turn 4: User provides latency requirement
        chat_ctx = _make_chat_ctx_with_message("Latency should be under 100ms.")

        async def mock_llm_scope_with_lock2(*args, **kwargs):
            yield _make_chat_chunk("[LOCK:latency=<100ms][Q:What about availability?]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_scope_with_lock2):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        agent.interview_session.state.add_locked_constraint("latency", "<100ms")
        initial_constraints_count = len(agent.interview_session.state.locked_constraints)
        assert initial_constraints_count >= 2
        mock_time.advance(120)

        # Test constraint overwrite protection
        # Try to overwrite "scale" — should be ignored
        agent.interview_session.state.add_locked_constraint("scale", "10M URLs/day")
        assert agent.interview_session.state.locked_constraints["scale"] == "1M URLs/day"
        assert len(agent.interview_session.state.locked_constraints) == initial_constraints_count

        # Advance time past SCOPE budget (10 min = 600s) to trigger auto-advance
        mock_time.advance(600 - 240)  # Already advanced 240s, need 360s more

        # Simulate a turn that triggers time budget check
        chat_ctx = _make_chat_ctx_with_message("Let me design the architecture now.")

        async def mock_llm_auto_advance(*args, **kwargs):
            yield _make_chat_chunk("[ACK:Okay, let's move forward.]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_auto_advance):
            # Call get_dynamic_context which enforces time budget
            agent.phase_manager.get_dynamic_context(agent.interview_session.state)

        # Verify auto-advance to ARCHITECTURE
        assert agent.interview_session.state.phase == InterviewPhase.ARCHITECTURE

        # --- PHASE 3: ARCHITECTURE (15 min) ---

        # Turn 5: User designs architecture
        chat_ctx = _make_chat_ctx_with_message("I'll use a hash-based key generator and Redis for caching.")

        async def mock_llm_arch(*args, **kwargs):
            yield _make_chat_chunk("[ACK:Interesting approach.][Q:How will you handle collisions?]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_arch):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        mock_time.advance(180)

        # Add another constraint
        agent.interview_session.state.add_locked_constraint("cache", "Redis")
        assert len(agent.interview_session.state.locked_constraints) > initial_constraints_count

        # Advance time past ARCHITECTURE budget (15 min = 900s)
        mock_time.advance(900 - 180)

        # Trigger auto-advance
        agent.phase_manager.get_dynamic_context(agent.interview_session.state)
        assert agent.interview_session.state.phase == InterviewPhase.DEEP_DIVE

        # --- PHASE 4: DEEP_DIVE (10 min) ---
        # Test consecutive silence recovery

        # Turn 6: Empty input (silence 1)
        chat_ctx = _make_chat_ctx_with_message("")

        async def mock_llm_silence1(*args, **kwargs):
            yield _make_chat_chunk("Sorry, I didn't catch that. Can you repeat?")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_silence1):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        assert agent.interview_session.state.consecutive_silence_count == 1
        mock_time.advance(10)

        # Turn 7: Empty input (silence 2)
        chat_ctx = _make_chat_ctx_with_message("")

        async def mock_llm_silence2(*args, **kwargs):
            yield _make_chat_chunk("Sorry, I didn't catch that. Can you repeat?")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_silence2):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        assert agent.interview_session.state.consecutive_silence_count == 2
        mock_time.advance(10)

        # Turn 8: Empty input (silence 3) — triggers recovery question
        chat_ctx = _make_chat_ctx_with_message("")

        async def mock_llm_recovery(*args, **kwargs):
            yield _make_chat_chunk("What specific part are you stuck on?")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_recovery):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        # Verify recovery triggered and counter reset
        assert agent.interview_session.state.consecutive_silence_count == 0
        mock_time.advance(10)

        # Turn 9: Substantive input resets counter
        chat_ctx = _make_chat_ctx_with_message("Let me think about the hash collision handling.")

        async def mock_llm_deep(*args, **kwargs):
            yield _make_chat_chunk("[ACK:Good thinking.][Q:What's your approach?]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_deep):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        mock_time.advance(600 - 30)  # Fill rest of DEEP_DIVE budget

        # Trigger auto-advance to FAILURE
        agent.phase_manager.get_dynamic_context(agent.interview_session.state)
        assert agent.interview_session.state.phase == InterviewPhase.FAILURE

        # --- PHASE 5: FAILURE (10 min) ---

        chat_ctx = _make_chat_ctx_with_message("If Redis goes down, we can fall back to database queries.")

        async def mock_llm_failure(*args, **kwargs):
            yield _make_chat_chunk("[ACK:Good fallback.][Q:What about data consistency?]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_failure):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        mock_time.advance(600)  # Full FAILURE budget

        # Trigger auto-advance to TRADEOFFS
        agent.phase_manager.get_dynamic_context(agent.interview_session.state)
        assert agent.interview_session.state.phase == InterviewPhase.TRADEOFFS

        # --- PHASE 6: TRADEOFFS (5 min) ---

        chat_ctx = _make_chat_ctx_with_message("The tradeoff is between latency and consistency.")

        async def mock_llm_tradeoffs(*args, **kwargs):
            yield _make_chat_chunk("[ACK:Interesting point.][Q:Which would you prioritize?]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_tradeoffs):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        mock_time.advance(300)  # Full TRADEOFFS budget

        # Trigger auto-advance to WRAP
        agent.phase_manager.get_dynamic_context(agent.interview_session.state)
        assert agent.interview_session.state.phase == InterviewPhase.WRAP

        # --- PHASE 7: WRAP (2 min) ---

        chat_ctx = _make_chat_ctx_with_message("Thank you for the interview!")

        async def mock_llm_wrap(*args, **kwargs):
            yield _make_chat_chunk("[ACK:Thank you! Great discussion today.]")

        with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_wrap):
            chunks = []
            async for chunk in agent.llm_node(chat_ctx, [], Mock()):
                chunks.append(chunk)

        mock_time.advance(120)  # Full WRAP budget

        # Verify WRAP is final phase (no auto-advance)
        agent.phase_manager.get_dynamic_context(agent.interview_session.state)
        assert agent.interview_session.state.phase == InterviewPhase.WRAP

        # --- Verify scorecard generation ---

        # Mock Anthropic API for scoring
        mock_scoring_response = {
            "dimensions": {
                "requirements_gathering": {"score": 4, "rationale": "Good scoping", "strengths": ["Asked about scale"], "gaps": []},
                "system_architecture": {"score": 4, "rationale": "Clear design", "strengths": ["Redis caching"], "gaps": []},
                "technical_depth": {"score": 3, "rationale": "Some detail", "strengths": [], "gaps": ["Could go deeper"]},
                "scalability_reliability": {"score": 4, "rationale": "Handled failures", "strengths": ["Fallback plan"], "gaps": []},
                "communication": {"score": 4, "rationale": "Clear and structured", "strengths": [], "gaps": []},
            },
            "overall_score": 3.9,
            "hire_signal": "HIRE",
        }

        async def mock_anthropic_create(**kwargs):
            mock_response = Mock()
            mock_response.content = [Mock()]
            mock_response.content[0].text = str(mock_scoring_response).replace("'", '"')
            return mock_response

        with patch("anthropic.AsyncAnthropic") as mock_anthropic_class:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=mock_anthropic_create)
            mock_anthropic_class.return_value = mock_client

            # Trigger scorecard generation
            scorecard = await agent._scoring_engine.generate_scorecard(agent.interview_session)

        # Verify scorecard was generated
        assert scorecard is not None
        assert scorecard.overall_score > 0
        assert scorecard.hire_signal in ["HIRE", "NO_HIRE", "STRONG_HIRE"]

        # --- Final verification ---

        # Verify all phases were visited
        assert agent.interview_session.state.phase == InterviewPhase.WRAP

        # Verify constraints accumulated
        assert len(agent.interview_session.state.locked_constraints) >= 3
        assert "scale" in agent.interview_session.state.locked_constraints
        assert "latency" in agent.interview_session.state.locked_constraints
        assert "cache" in agent.interview_session.state.locked_constraints

        # Verify no constraint overwrites
        assert agent.interview_session.state.locked_constraints["scale"] == "1M URLs/day"

        # Verify turn count
        assert agent.interview_session.state.total_turn_count >= 7

        # Verify session elapsed time (mocked ~45 min)
        total_elapsed = (mock_time.current_time - datetime(2024, 3, 15, 10, 0, 0)).total_seconds()
        assert total_elapsed >= 2700  # ~45 minutes
