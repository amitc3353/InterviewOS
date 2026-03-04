"""Tests for consecutive silence tracking and recovery question injection — 6 tests, zero network calls."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit.agents import llm

from backend.agents.interview_agent import InterviewAgent
from backend.config import AgentConfig
from backend.models.session import InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config() -> AgentConfig:
    """Create minimal test configuration."""
    return AgentConfig(
        livekit_url="ws://localhost:7880",
        livekit_api_key="test",
        livekit_api_secret="test",
        deepgram_api_key="test",
        anthropic_api_key="test",
        llm_model="claude-sonnet-4-20250514",
    )


def _make_agent(config: AgentConfig = None) -> InterviewAgent:
    """Create test agent instance."""
    if config is None:
        config = _make_config()
    return InterviewAgent(config, "Design a URL shortener")


def _make_chat_ctx_with_message(message_text: str) -> MagicMock:
    """Create mock chat context with a user message."""
    mock_chat_ctx = MagicMock(spec=llm.ChatContext)
    mock_chat_ctx.items = []

    if message_text is not None:
        # Create user message
        msg = MagicMock()
        msg.role = "user"
        msg.content = [message_text] if message_text else [""]
        mock_chat_ctx.messages = MagicMock(return_value=[msg])
    else:
        mock_chat_ctx.messages = MagicMock(return_value=[])

    mock_chat_ctx.add_message = MagicMock()
    return mock_chat_ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_silence_increments_counter():
    """First empty turn increments consecutive_silence_count to 1."""
    agent = _make_agent()
    mock_chat_ctx = _make_chat_ctx_with_message("")

    # Initial state
    assert agent.interview_session.state.consecutive_silence_count == 0

    # Call llm_node with empty message
    with patch('livekit.agents.Agent.default.llm_node'):
        chunks = []
        async for chunk in agent.llm_node(mock_chat_ctx, [], MagicMock()):
            chunks.append(chunk)

    # Verify counter incremented and recovery message sent
    assert agent.interview_session.state.consecutive_silence_count == 1
    assert len(chunks) == 1
    assert "didn't catch that" in chunks[0].delta.content


@pytest.mark.asyncio
async def test_second_silence_increments_counter():
    """Second consecutive empty turn increments counter to 2."""
    agent = _make_agent()
    agent.interview_session.state.consecutive_silence_count = 1

    mock_chat_ctx = _make_chat_ctx_with_message("")

    with patch('livekit.agents.Agent.default.llm_node'):
        chunks = []
        async for chunk in agent.llm_node(mock_chat_ctx, [], MagicMock()):
            chunks.append(chunk)

    # Verify counter incremented
    assert agent.interview_session.state.consecutive_silence_count == 2
    assert len(chunks) == 1
    assert "didn't catch that" in chunks[0].delta.content


@pytest.mark.asyncio
async def test_third_silence_triggers_recovery_question():
    """Third consecutive silence triggers LLM with recovery context instead of simple recovery."""
    agent = _make_agent()
    agent.interview_session.state.consecutive_silence_count = 2

    mock_chat_ctx = _make_chat_ctx_with_message("")

    # Mock phase_manager methods
    agent.phase_manager.get_static_system_prompt = MagicMock(return_value="Static prompt")
    agent.phase_manager.get_dynamic_context = MagicMock(return_value="Dynamic context")

    # Mock default LLM node to return a response
    async def mock_llm_stream():
        # Yield a single chunk with the recovery question
        yield llm.ChatChunk(
            id="test_chunk",
            delta=llm.ChoiceDelta(role="assistant", content="What specific part are you stuck on?"),
        )

    with patch('livekit.agents.Agent.default.llm_node', return_value=mock_llm_stream()):
        chunks = []
        async for chunk in agent.llm_node(mock_chat_ctx, [], MagicMock()):
            chunks.append(chunk)

    # Verify:
    # 1. Counter was incremented to 3
    # 2. Recovery context was added to dynamic context
    # 3. LLM was called (not skipped like first 2 silences)
    # 4. Counter was reset after recovery delivered
    assert len(chunks) > 0  # LLM response was yielded

    # Verify recovery context was added to dynamic context
    dynamic_context_calls = agent.phase_manager.get_dynamic_context.call_args_list
    assert len(dynamic_context_calls) == 1

    # Verify add_message was called to add recovery context
    assert mock_chat_ctx.add_message.called

    # Check that recovery instruction was added
    system_calls = [
        call for call in mock_chat_ctx.add_message.call_args_list
        if call[1].get('role') == 'system'
    ]
    # Should have at least one system message with recovery context
    assert len(system_calls) > 0

    # Verify counter was reset to 0 after recovery delivered
    assert agent.interview_session.state.consecutive_silence_count == 0


@pytest.mark.asyncio
async def test_substantive_input_resets_counter():
    """Substantive user input resets consecutive_silence_count to 0."""
    agent = _make_agent()
    agent.interview_session.state.consecutive_silence_count = 2

    # User provides real input
    mock_chat_ctx = _make_chat_ctx_with_message("I think we should use a hash function")

    agent.phase_manager.get_static_system_prompt = MagicMock(return_value="Static prompt")
    agent.phase_manager.get_dynamic_context = MagicMock(return_value="Dynamic context")

    # Mock default LLM node to return a response
    async def mock_llm_stream():
        yield llm.ChatChunk(
            id="test_chunk",
            delta=llm.ChoiceDelta(role="assistant", content="Great! Tell me more about that."),
        )

    with patch('livekit.agents.Agent.default.llm_node', return_value=mock_llm_stream()):
        chunks = []
        async for chunk in agent.llm_node(mock_chat_ctx, [], MagicMock()):
            chunks.append(chunk)

    # Verify counter was reset immediately upon detecting substantive input
    assert agent.interview_session.state.consecutive_silence_count == 0
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_recovery_context_injection():
    """Recovery context is injected into dynamic context when silence limit reached."""
    agent = _make_agent()
    agent.interview_session.state.consecutive_silence_count = 3

    # Simulate third silence (user_text will be empty, but counter already at 3)
    mock_chat_ctx = _make_chat_ctx_with_message("I need help")  # Use real input to trigger context check

    agent.phase_manager.get_static_system_prompt = MagicMock(return_value="Static prompt")
    agent.phase_manager.get_dynamic_context = MagicMock(return_value="Dynamic context")

    # Mock default LLM node
    async def mock_llm_stream():
        yield llm.ChatChunk(
            id="test_chunk",
            delta=llm.ChoiceDelta(role="assistant", content="Let me help you."),
        )

    with patch('livekit.agents.Agent.default.llm_node', return_value=mock_llm_stream()):
        chunks = []
        async for chunk in agent.llm_node(mock_chat_ctx, [], MagicMock()):
            chunks.append(chunk)

    # Verify add_message was called with system context
    system_calls = [
        call for call in mock_chat_ctx.add_message.call_args_list
        if call[1].get('role') == 'system'
    ]

    # Find the call with recovery context
    recovery_found = False
    for call in system_calls:
        content = call[1].get('content', '')
        if 'candidate seems stuck' in content or 'RECOVERY' in content:
            recovery_found = True
            break

    assert recovery_found, "Recovery context should be injected when consecutive_silence_count >= 3"


@pytest.mark.asyncio
async def test_counter_persists_across_turns():
    """consecutive_silence_count persists in SessionState across multiple turns."""
    agent = _make_agent()

    # Turn 1: Empty
    mock_chat_ctx_1 = _make_chat_ctx_with_message("")
    with patch('livekit.agents.Agent.default.llm_node'):
        async for _ in agent.llm_node(mock_chat_ctx_1, [], MagicMock()):
            pass
    assert agent.interview_session.state.consecutive_silence_count == 1

    # Turn 2: Empty
    mock_chat_ctx_2 = _make_chat_ctx_with_message("")
    with patch('livekit.agents.Agent.default.llm_node'):
        async for _ in agent.llm_node(mock_chat_ctx_2, [], MagicMock()):
            pass
    assert agent.interview_session.state.consecutive_silence_count == 2

    # Turn 3: Real input
    mock_chat_ctx_3 = _make_chat_ctx_with_message("Let me think about scalability")
    agent.phase_manager.get_static_system_prompt = MagicMock(return_value="Static")
    agent.phase_manager.get_dynamic_context = MagicMock(return_value="Dynamic")

    async def mock_llm_stream():
        yield llm.ChatChunk(
            id="test",
            delta=llm.ChoiceDelta(role="assistant", content="Good point."),
        )

    with patch('livekit.agents.Agent.default.llm_node', return_value=mock_llm_stream()):
        async for _ in agent.llm_node(mock_chat_ctx_3, [], MagicMock()):
            pass

    # Counter should reset after substantive input
    assert agent.interview_session.state.consecutive_silence_count == 0
