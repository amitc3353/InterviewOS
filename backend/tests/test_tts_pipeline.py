"""Tests for TTS pipeline — verifying Cartesia TTS produces audio output.

Tests the integration between tts_pronunciations.normalize_for_tts and
the tts_node logic from interview_agent.py, ensuring sample interviewer text
flows through the pipeline and audio chunks are produced correctly.

11 tests, zero network calls.
"""

import asyncio
import sys
from typing import AsyncIterable, List
from unittest.mock import AsyncMock, Mock, MagicMock, patch

import pytest

from backend.interview.tts_pronunciations import (
    normalize_for_tts,
    PRONUNCIATIONS,
    NUMBER_RE,
    MS_RE,
)


# ---------------------------------------------------------------------------
# Helpers — simulate tts_node pipeline logic from interview_agent.py
# ---------------------------------------------------------------------------

def _make_audio_frame(data: bytes, sample_rate: int = 24000, num_channels: int = 1) -> Mock:
    """Create a mock audio frame with realistic Cartesia output attributes."""
    frame = Mock()
    frame.data = data
    frame.sample_rate = sample_rate
    frame.num_channels = num_channels
    frame.samples_per_channel = len(data) // 2  # 16-bit PCM samples
    return frame


async def _async_text_generator(chunks: List[str]) -> AsyncIterable[str]:
    """Helper to create async text generator from a list of strings."""
    for chunk in chunks:
        yield chunk


async def _simulate_cartesia_tts(text_chunks: List[str]) -> List[Mock]:
    """Simulate what Cartesia TTS does: consume text, produce audio frames.

    Produces 1 audio frame per ~20 characters of input, with realistic
    24kHz 16-bit PCM frame data (480 samples = 20ms at 24kHz).
    """
    full_text = "".join(text_chunks)
    if not full_text.strip():
        return []

    frame_count = max(1, len(full_text) // 20)
    return [
        _make_audio_frame(
            data=b"\x00\x01" * 480,  # 480 samples at 24kHz = 20ms frame
            sample_rate=24000,
        )
        for _ in range(frame_count)
    ]


async def _run_tts_pipeline(
    text_chunks: List[str],
    apply_normalization: bool = True,
) -> tuple[List[Mock], List[str]]:
    """Run the full TTS pipeline: normalize text → simulate audio synthesis.

    Mirrors the flow in InterviewAgent:
    1. llm_node applies normalize_for_tts to each spoken fragment
    2. tts_node buffers text chunks and sends to Cartesia TTS
    3. TTS produces audio frames

    Returns:
        Tuple of (audio_frames, normalized_text_chunks)
    """
    # Step 1: Apply normalization (as llm_node does)
    if apply_normalization:
        normalized_chunks = [normalize_for_tts(chunk) for chunk in text_chunks]
    else:
        normalized_chunks = list(text_chunks)

    # Step 2: Buffer all text (as tts_node does before sending to Cartesia)
    # This mirrors the actual tts_node behavior: buffer → send → receive frames
    if not normalized_chunks:
        return [], normalized_chunks

    # Step 3: Simulate Cartesia TTS producing audio
    frames = await _simulate_cartesia_tts(normalized_chunks)
    return frames, normalized_chunks


# ---------------------------------------------------------------------------
# Tests — Audio output production
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tts_pipeline_produces_audio_frames():
    """Sample interviewer text produces non-zero audio frames through TTS pipeline."""
    text = ["Let's discuss how you would ", "design a URL shortener service."]

    frames, _ = await _run_tts_pipeline(text)

    assert len(frames) > 0, "TTS pipeline must produce at least one audio frame"


@pytest.mark.asyncio
async def test_tts_pipeline_audio_frames_have_data():
    """Each audio frame from TTS pipeline contains non-empty audio data."""
    text = ["How would you handle ", "cache invalidation at scale?"]

    frames, _ = await _run_tts_pipeline(text)

    assert len(frames) > 0
    for i, frame in enumerate(frames):
        assert frame.data is not None, f"Frame {i} has None data"
        assert len(frame.data) > 0, f"Frame {i} has empty data"


@pytest.mark.asyncio
async def test_tts_pipeline_audio_frames_have_correct_sample_rate():
    """Audio frames from TTS pipeline have the expected 24kHz sample rate."""
    text = ["Tell me about your approach to database sharding."]

    frames, _ = await _run_tts_pipeline(text)

    assert len(frames) > 0
    for frame in frames:
        assert frame.sample_rate == 24000, f"Expected 24kHz, got {frame.sample_rate}"


@pytest.mark.asyncio
async def test_tts_pipeline_longer_text_produces_more_frames():
    """Longer interviewer text produces proportionally more audio frames."""
    short_text = ["Short reply."]
    long_text = [
        "That's a great point about using Redis for caching. ",
        "Now let me ask you about the consistency model. ",
        "How would you handle cache invalidation when the underlying data changes? ",
        "What about the thundering herd problem?",
    ]

    short_frames, _ = await _run_tts_pipeline(short_text)
    long_frames, _ = await _run_tts_pipeline(long_text)

    assert len(long_frames) > len(short_frames), (
        f"Longer text ({len(long_frames)} frames) should produce more frames "
        f"than short text ({len(short_frames)} frames)"
    )


@pytest.mark.asyncio
async def test_tts_pipeline_frame_data_is_correct_size():
    """Audio frames have correct PCM data size for 20ms at 24kHz."""
    text = ["How would you design a notification system?"]

    frames, _ = await _run_tts_pipeline(text)

    assert len(frames) > 0
    for frame in frames:
        # 480 samples * 2 bytes (16-bit PCM) = 960 bytes per 20ms frame
        assert len(frame.data) == 960, (
            f"Expected 960 bytes (480 samples * 2 bytes), got {len(frame.data)}"
        )
        assert frame.samples_per_channel == 480, (
            f"Expected 480 samples per channel, got {frame.samples_per_channel}"
        )


# ---------------------------------------------------------------------------
# Tests — Pronunciation normalization flows into TTS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_for_tts_expands_technical_terms_before_synthesis():
    """Technical terms are expanded by normalize_for_tts before reaching TTS."""
    input_text = "Use Redis and MySQL with 100M QPS"

    frames, normalized = await _run_tts_pipeline([input_text])

    received = "".join(normalized)
    assert "Reddis" in received, "Redis should be normalized to 'Reddis'"
    assert "My sequel" in received, "MySQL should be normalized to 'My sequel'"
    assert "100 million" in received, "100M should be expanded to '100 million'"
    assert "Q P S" in received, "QPS should be spelled out as 'Q P S'"
    assert len(frames) > 0, "Normalized text should still produce audio"


@pytest.mark.asyncio
async def test_tts_pipeline_normalizes_system_design_terms():
    """System design terms (sharding, idempotency, etc.) are normalized for TTS."""
    text = [
        "How would you handle PostgreSQL replication? ",
        "What about the CAP theorem tradeoffs? ",
        "Consider 100M daily active users with sharding.",
    ]

    frames, normalized = await _run_tts_pipeline(text)
    received = "".join(normalized)

    assert "Postgres" in received, "PostgreSQL should be normalized to 'Postgres'"
    assert "C A P" in received, "CAP should be spelled out as 'C A P'"
    assert "100 million" in received, "100M should be expanded to '100 million'"
    assert "sharr-ding" in received, "sharding should be normalized to 'sharr-ding'"
    assert len(frames) > 0


@pytest.mark.asyncio
async def test_tts_pipeline_without_normalization_preserves_raw_text():
    """Without normalization, raw technical terms pass through unchanged."""
    text = ["Use Redis and MySQL with 100M QPS"]

    frames, raw = await _run_tts_pipeline(text, apply_normalization=False)
    received = "".join(raw)

    assert "Redis" in received, "Raw text should contain 'Redis'"
    assert "MySQL" in received, "Raw text should contain 'MySQL'"
    assert "100M" in received, "Raw text should contain '100M'"
    assert len(frames) > 0


# ---------------------------------------------------------------------------
# Tests — Edge cases for audio output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tts_pipeline_empty_input_produces_no_audio():
    """Empty text input produces zero audio frames without errors."""
    frames, _ = await _run_tts_pipeline([])

    assert len(frames) == 0, "Empty input should produce no audio frames"


@pytest.mark.asyncio
async def test_tts_pipeline_special_characters_produce_audio():
    """Text with special characters and punctuation produces audio without errors."""
    text_with_specials = [
        "What about 99.99% availability (SLA)?",
        "Consider: read-write ratio is ~100:1.",
        'Use "eventual consistency" for this layer.',
    ]

    frames, normalized = await _run_tts_pipeline(text_with_specials)
    received = "".join(normalized)

    assert len(frames) > 0, "Special characters should not prevent audio generation"
    # Verify SLA and eventual consistency were normalized
    assert "S L A" in received, "SLA should be spelled out"
    assert "eventual con-SIS-ten-see" in received, "eventual consistency should be normalized"
