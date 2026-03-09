"""Tests for InterviewAgent empty LLM response retry with fallback prompt."""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from livekit.agents import llm

from backend.agents.interview_agent import InterviewAgent
from backend.config import AgentConfig


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


def _make_chat_ctx():
    """Create a mock chat context with a user message (prevents silence handler)."""
    chat_ctx = Mock()
    user_msg = Mock()
    user_msg.role = "user"
    user_msg.content = ["I would use a distributed hash map for the cache layer"]
    chat_ctx.messages = Mock(return_value=[user_msg])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()
    return chat_ctx


# ---------------------------------------------------------------------------
# Tests for empty LLM response retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_llm_response_triggers_retry():
    """Empty LLM response triggers retry with fallback prompt."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = _make_chat_ctx()

    # Track LLM call count
    call_count = [0]

    async def mock_llm_node(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: return empty response (only internal tags, no spoken text)
            yield _make_chat_chunk("[PHASE:scope]")
        else:
            # Second call (retry): return valid spoken text
            yield _make_chat_chunk("[ACK:Got it.][Q:What scale?]")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should have called LLM twice (initial + retry)
    assert call_count[0] == 2

    # Should have added fallback prompt to chat context
    add_message_calls = [call for call in chat_ctx.add_message.call_args_list
                         if len(call[1]) > 0 and call[1].get('role') == 'system']
    assert any('You must provide a spoken response' in str(call) for call in add_message_calls)

    # Should have yielded chunks from retry
    assert len(result_chunks) > 0


@pytest.mark.asyncio
async def test_empty_llm_response_retry_success():
    """Retry success returns spoken_text from retry response."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = _make_chat_ctx()

    call_count = [0]

    async def mock_llm_node(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: empty spoken text
            yield _make_chat_chunk("[LISTEN]")  # Internal tag only, no spoken text
        else:
            # Retry: valid spoken response
            yield _make_chat_chunk("[ACK:I understand.][Q:What's the traffic pattern?]")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should retry once
    assert call_count[0] == 2

    # Should have received spoken text from retry
    assert len(result_chunks) > 0

    # Concatenate all chunk content
    full_content = ""
    for chunk in result_chunks:
        if chunk.delta and chunk.delta.content:
            full_content += chunk.delta.content

    # Should contain the retry response text
    assert len(full_content) > 0
    assert "understand" in full_content.lower() or "traffic" in full_content.lower()

    # Verify the assistant message was recorded
    assert len(agent.interview_session.state.conversation_history) > 0
    last_msg = agent.interview_session.state.conversation_history[-1]
    assert last_msg.role == "assistant"
    assert len(last_msg.content) > 0


@pytest.mark.asyncio
async def test_empty_llm_response_retry_fails_uses_hardcoded_fallback():
    """Retry fails (still empty) uses hardcoded fallback 'Could you elaborate on that?'"""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = _make_chat_ctx()

    call_count = [0]

    async def mock_llm_node_always_empty(*args, **kwargs):
        call_count[0] += 1
        # Both initial and retry return empty spoken text
        yield _make_chat_chunk("[PHASE:scope]")  # No spoken text

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_always_empty):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should have called LLM twice (initial + retry)
    assert call_count[0] == 2

    # Should have delivered hardcoded fallback
    assert len(result_chunks) > 0

    # Check for hardcoded fallback text
    full_content = ""
    for chunk in result_chunks:
        if chunk.delta and chunk.delta.content:
            full_content += chunk.delta.content

    assert "Could you elaborate on that?" in full_content

    # Verify fallback was recorded in history
    assert len(agent.interview_session.state.conversation_history) > 0
    last_msg = agent.interview_session.state.conversation_history[-1]
    assert last_msg.role == "assistant"
    assert "Could you elaborate on that?" in last_msg.content


@pytest.mark.asyncio
async def test_empty_llm_response_retry_timeout_uses_fallback():
    """Retry timeout uses hardcoded fallback."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = _make_chat_ctx()

    call_count = [0]

    async def mock_llm_node_with_timeout(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: empty response
            yield _make_chat_chunk("[PHASE:scope]")
        else:
            # Retry: timeout (sleep longer than 5s timeout)
            await asyncio.sleep(100)
            yield _make_chat_chunk("[ACK:Should never reach]")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_with_timeout):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should have attempted retry
    assert call_count[0] == 2

    # Should have delivered hardcoded fallback due to timeout
    assert len(result_chunks) > 0

    full_content = ""
    for chunk in result_chunks:
        if chunk.delta and chunk.delta.content:
            full_content += chunk.delta.content

    assert "Could you elaborate on that?" in full_content


@pytest.mark.asyncio
async def test_empty_llm_response_retry_error_uses_fallback():
    """Retry error uses hardcoded fallback."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = _make_chat_ctx()

    call_count = [0]

    async def mock_llm_node_with_error(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: empty response
            yield _make_chat_chunk("[LISTEN]")
        else:
            # Retry: raises error
            raise Exception("API error")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_with_error):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should have attempted retry
    assert call_count[0] == 2

    # Should have delivered hardcoded fallback
    assert len(result_chunks) > 0

    full_content = ""
    for chunk in result_chunks:
        if chunk.delta and chunk.delta.content:
            full_content += chunk.delta.content

    assert "Could you elaborate on that?" in full_content


@pytest.mark.asyncio
async def test_non_empty_llm_response_no_retry():
    """Non-empty LLM response does not trigger retry."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = _make_chat_ctx()

    call_count = [0]

    async def mock_llm_node_valid(*args, **kwargs):
        call_count[0] += 1
        # Return valid spoken text on first call
        yield _make_chat_chunk("[ACK:Sounds good.][Q:What's the expected QPS?]")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_valid):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should only call LLM once (no retry needed)
    assert call_count[0] == 1

    # Should have yielded chunks
    assert len(result_chunks) > 0

    # Verify spoken text was recorded
    assert len(agent.interview_session.state.conversation_history) > 0
    last_msg = agent.interview_session.state.conversation_history[-1]
    assert last_msg.role == "assistant"
    assert len(last_msg.content) > 0
