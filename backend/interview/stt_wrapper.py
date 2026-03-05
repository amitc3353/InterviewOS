"""STT wrapper with timeout and error handling."""

import asyncio
from typing import AsyncIterator, Optional

from livekit import rtc
from livekit.agents import stt

from ..structured_logging import get_logger

logger = get_logger(__name__)


class TimeoutSTT(stt.STT):
    """
    STT wrapper that adds timeout and error handling to any STT implementation.

    Wraps STT stream operations with asyncio.wait_for to prevent hanging.
    On timeout or error, logs the issue and returns empty results.
    """

    def __init__(
        self,
        wrapped_stt: stt.STT,
        timeout: float = 5.0,
    ):
        """
        Initialize timeout STT wrapper.

        Args:
            wrapped_stt: The underlying STT implementation to wrap
            timeout: Maximum seconds to wait for STT recognition (default: 5.0)
        """
        super().__init__()
        self._wrapped_stt = wrapped_stt
        self._timeout = timeout
        self._turn_number = 0

    async def recognize(
        self,
        *,
        buffer: rtc.AudioFrame,
        language: Optional[str] = None,
    ) -> stt.SpeechEvent:
        """
        Recognize speech from audio buffer with timeout protection.

        Args:
            buffer: Audio frame to transcribe
            language: Optional language code

        Returns:
            SpeechEvent with transcription or empty event on timeout/error
        """
        self._turn_number += 1
        start_time = asyncio.get_event_loop().time()

        try:
            # Wrap recognition with timeout
            event = await asyncio.wait_for(
                self._wrapped_stt.recognize(buffer=buffer, language=language),
                timeout=self._timeout,
            )

            duration = asyncio.get_event_loop().time() - start_time

            # Check for empty response
            if not event or not event.alternatives or not event.alternatives[0].text.strip():
                await logger.warning_async(
                    "STT returned empty response",
                    event_type="stt_empty",
                    turn_number=self._turn_number,
                    duration_seconds=round(duration, 2),
                )
                # Return empty event to trigger recovery logic
                return stt.SpeechEvent(
                    type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[stt.SpeechData(text="", language="")],
                )

            await logger.debug_async(
                f"STT recognized text in {duration:.2f}s",
                event_type="stt_recognized",
                turn_number=self._turn_number,
                duration_seconds=round(duration, 2),
                text_preview=event.alternatives[0].text[:50],
            )
            return event

        except asyncio.TimeoutError:
            duration = asyncio.get_event_loop().time() - start_time
            await logger.error_async(
                f"STT timeout after {duration:.2f}s",
                event_type="stt_timeout",
                turn_number=self._turn_number,
                timeout_seconds=self._timeout,
                duration_seconds=round(duration, 2),
            )
            # Return empty event to trigger recovery logic
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(text="", language="")],
            )

        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            await logger.error_async(
                f"STT error after {duration:.2f}s: {e}",
                event_type="stt_error",
                turn_number=self._turn_number,
                duration_seconds=round(duration, 2),
                error_type=type(e).__name__,
                exc_info=True,
            )
            # Return empty event to trigger recovery logic
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(text="", language="")],
            )

    def stream(
        self,
        *,
        language: Optional[str] = None,
    ) -> "TimeoutSpeechStream":
        """
        Create a streaming recognition session with timeout protection.

        Args:
            language: Optional language code

        Returns:
            TimeoutSpeechStream that wraps the underlying stream
        """
        wrapped_stream = self._wrapped_stt.stream(language=language)
        return TimeoutSpeechStream(
            wrapped_stream=wrapped_stream,
            timeout=self._timeout,
            turn_number=self._turn_number,
        )


class TimeoutSpeechStream(stt.SpeechStream):
    """
    Speech stream wrapper that adds timeout protection to streaming STT.
    """

    def __init__(
        self,
        wrapped_stream: stt.SpeechStream,
        timeout: float,
        turn_number: int,
    ):
        """
        Initialize timeout speech stream.

        Args:
            wrapped_stream: The underlying speech stream to wrap
            timeout: Maximum seconds to wait for each STT event
            turn_number: Current turn number for logging
        """
        super().__init__()
        self._wrapped_stream = wrapped_stream
        self._timeout = timeout
        self._turn_number = turn_number

    async def __anext__(self) -> stt.SpeechEvent:
        """
        Get next speech event with timeout protection.

        Returns:
            SpeechEvent from underlying stream

        Raises:
            StopAsyncIteration: When stream ends
        """
        try:
            # Wrap each event with timeout
            event = await asyncio.wait_for(
                self._wrapped_stream.__anext__(),
                timeout=self._timeout,
            )
            return event

        except asyncio.TimeoutError:
            await logger.error_async(
                f"STT stream timeout after {self._timeout:.2f}s",
                event_type="stt_stream_timeout",
                turn_number=self._turn_number,
                timeout_seconds=self._timeout,
            )
            # End the stream on timeout
            raise StopAsyncIteration

        except Exception as e:
            await logger.error_async(
                f"STT stream error: {e}",
                event_type="stt_stream_error",
                turn_number=self._turn_number,
                error_type=type(e).__name__,
                exc_info=True,
            )
            # End the stream on error
            raise StopAsyncIteration

    async def aclose(self):
        """Close the underlying stream."""
        await self._wrapped_stream.aclose()

    def push_frame(self, frame: rtc.AudioFrame):
        """Push audio frame to underlying stream."""
        self._wrapped_stream.push_frame(frame)

    async def flush(self):
        """Flush underlying stream."""
        try:
            await asyncio.wait_for(
                self._wrapped_stream.flush(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            await logger.warning_async(
                f"STT stream flush timeout after {self._timeout:.2f}s",
                event_type="stt_flush_timeout",
                timeout_seconds=self._timeout,
            )
        except Exception as e:
            await logger.error_async(
                f"STT stream flush error: {e}",
                event_type="stt_flush_error",
                error_type=type(e).__name__,
            )
