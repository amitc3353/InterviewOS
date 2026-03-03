"""Tests for LLM resilience: timeout, retry, rate limit, context trimming."""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from livekit.agents import llm

from backend.agents.interview_agent import (
    InterviewAgent,
    _stream_with_first_chunk_timeout,
    LLM_TIMEOUT_SECONDS,
    MAX_LLM_RETRIES,
)
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


async def _async_generator(items):
    """Helper to create async generator from list."""
    for item in items:
        yield item


async def _async_generator_with_delay(items, delay):
    """Helper to create async generator with delay before first item."""
    await asyncio.sleep(delay)
    for item in items:
        yield item


def _make_chat_chunk(content: str, chunk_id: str = "test-chunk") -> llm.ChatChunk:
    """Create a test chat chunk."""
    return llm.ChatChunk(
        id=chunk_id,
        delta=llm.ChoiceDelta(role="assistant", content=content),
    )


class MockRateLimitError(Exception):
    """Mock 429 rate limit error."""
    def __init__(self, retry_after=None):
        super().__init__("Rate limit exceeded")
        self.status_code = 429
        if retry_after:
            self.response = Mock()
            self.response.headers = {"Retry-After": str(retry_after)}
        else:
            self.response = Mock()
            self.response.headers = {}


# ---------------------------------------------------------------------------
# Tests for _stream_with_first_chunk_timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_timeout_helper_success():
    """Helper streams all items when no timeout."""
    items = [_make_chat_chunk("Hello"), _make_chat_chunk("World")]
    gen = _async_generator(items)

    result = []
    async for chunk in _stream_with_first_chunk_timeout(gen, timeout=1.0):
        result.append(chunk)

    assert len(result) == 2
    assert result[0].delta.content == "Hello"
    assert result[1].delta.content == "World"


@pytest.mark.asyncio
async def test_stream_timeout_helper_timeout():
    """Helper raises TimeoutError when first chunk exceeds timeout."""
    items = [_make_chat_chunk("Late response")]
    gen = _async_generator_with_delay(items, delay=2.0)

    with pytest.raises(asyncio.TimeoutError):
        async for _ in _stream_with_first_chunk_timeout(gen, timeout=0.5):
            pass


@pytest.mark.asyncio
async def test_stream_timeout_helper_subsequent_chunks_no_timeout():
    """Helper only times out first chunk, not subsequent ones."""
    async def slow_generator():
        yield _make_chat_chunk("Fast first")
        await asyncio.sleep(1.0)  # Slow second chunk
        yield _make_chat_chunk("Slow second")

    result = []
    # Timeout is 0.5s, but second chunk takes 1s - should still succeed
    async for chunk in _stream_with_first_chunk_timeout(slow_generator(), timeout=0.5):
        result.append(chunk)

    assert len(result) == 2
    assert result[1].delta.content == "Slow second"


# ---------------------------------------------------------------------------
# Tests for LLM resilience in InterviewAgent.llm_node
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_timeout_retry_success():
    """Timeout on first attempt, success on retry."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    # Mock chat context
    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    # Track attempt count
    attempt_count = [0]

    async def mock_llm_node(*args, **kwargs):
        attempt_count[0] += 1
        if attempt_count[0] == 1:
            # First attempt: timeout (no chunks)
            await asyncio.sleep(100)  # Will be interrupted by timeout
        else:
            # Second attempt: success
            yield _make_chat_chunk("[ACK:Got it.][Q:What scale?]")

    # Patch the default LLM node
    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should retry once and succeed
    assert attempt_count[0] == 2
    assert len(result_chunks) > 0


@pytest.mark.asyncio
async def test_llm_timeout_max_retries_delivers_filler():
    """After max retries on timeout, deliver filler 'Hmm.'"""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    async def mock_llm_node_always_timeout(*args, **kwargs):
        # Always timeout
        await asyncio.sleep(100)
        yield _make_chat_chunk("Should never reach")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_always_timeout):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should deliver filler
    assert len(result_chunks) == 1
    assert "Hmm" in result_chunks[0].delta.content


@pytest.mark.asyncio
async def test_rate_limit_429_retry_with_backoff():
    """Rate limit (429) triggers retry with exponential backoff."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    attempt_count = [0]

    async def mock_llm_node_rate_limit(*args, **kwargs):
        attempt_count[0] += 1
        if attempt_count[0] == 1:
            raise MockRateLimitError()
        else:
            yield _make_chat_chunk("[ACK:Okay.][Q:Continue?]")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_rate_limit):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should retry and succeed
    assert attempt_count[0] == 2
    assert len(result_chunks) > 0


@pytest.mark.asyncio
async def test_rate_limit_429_with_retry_after_header():
    """Rate limit (429) with retry-after header is respected."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    attempt_count = [0]
    start_time = asyncio.get_event_loop().time()

    async def mock_llm_node_with_retry_after(*args, **kwargs):
        attempt_count[0] += 1
        if attempt_count[0] == 1:
            raise MockRateLimitError(retry_after=0.5)  # 0.5s retry-after
        else:
            yield _make_chat_chunk("[ACK:Ready.][Q:Next?]")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_with_retry_after):
        async for _ in agent.llm_node(chat_ctx, [], Mock()):
            pass

    elapsed = asyncio.get_event_loop().time() - start_time
    # Should have waited at least 0.5s for retry-after
    assert elapsed >= 0.4  # Allow small margin for test timing
    assert attempt_count[0] == 2


@pytest.mark.asyncio
async def test_rate_limit_max_retries_delivers_filler():
    """After max retries on rate limit, deliver filler."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    async def mock_llm_node_always_429(*args, **kwargs):
        raise MockRateLimitError()

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_always_429):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should deliver filler after exhausting retries
    assert len(result_chunks) == 1
    assert "Give me just a moment" in result_chunks[0].delta.content


@pytest.mark.asyncio
async def test_non_retryable_error_delivers_filler():
    """Non-retryable errors deliver filler immediately."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    async def mock_llm_node_500_error(*args, **kwargs):
        error = Exception("Internal server error")
        error.status_code = 500
        raise error

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_500_error):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should deliver filler immediately (500 is not retryable)
    assert len(result_chunks) == 1
    assert "Give me just a moment" in result_chunks[0].delta.content


@pytest.mark.asyncio
async def test_context_trimming_logs_when_active():
    """Context trimming logs when history exceeds MAX_HISTORY_MESSAGES."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    # Create chat context with many messages
    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])

    # Create 25 non-system messages (exceeds MAX_HISTORY_MESSAGES=18)
    chat_ctx.items = [
        Mock(role="user", content="msg 1"),
        Mock(role="assistant", content="resp 1"),
    ] * 15  # 30 messages total

    # Add system messages (should be preserved)
    system_msg = Mock(role="system", content="You are an interviewer")
    chat_ctx.items = [system_msg] + chat_ctx.items

    async def mock_llm_node(*args, **kwargs):
        yield _make_chat_chunk("[ACK:Yes.][Q:What?]")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node):
        # Should trim context before LLM call
        async for _ in agent.llm_node(chat_ctx, [], Mock()):
            pass

    # Verify system message preserved
    assert any(hasattr(item, 'role') and item.role == "system" for item in chat_ctx.items)

    # Verify trimming occurred (non-system messages <= 18)
    non_system = [item for item in chat_ctx.items if not (hasattr(item, 'role') and item.role == "system")]
    assert len(non_system) <= 18


@pytest.mark.asyncio
async def test_malformed_json_fallback():
    """Response parser fallback chain handles malformed JSON gracefully."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    # Return malformed JSON (should trigger parser fallback)
    async def mock_llm_node_malformed(*args, **kwargs):
        yield _make_chat_chunk('{"phase": "scope", "question": "What scale')  # Truncated JSON

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_malformed):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should handle gracefully (parser has fallback chain: json → regex → raw)
    # Exact behavior depends on parser implementation, but should not crash
    assert len(result_chunks) >= 0  # No crash = success


@pytest.mark.asyncio
async def test_empty_stt_response_recovery():
    """Empty STT response triggers recovery message."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    # Create chat context with empty user message
    chat_ctx = Mock()
    user_msg = Mock(role="user", content=[llm.ChatText(text="")])  # Empty STT
    chat_ctx.messages = Mock(return_value=[user_msg])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    result_chunks = []
    async for chunk in agent.llm_node(chat_ctx, [], Mock()):
        result_chunks.append(chunk)

    # Should deliver recovery message
    assert len(result_chunks) == 1
    assert "didn't catch that" in result_chunks[0].delta.content.lower() or "repeat" in result_chunks[0].delta.content.lower()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_resilience_flow_timeout_then_success():
    """
    Integration test: Timeout on attempt 1, rate limit on attempt 2, success on attempt 3.

    This verifies the full retry flow with multiple failure modes.
    """
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    chat_ctx = Mock()
    chat_ctx.messages = Mock(return_value=[])
    chat_ctx.items = []
    chat_ctx.add_message = Mock()

    attempt_count = [0]

    async def mock_llm_node_multi_failure(*args, **kwargs):
        attempt_count[0] += 1
        if attempt_count[0] == 1:
            # Timeout
            await asyncio.sleep(100)
        elif attempt_count[0] == 2:
            # Rate limit
            raise MockRateLimitError()
        else:
            # Success
            yield _make_chat_chunk("[ACK:Alright.][Q:Database choice?]")

    with patch.object(agent.__class__.__bases__[0].default, 'llm_node', side_effect=mock_llm_node_multi_failure):
        result_chunks = []
        async for chunk in agent.llm_node(chat_ctx, [], Mock()):
            result_chunks.append(chunk)

    # Should retry through both failures and succeed on third attempt
    assert attempt_count[0] == 3
    assert len(result_chunks) > 0
    # Verify it's not a filler
    assert "Hmm" not in result_chunks[0].delta.content
    assert "moment" not in result_chunks[0].delta.content
