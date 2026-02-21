"""Audio Output Adapter - Play audio via sounddevice."""

import io
import sounddevice as sd
import soundfile as sf


class AudioOutAdapter:
    """
    Audio output adapter for playing synthesized speech.

    Interface for transport layer - abstracts audio playback.
    """

    def __init__(self):
        """Initialize audio output."""
        self.is_playing = False

    def play(self, audio_buffer: bytes) -> None:
        """
        Play audio from buffer.

        Args:
            audio_buffer: Audio bytes (MP3, WAV, etc.)
        """
        if not audio_buffer:
            return

        try:
            # Read audio from buffer
            audio_io = io.BytesIO(audio_buffer)
            data, samplerate = sf.read(audio_io)

            # Play (blocking)
            self.is_playing = True
            sd.play(data, samplerate)
            sd.wait()  # Wait until playback finishes
            self.is_playing = False

        except Exception as e:
            self.is_playing = False
            raise RuntimeError(f"Audio playback failed: {e}")

    def stop(self) -> None:
        """Stop current playback."""
        if self.is_playing:
            sd.stop()
            self.is_playing = False
