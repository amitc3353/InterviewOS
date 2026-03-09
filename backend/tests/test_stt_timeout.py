"""Tests for STT timeout and error handling — 8 tests, zero network calls."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit import rtc
from livekit.agents import llm, stt

from backend.interview.stt_wrapper import TimeoutSTT, TimeoutSpeechStream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_speech_event(text: str) -> stt.SpeechEvent:
    """Create a mock SpeechEvent with the given text."""
    return stt.SpeechEvent(
        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
        alternatives=[stt.SpeechData(text=text, language="en")],
    )


def _make_empty_speech_event() -> stt.SpeechEvent:
    """Create a mock SpeechEvent with empty text."""
    return stt.SpeechEvent(
        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
        alternatives=[stt.SpeechData(text="", language="")],
    )


def _make_audio_frame() -> rtc.AudioFrame:
    """Create a minimal mock audio frame."""
    frame = MagicMock(spec=rtc.AudioFrame)
    return frame


# ---------------------------------------------------------------------------
# TimeoutSTT.recognize() Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recognize_success():
    """recognize() returns event from wrapped STT when successful."""
    # Setup mock STT
    mock_stt = MagicMock(spec=stt.STT)
    expected_event = _make_speech_event("Hello world")
    mock_stt.recognize = AsyncMock(return_value=expected_event)

    # Create wrapper
    timeout_stt = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

    # Call recognize
    audio_frame = _make_audio_frame()
    result = await timeout_stt.recognize(buffer=audio_frame)

    # Verify
    assert result == expected_event
    assert result.alternatives[0].text == "Hello world"
    mock_stt.recognize.assert_awaited_once_with(buffer=audio_frame, language=None)


@pytest.mark.asyncio
async def test_recognize_timeout():
    """recognize() returns empty event when wrapped STT times out."""
    # Setup mock STT that never completes
    mock_stt = MagicMock(spec=stt.STT)

    async def slow_recognize(*args, **kwargs):
        await asyncio.sleep(10)  # Longer than timeout
        return _make_speech_event("Too late")

    mock_stt.recognize = slow_recognize

    # Create wrapper with short timeout
    timeout_stt = TimeoutSTT(wrapped_stt=mock_stt, timeout=0.1)

    # Call recognize - should timeout
    audio_frame = _make_audio_frame()
    result = await timeout_stt.recognize(buffer=audio_frame)

    # Verify empty event returned (not exception raised)
    assert result is not None
    assert result.type == stt.SpeechEventType.FINAL_TRANSCRIPT
    assert len(result.alternatives) > 0
    assert result.alternatives[0].text == ""


@pytest.mark.asyncio
async def test_recognize_empty_response():
    """recognize() returns empty event when wrapped STT returns empty text."""
    # Setup mock STT that returns empty text
    mock_stt = MagicMock(spec=stt.STT)
    mock_stt.recognize = AsyncMock(return_value=_make_empty_speech_event())

    # Create wrapper
    timeout_stt = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

    # Call recognize
    audio_frame = _make_audio_frame()
    result = await timeout_stt.recognize(buffer=audio_frame)

    # Verify empty event returned
    assert result is not None
    assert result.alternatives[0].text == ""


@pytest.mark.asyncio
async def test_recognize_error_handling():
    """recognize() returns empty event when wrapped STT raises exception."""
    # Setup mock STT that raises exception
    mock_stt = MagicMock(spec=stt.STT)
    mock_stt.recognize = AsyncMock(side_effect=RuntimeError("Deepgram API error"))

    # Create wrapper
    timeout_stt = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

    # Call recognize - should catch error and return empty event
    audio_frame = _make_audio_frame()
    result = await timeout_stt.recognize(buffer=audio_frame)

    # Verify empty event returned (not exception raised)
    assert result is not None
    assert result.alternatives[0].text == ""


@pytest.mark.asyncio
async def test_recognize_turn_counter():
    """recognize() increments turn counter for logging context."""
    # Setup mock STT
    mock_stt = MagicMock(spec=stt.STT)
    mock_stt.recognize = AsyncMock(return_value=_make_speech_event("Turn 1"))

    # Create wrapper
    timeout_stt = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

    # Initial turn number should be 0
    assert timeout_stt._turn_number == 0

    # First call
    await timeout_stt.recognize(buffer=_make_audio_frame())
    assert timeout_stt._turn_number == 1

    # Second call
    await timeout_stt.recognize(buffer=_make_audio_frame())
    assert timeout_stt._turn_number == 2


# ---------------------------------------------------------------------------
# TimeoutSTT.stream() Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_creates_wrapper():
    """stream() creates TimeoutSpeechStream wrapper."""
    # Setup mock STT
    mock_stt = MagicMock(spec=stt.STT)
    mock_stream = MagicMock(spec=stt.SpeechStream)
    mock_stt.stream = MagicMock(return_value=mock_stream)

    # Create wrapper
    timeout_stt = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

    # Call stream
    result = timeout_stt.stream(language="en")

    # Verify wrapper created
    assert isinstance(result, TimeoutSpeechStream)
    assert result._wrapped_stream == mock_stream
    assert result._timeout == 5.0
    mock_stt.stream.assert_called_once_with(language="en")


# ---------------------------------------------------------------------------
# TimeoutSpeechStream Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_timeout():
    """Stream iterator handles timeout gracefully."""
    # Setup mock stream that never yields
    mock_stream = MagicMock(spec=stt.SpeechStream)

    async def slow_iter():
        await asyncio.sleep(10)  # Longer than timeout
        yield _make_speech_event("Too late")

    mock_stream.__anext__ = AsyncMock(side_effect=slow_iter().__anext__)

    # Create wrapper with short timeout
    timeout_stream = TimeoutSpeechStream(
        wrapped_stream=mock_stream,
        timeout=0.1,
        turn_number=1,
    )

    # Try to iterate - should stop on timeout
    events = []
    try:
        async for event in timeout_stream:
            events.append(event)
    except StopAsyncIteration:
        pass

    # Verify no events were yielded (timeout triggered StopAsyncIteration)
    assert len(events) == 0


@pytest.mark.asyncio
async def test_agent_recovery_message():
    """Integration test: Agent generates recovery message on empty STT."""
    from backend.agents.interview_agent import InterviewAgent
    from backend.config import AgentConfig
    from backend.models.session import InterviewPhase

    # Create minimal config
    config = AgentConfig(
        livekit_url="ws://localhost:7880",
        livekit_api_key="test",
        livekit_api_secret="test",
        deepgram_api_key="test",
        anthropic_api_key="test",
        openai_api_key="test",
        cartesia_api_key="test",
        llm_model="claude-sonnet-4-20250514",
    )

    # Create agent
    agent = InterviewAgent(config, "Design a URL shortener")

    # Create mock chat context with empty user message
    mock_chat_ctx = MagicMock(spec=llm.ChatContext)
    mock_chat_ctx.items = []

    # Create empty user message
    empty_msg = MagicMock()
    empty_msg.role = "user"
    empty_msg.content = [""]  # Empty text
    mock_chat_ctx.messages = MagicMock(return_value=[empty_msg])
    mock_chat_ctx.add_message = MagicMock()

    # Mock the Agent.default.llm_node to avoid actual LLM calls
    with patch('livekit.agents.Agent.default.llm_node') as mock_llm_node:
        # Collect chunks yielded by llm_node
        chunks = []
        async for chunk in agent.llm_node(mock_chat_ctx, [], MagicMock()):
            chunks.append(chunk)

        # Verify recovery message was generated
        assert len(chunks) == 1
        assert chunks[0].delta.content == "Sorry, I didn't catch that. Can you repeat?"

        # Verify LLM was not called (we returned early)
        mock_llm_node.assert_not_called()

        # Verify recovery message was added to history
        messages = agent.interview_session.state.conversation_history
        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].content == "Sorry, I didn't catch that. Can you repeat?"
