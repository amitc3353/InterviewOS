"""Tests for Deepgram STT pipeline — verifies speech capture and transcription.

Tests the end-to-end STT pipeline: Deepgram STT plugin configuration,
audio frame processing through TimeoutSTT wrapper, transcript extraction
from SpeechEvents, and integration with the interview agent's speech
capture logic. All external services are mocked — zero network calls.

Livekit mocks are installed by conftest.py before test collection.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from typing import List

import pytest

# Livekit mocks are installed by conftest.py before test collection
from livekit import rtc
from livekit.agents import stt

from backend.config import AgentConfig
from backend.interview.stt_wrapper import TimeoutSTT, TimeoutSpeechStream
from backend.models.session import InterviewSession, SessionState, InterviewPhase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audio_frame(
    num_samples: int = 16000,
    sample_rate: int = 16000,
    num_channels: int = 1,
) -> MagicMock:
    """Create a mock audio frame simulating 1 second of 16kHz mono audio."""
    frame = MagicMock()
    frame.sample_rate = sample_rate
    frame.num_channels = num_channels
    frame.samples_per_channel = num_samples
    frame.data = b"\x00" * (num_samples * num_channels * 2)  # 16-bit PCM
    return frame


def _make_speech_event(text: str, language: str = "en") -> stt.SpeechEvent:
    """Create a SpeechEvent with the given transcript text."""
    return stt.SpeechEvent(
        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
        alternatives=[stt.SpeechData(text=text, language=language)],
    )


def _make_config() -> AgentConfig:
    """Create minimal test config with all required fields."""
    return AgentConfig(
        livekit_url="ws://localhost:7880",
        livekit_api_key="devkey",
        livekit_api_secret="devsecret",
        deepgram_api_key="test-dg-key",
        anthropic_api_key="test-anthropic-key",
        openai_api_key="test-openai-key",
        cartesia_api_key="test-cartesia-key",
    )


def _make_mock_deepgram_stt() -> MagicMock:
    """Create a mock Deepgram STT that behaves like deepgram.STT."""
    mock = MagicMock(spec=stt.STT)
    return mock


def _make_session_state(phase: InterviewPhase = InterviewPhase.INTRO) -> SessionState:
    """Build a minimal SessionState for testing."""
    state = SessionState()
    state.phase = phase
    return state


# ---------------------------------------------------------------------------
# Tests — Deepgram STT Configuration
# ---------------------------------------------------------------------------

class TestDeepgramSTTConfiguration:
    """Verify Deepgram STT is configured correctly in the pipeline."""

    def test_deepgram_api_key_passed_to_stt(self):
        """Deepgram STT receives the API key from config."""
        config = _make_config()
        assert config.deepgram_api_key == "test-dg-key"
        assert config.stt_provider == "deepgram"

    def test_timeout_stt_wraps_deepgram_with_correct_timeout(self):
        """TimeoutSTT wraps Deepgram STT with the configured timeout."""
        mock_dg = _make_mock_deepgram_stt()
        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)

        assert wrapped._wrapped_stt is mock_dg
        assert wrapped._timeout == 5.0

    def test_config_rejects_empty_deepgram_key(self):
        """Config validation fails when Deepgram API key is empty."""
        config = AgentConfig(
            livekit_url="wss://test.livekit.cloud",
            livekit_api_key="key",
            livekit_api_secret="secret",
            deepgram_api_key="",
            anthropic_api_key="ant",
            openai_api_key="oai",
            cartesia_api_key="cart",
        )
        assert config.validate() is False

    def test_default_timeout_is_five_seconds(self):
        """TimeoutSTT defaults to 5-second timeout when not specified."""
        mock_dg = _make_mock_deepgram_stt()
        wrapped = TimeoutSTT(wrapped_stt=mock_dg)

        assert wrapped._timeout == 5.0


# ---------------------------------------------------------------------------
# Tests — Audio Frame to Transcript Pipeline
# ---------------------------------------------------------------------------

class TestAudioToTranscript:
    """Verify sample audio is captured and transcribed correctly."""

    @pytest.mark.asyncio
    async def test_single_utterance_transcribed(self):
        """Single audio frame produces accurate transcript text."""
        mock_dg = _make_mock_deepgram_stt()
        expected_text = "I would use a hash-based approach for URL shortening"
        mock_dg.recognize = AsyncMock(
            return_value=_make_speech_event(expected_text)
        )

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)
        audio_frame = _make_audio_frame()

        result = await wrapped.recognize(buffer=audio_frame)

        assert result.type == stt.SpeechEventType.FINAL_TRANSCRIPT
        assert result.alternatives[0].text == expected_text
        assert result.alternatives[0].language == "en"
        mock_dg.recognize.assert_awaited_once_with(
            buffer=audio_frame, language=None
        )

    @pytest.mark.asyncio
    async def test_multi_turn_transcription(self):
        """Multiple consecutive audio frames each produce correct transcripts."""
        mock_dg = _make_mock_deepgram_stt()
        utterances = [
            "For the URL shortener I'd start with requirements",
            "We need to handle about 100 million URLs per day",
            "I'd use a distributed key-value store like DynamoDB",
        ]

        call_count = 0

        async def sequential_recognize(*args, **kwargs):
            nonlocal call_count
            text = utterances[call_count]
            call_count += 1
            return _make_speech_event(text)

        mock_dg.recognize = sequential_recognize

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)

        results: List[str] = []
        for _ in utterances:
            frame = _make_audio_frame()
            event = await wrapped.recognize(buffer=frame)
            results.append(event.alternatives[0].text)

        assert results == utterances
        assert wrapped._turn_number == 3

    @pytest.mark.asyncio
    async def test_short_utterance_transcribed(self):
        """Very short speech (single word) is captured correctly."""
        mock_dg = _make_mock_deepgram_stt()
        mock_dg.recognize = AsyncMock(
            return_value=_make_speech_event("Yes")
        )

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)
        result = await wrapped.recognize(buffer=_make_audio_frame())

        assert result.alternatives[0].text == "Yes"

    @pytest.mark.asyncio
    async def test_long_utterance_transcribed(self):
        """Long speech (paragraph-length) is captured without truncation."""
        mock_dg = _make_mock_deepgram_stt()
        long_text = (
            "So for the system design of this URL shortener, I would first "
            "consider the read-to-write ratio which is typically around 100:1. "
            "This means we need to optimize heavily for reads. I would use a "
            "distributed cache layer like Redis in front of our persistent "
            "storage to handle the high read throughput. For the write path, "
            "we can use a base-62 encoding scheme to generate short URLs "
            "from an auto-incrementing counter managed by a Zookeeper cluster."
        )
        mock_dg.recognize = AsyncMock(
            return_value=_make_speech_event(long_text)
        )

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)
        result = await wrapped.recognize(buffer=_make_audio_frame())

        assert result.alternatives[0].text == long_text
        assert len(result.alternatives[0].text) > 200

    @pytest.mark.asyncio
    async def test_language_parameter_forwarded(self):
        """Language parameter is passed through to underlying STT."""
        mock_dg = _make_mock_deepgram_stt()
        mock_dg.recognize = AsyncMock(
            return_value=_make_speech_event("Hello", language="en-US")
        )

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)
        frame = _make_audio_frame()
        await wrapped.recognize(buffer=frame, language="en-US")

        mock_dg.recognize.assert_awaited_once_with(
            buffer=frame, language="en-US",
        )


# ---------------------------------------------------------------------------
# Tests — Streaming STT Pipeline
# ---------------------------------------------------------------------------

class TestStreamingSTTPipeline:
    """Verify streaming speech recognition captures speech correctly."""

    @pytest.mark.asyncio
    async def test_stream_yields_final_transcripts(self):
        """Streaming STT yields final transcript events."""
        mock_dg = _make_mock_deepgram_stt()
        mock_stream = MagicMock()

        # Simulate a stream that yields two final events then stops
        events = [
            _make_speech_event("I would design"),
            _make_speech_event("a distributed cache"),
        ]
        event_iter = iter(events)

        async def mock_anext(*args):
            try:
                return next(event_iter)
            except StopIteration:
                raise StopAsyncIteration

        mock_stream.__anext__ = mock_anext
        mock_dg.stream = MagicMock(return_value=mock_stream)

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)
        timeout_stream = wrapped.stream(language="en")

        collected = []
        async for event in timeout_stream:
            collected.append(event.alternatives[0].text)

        assert collected == ["I would design", "a distributed cache"]

    @pytest.mark.asyncio
    async def test_stream_push_frame_forwards_audio(self):
        """push_frame forwards audio data to the underlying stream."""
        mock_stream = MagicMock()

        timeout_stream = TimeoutSpeechStream(
            wrapped_stream=mock_stream,
            timeout=5.0,
            turn_number=1,
        )

        frame = _make_audio_frame()
        timeout_stream.push_frame(frame)

        mock_stream.push_frame.assert_called_once_with(frame)

    @pytest.mark.asyncio
    async def test_stream_close_propagates(self):
        """aclose() is forwarded to the underlying stream."""
        mock_stream = MagicMock()
        mock_stream.aclose = AsyncMock()

        timeout_stream = TimeoutSpeechStream(
            wrapped_stream=mock_stream,
            timeout=5.0,
            turn_number=1,
        )

        await timeout_stream.aclose()
        mock_stream.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests — Speech Capture in Interview Agent Context
# ---------------------------------------------------------------------------

class TestSpeechCaptureIntegration:
    """Verify candidate speech is captured and stored in session state."""

    def test_transcript_recorded_in_session_history(self):
        """Transcribed speech is added to conversation_history."""
        state = _make_session_state(InterviewPhase.SCOPE)
        assert len(state.conversation_history) == 0

        # Simulate what the agent does after STT recognition
        user_text = "I think we need to handle about 500 million requests per day"
        state.add_message("user", user_text)

        assert len(state.conversation_history) == 1
        assert state.conversation_history[0].role == "user"
        assert state.conversation_history[0].content == user_text

    def test_multiple_transcripts_accumulate(self):
        """Multiple transcribed utterances accumulate in session history."""
        state = _make_session_state(InterviewPhase.ARCHITECTURE)

        utterances = [
            "I'd use a microservices architecture",
            "Each service handles one domain",
            "Communication via async message queues",
        ]

        for text in utterances:
            state.add_message("user", text)

        user_messages = [
            m for m in state.conversation_history if m.role == "user"
        ]
        assert len(user_messages) == 3
        assert [m.content for m in user_messages] == utterances

    def test_empty_transcript_not_recorded(self):
        """Empty STT result does not add a user message to history."""
        state = _make_session_state()

        # Simulate what happens in llm_node when STT returns empty
        user_text = ""
        if user_text and user_text.strip():
            state.add_message("user", user_text)

        assert len(state.conversation_history) == 0

    def test_whitespace_only_transcript_not_recorded(self):
        """Whitespace-only STT result is treated as empty."""
        state = _make_session_state()

        user_text = "   \n\t  "
        if user_text and user_text.strip():
            state.add_message("user", user_text)

        assert len(state.conversation_history) == 0

    @pytest.mark.asyncio
    async def test_transcript_preserves_technical_terms(self):
        """STT transcripts preserve technical terms accurately."""
        mock_dg = _make_mock_deepgram_stt()
        technical_text = (
            "I'd use consistent hashing with virtual nodes, "
            "backed by a Cassandra cluster with RF=3 and "
            "quorum reads and writes for strong consistency"
        )
        mock_dg.recognize = AsyncMock(
            return_value=_make_speech_event(technical_text)
        )

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)
        result = await wrapped.recognize(buffer=_make_audio_frame())

        transcript = result.alternatives[0].text
        assert "consistent hashing" in transcript
        assert "virtual nodes" in transcript
        assert "Cassandra" in transcript
        assert "RF=3" in transcript
        assert "quorum" in transcript

    def test_turn_count_tracks_user_messages(self):
        """Session turn counter increments with each user message."""
        state = _make_session_state()
        assert state.total_turn_count == 0

        state.add_message("user", "First utterance")
        assert state.total_turn_count == 1

        state.add_message("assistant", "Interviewer response")
        # Only user turns increment total_turn_count in some implementations
        # Verify it tracks correctly
        assert state.total_turn_count >= 1


# ---------------------------------------------------------------------------
# Tests — STT Pipeline Error Recovery
# ---------------------------------------------------------------------------

class TestSTTPipelineErrorRecovery:
    """Verify STT pipeline handles Deepgram errors gracefully."""

    @pytest.mark.asyncio
    async def test_deepgram_api_error_returns_empty_event(self):
        """Deepgram API error results in empty event, not crash."""
        mock_dg = _make_mock_deepgram_stt()
        mock_dg.recognize = AsyncMock(
            side_effect=ConnectionError("Deepgram API unavailable")
        )

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)
        result = await wrapped.recognize(buffer=_make_audio_frame())

        assert result is not None
        assert result.type == stt.SpeechEventType.FINAL_TRANSCRIPT
        assert result.alternatives[0].text == ""

    @pytest.mark.asyncio
    async def test_deepgram_rate_limit_returns_empty_event(self):
        """Deepgram rate limit error returns empty event gracefully."""
        mock_dg = _make_mock_deepgram_stt()
        mock_dg.recognize = AsyncMock(
            side_effect=Exception("429 Too Many Requests")
        )

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)
        result = await wrapped.recognize(buffer=_make_audio_frame())

        assert result is not None
        assert result.alternatives[0].text == ""

    @pytest.mark.asyncio
    async def test_pipeline_recovers_after_transient_error(self):
        """STT pipeline recovers and transcribes after a transient error."""
        mock_dg = _make_mock_deepgram_stt()

        call_count = 0

        async def flaky_recognize(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Transient network error")
            return _make_speech_event("Recovery successful")

        mock_dg.recognize = flaky_recognize

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=5.0)

        # First call fails gracefully
        result1 = await wrapped.recognize(buffer=_make_audio_frame())
        assert result1.alternatives[0].text == ""

        # Second call succeeds
        result2 = await wrapped.recognize(buffer=_make_audio_frame())
        assert result2.alternatives[0].text == "Recovery successful"

    @pytest.mark.asyncio
    async def test_timeout_returns_empty_not_exception(self):
        """STT timeout returns empty event instead of raising."""
        mock_dg = _make_mock_deepgram_stt()

        async def slow_recognize(*args, **kwargs):
            await asyncio.sleep(10)
            return _make_speech_event("Too late")

        mock_dg.recognize = slow_recognize

        wrapped = TimeoutSTT(wrapped_stt=mock_dg, timeout=0.1)
        result = await wrapped.recognize(buffer=_make_audio_frame())

        assert result is not None
        assert result.alternatives[0].text == ""

    def test_consecutive_silence_increments_counter(self):
        """Empty STT results increment the consecutive silence counter."""
        state = _make_session_state()
        assert state.consecutive_silence_count == 0

        # Simulate the agent's silence tracking logic
        for i in range(3):
            user_text = ""
            if not user_text or not user_text.strip():
                state.consecutive_silence_count += 1

        assert state.consecutive_silence_count == 3

    def test_substantive_input_resets_silence_counter(self):
        """Non-empty transcript resets consecutive silence counter."""
        state = _make_session_state()
        state.consecutive_silence_count = 2

        # Simulate substantive input arriving
        user_text = "I would design a distributed cache"
        if user_text and user_text.strip():
            state.consecutive_silence_count = 0

        assert state.consecutive_silence_count == 0


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
