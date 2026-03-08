"""Tests for structured logging in stt_wrapper.py — STT error and timeout logging."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import logging

import pytest
from livekit import rtc
from livekit.agents import stt

from backend.interview.stt_wrapper import TimeoutSTT, TimeoutSpeechStream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_stt() -> stt.STT:
    """Create a mock STT implementation."""
    mock_stt = MagicMock(spec=stt.STT)
    return mock_stt


def _make_speech_event(text: str = "Hello world") -> stt.SpeechEvent:
    """Create a mock SpeechEvent."""
    return stt.SpeechEvent(
        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
        alternatives=[stt.SpeechData(text=text, language="en")],
    )


# ---------------------------------------------------------------------------
# Tests — STT Timeout Logging
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stt_timeout_logs_error_event():
    """STT timeout logs error event with timeout_seconds and turn_number."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.error_async = AsyncMock()

        # Create mock STT that times out
        mock_stt = _make_mock_stt()
        mock_stt.recognize = AsyncMock()

        async def slow_recognize(*args, **kwargs):
            await asyncio.sleep(10)  # Exceeds timeout
            return _make_speech_event()

        mock_stt.recognize.side_effect = slow_recognize

        # Wrap with timeout
        wrapped = TimeoutSTT(wrapped_stt=mock_stt, timeout=0.1)

        # Try to recognize (should timeout)
        buffer = MagicMock(spec=rtc.AudioFrame)
        result = await wrapped.recognize(buffer=buffer)

        # Should return empty event
        assert result.alternatives[0].text == ""

        # Verify timeout logging
        assert mock_logger.error_async.called
        call_args = mock_logger.error_async.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'stt_timeout'
        assert 'turn_number' in call_args.kwargs
        assert 'timeout_seconds' in call_args.kwargs
        assert call_args.kwargs['timeout_seconds'] == 0.1


@pytest.mark.asyncio
async def test_stt_error_logs_error_event():
    """STT error logs error event with error_type and turn_number."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.error_async = AsyncMock()

        # Create mock STT that raises error
        mock_stt = _make_mock_stt()
        mock_stt.recognize = AsyncMock()
        mock_stt.recognize.side_effect = RuntimeError("STT service unavailable")

        # Wrap with timeout
        wrapped = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

        # Try to recognize (should error)
        buffer = MagicMock(spec=rtc.AudioFrame)
        result = await wrapped.recognize(buffer=buffer)

        # Should return empty event
        assert result.alternatives[0].text == ""

        # Verify error logging
        assert mock_logger.error_async.called
        call_args = mock_logger.error_async.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'stt_error'
        assert 'turn_number' in call_args.kwargs
        assert 'error_type' in call_args.kwargs
        assert call_args.kwargs['error_type'] == 'RuntimeError'


@pytest.mark.asyncio
async def test_stt_empty_response_logs_warning():
    """STT empty response logs warning event."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.warning_async = AsyncMock()

        # Create mock STT that returns empty text
        mock_stt = _make_mock_stt()
        mock_stt.recognize = AsyncMock(return_value=_make_speech_event(text=""))

        # Wrap with timeout
        wrapped = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

        # Recognize empty response
        buffer = MagicMock(spec=rtc.AudioFrame)
        result = await wrapped.recognize(buffer=buffer)

        # Should return empty event
        assert result.alternatives[0].text == ""

        # Verify warning logging
        assert mock_logger.warning_async.called
        call_args = mock_logger.warning_async.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'stt_empty'
        assert 'turn_number' in call_args.kwargs


@pytest.mark.asyncio
async def test_stt_success_logs_debug():
    """Successful STT recognition logs debug event with text preview."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.debug_async = AsyncMock()

        # Create mock STT that succeeds
        mock_stt = _make_mock_stt()
        mock_stt.recognize = AsyncMock(return_value=_make_speech_event("I would design a distributed cache"))

        # Wrap with timeout
        wrapped = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

        # Recognize
        buffer = MagicMock(spec=rtc.AudioFrame)
        result = await wrapped.recognize(buffer=buffer)

        # Should return full text
        assert result.alternatives[0].text == "I would design a distributed cache"

        # Verify debug logging
        assert mock_logger.debug_async.called
        call_args = mock_logger.debug_async.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'stt_recognized'
        assert 'turn_number' in call_args.kwargs
        assert 'text_preview' in call_args.kwargs


# ---------------------------------------------------------------------------
# Tests — STT Stream Logging
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stt_stream_timeout_logs_error():
    """STT stream timeout logs error event."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.error_async = AsyncMock()

        # Use a real class instead of MagicMock — dunder methods on MagicMock
        # instances are not reliably forwarded by the metaclass.
        class SlowStream:
            async def __anext__(self):
                await asyncio.sleep(10)
                return _make_speech_event()

            def push_frame(self, frame):
                pass

            async def flush(self):
                pass

            async def aclose(self):
                pass

        # Wrap with timeout
        wrapped_stream = TimeoutSpeechStream(
            wrapped_stream=SlowStream(),
            timeout=0.1,
            turn_number=1,
        )

        # Try to get next event (should timeout)
        with pytest.raises(StopAsyncIteration):
            await wrapped_stream.__anext__()

        # Verify timeout logging
        assert mock_logger.error_async.called
        call_args = mock_logger.error_async.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'stt_stream_timeout'
        assert 'timeout_seconds' in call_args.kwargs


@pytest.mark.asyncio
async def test_stt_stream_error_logs_error():
    """STT stream error logs error event with error_type."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.error_async = AsyncMock()

        # Use a real class instead of MagicMock for reliable dunder forwarding.
        class ErrorStream:
            async def __anext__(self):
                raise ValueError("Stream error")

            def push_frame(self, frame):
                pass

            async def flush(self):
                pass

            async def aclose(self):
                pass

        # Wrap with timeout
        wrapped_stream = TimeoutSpeechStream(
            wrapped_stream=ErrorStream(),
            timeout=5.0,
            turn_number=1,
        )

        # Try to get next event (should error)
        with pytest.raises(StopAsyncIteration):
            await wrapped_stream.__anext__()

        # Verify error logging
        assert mock_logger.error_async.called
        call_args = mock_logger.error_async.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'stt_stream_error'
        assert 'error_type' in call_args.kwargs
        assert call_args.kwargs['error_type'] == 'ValueError'


@pytest.mark.asyncio
async def test_stt_stream_flush_timeout_logs_warning():
    """STT stream flush timeout logs warning event."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.warning_async = AsyncMock()

        # Create mock stream with slow flush
        mock_stream = MagicMock(spec=stt.SpeechStream)

        async def slow_flush():
            await asyncio.sleep(10)

        mock_stream.flush = slow_flush

        # Wrap with timeout
        wrapped_stream = TimeoutSpeechStream(
            wrapped_stream=mock_stream,
            timeout=0.1,
            turn_number=1,
        )

        # Flush (should timeout)
        await wrapped_stream.flush()

        # Verify timeout logging
        assert mock_logger.warning_async.called
        call_args = mock_logger.warning_async.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'stt_flush_timeout'
        assert 'timeout_seconds' in call_args.kwargs


@pytest.mark.asyncio
async def test_stt_stream_flush_error_logs_error():
    """STT stream flush error logs error event."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.error_async = AsyncMock()

        # Create mock stream with flush error
        mock_stream = MagicMock(spec=stt.SpeechStream)

        async def error_flush():
            raise IOError("Flush failed")

        mock_stream.flush = error_flush

        # Wrap with timeout
        wrapped_stream = TimeoutSpeechStream(
            wrapped_stream=mock_stream,
            timeout=5.0,
            turn_number=1,
        )

        # Flush (should error)
        await wrapped_stream.flush()

        # Verify error logging
        assert mock_logger.error_async.called
        call_args = mock_logger.error_async.call_args

        assert 'event_type' in call_args.kwargs
        assert call_args.kwargs['event_type'] == 'stt_flush_error'
        assert 'error_type' in call_args.kwargs
        assert call_args.kwargs['error_type'] == 'OSError'  # IOError is alias for OSError in Python 3


# ---------------------------------------------------------------------------
# Tests — Turn Number Tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_turn_number_increments_per_recognize():
    """Turn number increments with each recognize call."""
    with patch('backend.interview.stt_wrapper.logger') as mock_logger:
        mock_logger.debug_async = AsyncMock()

        mock_stt = _make_mock_stt()
        mock_stt.recognize = AsyncMock(return_value=_make_speech_event())

        wrapped = TimeoutSTT(wrapped_stt=mock_stt, timeout=5.0)

        buffer = MagicMock(spec=rtc.AudioFrame)

        # First recognize
        await wrapped.recognize(buffer=buffer)
        first_call = mock_logger.debug_async.call_args
        assert first_call.kwargs['turn_number'] == 1

        # Second recognize
        await wrapped.recognize(buffer=buffer)
        second_call = mock_logger.debug_async.call_args
        assert second_call.kwargs['turn_number'] == 2


# ---------------------------------------------------------------------------
# Tests — Run All Tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
