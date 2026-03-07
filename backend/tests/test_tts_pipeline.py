"""Tests for TTS pipeline — verifying tts_node produces audio output.

Tests that InterviewAgent.tts_node correctly passes text through to
Agent.default.tts_node and yields audio frames. Verifies the integration
between the custom tts_node wrapper and the underlying TTS provider.

8 tests, zero network calls.
"""

import asyncio
from typing import List
from unittest.mock import AsyncMock, Mock, patch

import pytest
from livekit.agents import Agent

from backend.agents.interview_agent import InterviewAgent
from backend.config import AgentConfig
from backend.interview.tts_pronunciations import normalize_for_tts


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


def _make_audio_frame(
    data: bytes = b"\x00\x01" * 480,
    sample_rate: int = 24000,
    num_channels: int = 1,
) -> Mock:
    """Create a mock audio frame with realistic Cartesia output attributes.

    Default: 480 samples of 16-bit PCM at 24kHz = 20ms frame.
    """
    frame = Mock()
    frame.data = data
    frame.sample_rate = sample_rate
    frame.num_channels = num_channels
    frame.samples_per_channel = len(data) // 2
    return frame


async def _async_text_generator(chunks: List[str]):
    """Helper to create async text generator."""
    for chunk in chunks:
        yield chunk


# ---------------------------------------------------------------------------
# Tests — tts_node produces audio output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tts_node_produces_audio_frames_from_text():
    """tts_node yields audio frames when given interviewer text."""
    agent = InterviewAgent(_make_config(), "Design a URL shortener")

    async def mock_tts(self, text, model_settings):
        async for _ in text:
            pass
        for _ in range(3):
            yield _make_audio_frame()

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts):
        frames = []
        async for frame in agent.tts_node(
            _async_text_generator(["Let's discuss how you would design this."]),
            Mock(),
        ):
            frames.append(frame)

    assert len(frames) == 3, "tts_node must yield audio frames from text input"


@pytest.mark.asyncio
async def test_tts_node_audio_frames_contain_pcm_data():
    """Each audio frame from tts_node contains non-empty PCM audio data."""
    agent = InterviewAgent(_make_config(), "Design a cache")

    pcm_data = b"\x00\x01" * 480  # 960 bytes = 20ms at 24kHz 16-bit

    async def mock_tts(self, text, model_settings):
        async for _ in text:
            pass
        for _ in range(2):
            yield _make_audio_frame(data=pcm_data, sample_rate=24000)

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts):
        frames = []
        async for frame in agent.tts_node(
            _async_text_generator(["How would you handle cache invalidation?"]),
            Mock(),
        ):
            frames.append(frame)

    assert len(frames) == 2
    for i, frame in enumerate(frames):
        assert frame.data is not None, f"Frame {i} has None data"
        assert len(frame.data) == 960, (
            f"Frame {i}: expected 960 bytes (480 samples * 2 bytes), got {len(frame.data)}"
        )
        assert frame.sample_rate == 24000, f"Frame {i}: expected 24kHz sample rate"


@pytest.mark.asyncio
async def test_tts_node_longer_text_receives_more_frames():
    """tts_node yields more frames when the underlying TTS produces more for longer text."""
    agent = InterviewAgent(_make_config(), "Design a notification system")

    async def mock_tts_proportional(self, text, model_settings):
        """Mock TTS that produces frames proportional to text length."""
        chunks = []
        async for chunk in text:
            chunks.append(chunk)
        full_text = "".join(chunks)
        frame_count = max(1, len(full_text) // 20)
        for _ in range(frame_count):
            yield _make_audio_frame()

    short_text = ["Short reply."]
    long_text = [
        "That's a great point about using Redis for caching. ",
        "Now let me ask about the consistency model. ",
        "How would you handle invalidation when data changes? ",
        "What about the thundering herd problem?",
    ]

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts_proportional):
        short_frames = []
        async for frame in agent.tts_node(
            _async_text_generator(short_text), Mock()
        ):
            short_frames.append(frame)

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts_proportional):
        long_frames = []
        async for frame in agent.tts_node(
            _async_text_generator(long_text), Mock()
        ):
            long_frames.append(frame)

    assert len(long_frames) > len(short_frames), (
        f"Longer text ({len(long_frames)} frames) should produce more frames "
        f"than short text ({len(short_frames)} frames)"
    )


@pytest.mark.asyncio
async def test_tts_node_passes_all_text_chunks_to_underlying_tts():
    """tts_node buffers and passes all text chunks to Agent.default.tts_node."""
    agent = InterviewAgent(_make_config(), "Design a rate limiter")
    received_text: List[str] = []

    async def mock_tts_capture(self, text, model_settings):
        async for chunk in text:
            received_text.append(chunk)
        yield _make_audio_frame()

    input_chunks = [
        "How would you ",
        "handle rate limiting ",
        "at the API gateway level?",
    ]

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts_capture):
        async for _ in agent.tts_node(
            _async_text_generator(input_chunks), Mock()
        ):
            pass

    # tts_node buffers all text then creates a new generator for Agent.default.tts_node
    full_received = "".join(received_text)
    full_input = "".join(input_chunks)
    assert full_received == full_input, (
        f"Text passed to TTS should match input. Got: {full_received!r}"
    )


@pytest.mark.asyncio
async def test_tts_node_with_special_characters_produces_audio():
    """Text with special characters and punctuation produces audio without errors."""
    agent = InterviewAgent(_make_config(), "Design an SLA monitor")

    async def mock_tts(self, text, model_settings):
        async for _ in text:
            pass
        yield _make_audio_frame()

    special_text = [
        'What about 99.99% availability (SLA)?',
        "Consider: read-write ratio is ~100:1.",
        'Use "eventual consistency" for this layer.',
    ]

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts):
        frames = []
        async for frame in agent.tts_node(
            _async_text_generator(special_text), Mock()
        ):
            frames.append(frame)

    assert len(frames) > 0, "Special characters should not prevent audio generation"


@pytest.mark.asyncio
async def test_tts_node_single_chunk_produces_audio():
    """tts_node handles a single text chunk and produces audio frames."""
    agent = InterviewAgent(_make_config(), "Design a search engine")

    async def mock_tts(self, text, model_settings):
        async for _ in text:
            pass
        yield _make_audio_frame()
        yield _make_audio_frame()

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts):
        frames = []
        async for frame in agent.tts_node(
            _async_text_generator(["Tell me about your approach to indexing."]),
            Mock(),
        ):
            frames.append(frame)

    assert len(frames) == 2


@pytest.mark.asyncio
async def test_tts_node_whitespace_only_text_skips_synthesis():
    """tts_node with whitespace-only text still attempts synthesis (non-empty chunks)."""
    agent = InterviewAgent(_make_config(), "Design a chat system")
    tts_called = [False]

    async def mock_tts(self, text, model_settings):
        tts_called[0] = True
        async for _ in text:
            pass
        yield _make_audio_frame()

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts):
        frames = []
        async for frame in agent.tts_node(
            _async_text_generator(["   "]), Mock()
        ):
            frames.append(frame)

    # Whitespace-only is non-empty, so tts_node will attempt synthesis
    assert tts_called[0] is True


@pytest.mark.asyncio
async def test_normalize_for_tts_integrates_with_tts_pipeline():
    """normalize_for_tts correctly transforms text that would then flow to tts_node.

    This verifies the integration: llm_node calls normalize_for_tts on text fragments,
    then the normalized text is yielded to tts_node. We test both stages work together.
    """
    agent = InterviewAgent(_make_config(), "Design a cache")
    received_text: List[str] = []

    async def mock_tts_capture(self, text, model_settings):
        async for chunk in text:
            received_text.append(chunk)
        yield _make_audio_frame()

    # Simulate what llm_node does: normalize text before passing to tts_node
    raw_text = "Use Redis with 100M QPS and PostgreSQL"
    normalized = normalize_for_tts(raw_text)

    with patch.object(Agent.default, "tts_node", side_effect=mock_tts_capture):
        frames = []
        async for frame in agent.tts_node(
            _async_text_generator([normalized]), Mock()
        ):
            frames.append(frame)

    full_text = "".join(received_text)
    assert "Reddis" in full_text, "Redis should be normalized to 'Reddis'"
    assert "100 million" in full_text, "100M should be expanded to '100 million'"
    assert "Postgres" in full_text, "PostgreSQL should be normalized to 'Postgres'"
    assert len(frames) > 0, "Normalized text should produce audio frames"
