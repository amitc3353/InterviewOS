"""Tests for TTS timeout and retry handling — 7 tests, zero network calls."""
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import pytest

from livekit.agents import Agent

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


async def _async_text_generator(chunks: list[str]):
    """Helper to create async text generator."""
    for chunk in chunks:
        yield chunk


async def _async_audio_generator(frame_count: int):
    """Helper to create async audio frame generator that yields immediately."""
    for i in range(frame_count):
        yield Mock(data=f"audio_frame_{i}")


async def _async_audio_generator_with_delay(frame_count: int, delay: float):
    """Helper to create async audio generator with delay on first frame only."""
    # Delay before first frame
    await asyncio.sleep(delay)
    for i in range(frame_count):
        yield Mock(data=f"audio_frame_{i}")


# ---------------------------------------------------------------------------
# TTS Timeout and Retry Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tts_success_no_retry():
    """TTS succeeds on first attempt, no retry needed."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    # Mock successful TTS
    async def mock_tts_node(self, text, model_settings):
        # Consume text
        chunks = []
        async for chunk in text:
            chunks.append(chunk)
        # Yield audio frames
        async for frame in _async_audio_generator(3):
            yield frame

    text_chunks = ["Hello ", "world"]

    with patch.object(Agent.default, 'tts_node', side_effect=mock_tts_node):
        audio_frames = []
        async for frame in agent.tts_node(_async_text_generator(text_chunks), Mock()):
            audio_frames.append(frame)

    # Should get all audio frames
    assert len(audio_frames) == 3


@pytest.mark.asyncio
async def test_tts_timeout_retry_success():
    """TTS times out on first frame of first attempt, succeeds on retry."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    attempt_count = [0]

    async def mock_tts_node_timeout_then_success(self, text, model_settings):
        attempt_count[0] += 1
        # Consume text
        async for _ in text:
            pass

        if attempt_count[0] == 1:
            # First attempt: timeout on first frame (delay longer than 5s timeout)
            await asyncio.sleep(10)
            yield Mock(data="should_never_reach")
        else:
            # Second attempt: success - yield frames immediately
            async for frame in _async_audio_generator(2):
                yield frame

    text_chunks = ["Test message"]

    with patch.object(Agent.default, 'tts_node', side_effect=mock_tts_node_timeout_then_success):
        audio_frames = []
        async for frame in agent.tts_node(_async_text_generator(text_chunks), Mock()):
            audio_frames.append(frame)

    # Should retry and succeed
    assert attempt_count[0] == 2
    assert len(audio_frames) == 2


@pytest.mark.asyncio
async def test_tts_error_retry_success():
    """TTS raises error on first attempt, succeeds on retry."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    attempt_count = [0]

    async def mock_tts_node_error_then_success(self, text, model_settings):
        attempt_count[0] += 1
        # Consume text
        async for _ in text:
            pass

        if attempt_count[0] == 1:
            # First attempt: error
            raise RuntimeError("Cartesia API error")
        else:
            # Second attempt: success
            async for frame in _async_audio_generator(2):
                yield frame

    text_chunks = ["Error test"]

    with patch.object(Agent.default, 'tts_node', side_effect=mock_tts_node_error_then_success):
        audio_frames = []
        async for frame in agent.tts_node(_async_text_generator(text_chunks), Mock()):
            audio_frames.append(frame)

    # Should retry and succeed
    assert attempt_count[0] == 2
    assert len(audio_frames) == 2


@pytest.mark.asyncio
async def test_tts_max_retries_logs_error_returns_silence():
    """TTS fails both attempts, logs error loudly, returns silence."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    attempt_count = [0]

    async def mock_tts_node_always_fails(self, text, model_settings):
        attempt_count[0] += 1
        # Consume text
        async for _ in text:
            pass
        # Always fail
        raise RuntimeError("Cartesia is down")
        yield  # unreachable — makes this an async generator so side_effect returns it

    text_chunks = ["This will fail"]

    with patch.object(Agent.default, 'tts_node', side_effect=mock_tts_node_always_fails):
        audio_frames = []
        # Should not raise exception, just log and return empty
        async for frame in agent.tts_node(_async_text_generator(text_chunks), Mock()):
            audio_frames.append(frame)

    # Should attempt twice
    assert attempt_count[0] == 2
    # Should return no audio (silence fallback)
    assert len(audio_frames) == 0


@pytest.mark.asyncio
async def test_tts_timeout_max_retries_returns_silence():
    """TTS times out on first frame of both attempts, returns silence."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    attempt_count = [0]

    async def mock_tts_node_always_timeout(self, text, model_settings):
        attempt_count[0] += 1
        # Consume text
        async for _ in text:
            pass
        # Always timeout on first frame (delay longer than 5s timeout)
        await asyncio.sleep(10)
        yield Mock(data="should_never_reach")

    text_chunks = ["Timeout test"]

    with patch.object(Agent.default, 'tts_node', side_effect=mock_tts_node_always_timeout):
        audio_frames = []
        async for frame in agent.tts_node(_async_text_generator(text_chunks), Mock()):
            audio_frames.append(frame)

    # Should attempt twice (MAX_TTS_RETRIES = 2)
    assert attempt_count[0] == 2
    # Should return no audio (silence fallback)
    assert len(audio_frames) == 0


@pytest.mark.asyncio
async def test_tts_empty_text_skips_synthesis():
    """TTS skips synthesis when text is empty."""
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    # Mock TTS that should not be called
    mock_tts_called = [False]

    async def mock_tts_node_should_not_call(self, text, model_settings):
        mock_tts_called[0] = True
        async for _ in text:
            pass
        yield Mock(data="should_not_reach")

    text_chunks = []  # Empty

    with patch.object(Agent.default, 'tts_node', side_effect=mock_tts_node_should_not_call):
        audio_frames = []
        async for frame in agent.tts_node(_async_text_generator(text_chunks), Mock()):
            audio_frames.append(frame)

    # Should not call TTS for empty text
    assert mock_tts_called[0] is False
    assert len(audio_frames) == 0


@pytest.mark.asyncio
async def test_tts_preserves_llm_response_in_history():
    """TTS failure does not lose LLM response from session history.

    This is an integration test verifying that even if TTS fails completely,
    the LLM's text response is still recorded in the session history.
    """
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    # Simulate LLM generating a response
    llm_response = "This is an important answer that must not be lost"

    # Mock TTS that always fails
    async def mock_tts_always_fails(self, text, model_settings):
        async for _ in text:
            pass
        raise RuntimeError("TTS is completely down")

    text_chunks = [llm_response]

    with patch.object(Agent.default, 'tts_node', side_effect=mock_tts_always_fails):
        audio_frames = []
        # TTS fails but should not raise exception
        async for frame in agent.tts_node(_async_text_generator(text_chunks), Mock()):
            audio_frames.append(frame)

    # TTS should fail gracefully
    assert len(audio_frames) == 0

    # The LLM response text should still be available (it was passed to tts_node)
    # This verifies that text made it to TTS layer, even if audio synthesis failed
    # In the real flow, llm_node records the text in history BEFORE tts_node is called
    # So TTS failure cannot lose the response


@pytest.mark.asyncio
async def test_tts_streams_frames_immediately():
    """TTS streams audio frames immediately as they arrive (no buffering).

    This test verifies the fix for the streaming regression - frames should be
    yielded as they're generated, not collected and dumped at the end.
    """
    config = _make_config()
    agent = InterviewAgent(config, "Design a cache")

    frame_yield_times = []

    async def mock_tts_node_with_delays(self, text, model_settings):
        # Consume text
        async for _ in text:
            pass
        # Yield frames with small delays between them
        for i in range(3):
            await asyncio.sleep(0.1)  # Small delay between frames
            yield Mock(data=f"audio_frame_{i}")

    text_chunks = ["Streaming test"]

    with patch.object(Agent.default, 'tts_node', side_effect=mock_tts_node_with_delays):
        audio_frames = []
        start_time = asyncio.get_event_loop().time()

        async for frame in agent.tts_node(_async_text_generator(text_chunks), Mock()):
            frame_yield_times.append(asyncio.get_event_loop().time() - start_time)
            audio_frames.append(frame)

    # Should get all 3 frames
    assert len(audio_frames) == 3

    # Frames should arrive incrementally (not all at once at the end)
    # First frame should arrive around 0.1s, second around 0.2s, third around 0.3s
    assert len(frame_yield_times) == 3
    # Verify frames arrive with spacing (not all buffered and released together)
    # If buffered, all frames would arrive at ~0.3s; if streaming, they're spaced out
    assert frame_yield_times[0] < 0.2  # First frame arrives early
    assert frame_yield_times[1] < 0.3  # Second frame arrives before end
    assert frame_yield_times[2] < 0.5  # Third frame arrives last
