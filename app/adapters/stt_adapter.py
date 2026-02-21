"""STT Adapter - Streaming speech-to-text via Deepgram."""

import queue
from typing import Callable, Optional
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from app.config import Config


class STTAdapter:
    """
    Streaming speech-to-text adapter.

    Interface for transport layer - abstracts STT implementation.
    """

    def __init__(self):
        """Initialize Deepgram client."""
        if not Config.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY not set in .env")

        self.client = DeepgramClient(Config.DEEPGRAM_API_KEY)
        self.connection = None
        self.is_listening = False

        self.partial_callback: Optional[Callable[[str], None]] = None
        self.final_transcript = []
        self.audio_queue = queue.Queue()

    def on_partial(self, callback: Callable[[str], None]) -> None:
        """
        Register callback for partial transcripts (streaming).

        Args:
            callback: Function to call with partial transcript text
        """
        self.partial_callback = callback

    def start_listening(self) -> None:
        """Start streaming transcription."""
        if self.is_listening:
            return

        self.is_listening = True
        self.final_transcript = []

        # Create connection
        self.connection = self.client.listen.live.v("1")

        # Event handlers
        def on_message(self, result, **kwargs):
            sentence = result.channel.alternatives[0].transcript

            if len(sentence) == 0:
                return

            if result.is_final:
                self.final_transcript.append(sentence)
            elif self.partial_callback:
                # Call partial callback for streaming feedback
                self.partial_callback(sentence)

        def on_error(self, error, **kwargs):
            print(f"STT Error: {error}")

        # Register handlers
        self.connection.on(LiveTranscriptionEvents.Transcript, on_message)
        self.connection.on(LiveTranscriptionEvents.Error, on_error)

        # Start connection
        options = LiveOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            interim_results=True,
            utterance_end_ms=1000,
            endpointing=300,
        )

        if not self.connection.start(options):
            raise RuntimeError("Failed to start Deepgram connection")

    def send_audio(self, audio_data: bytes) -> None:
        """
        Send audio data to STT service.

        Args:
            audio_data: Raw audio bytes (PCM 16-bit, 16kHz)
        """
        if self.connection and self.is_listening:
            self.connection.send(audio_data)

    def stop_listening(self) -> str:
        """
        Stop listening and return finalized transcript.

        Returns:
            Complete transcript text
        """
        if not self.is_listening:
            return ""

        self.is_listening = False

        # Flush and close connection
        if self.connection:
            self.connection.finish()
            self.connection = None

        # Join final transcript
        transcript = " ".join(self.final_transcript).strip()
        self.final_transcript = []

        return transcript
