"""Audio Output Adapter - Play audio via sounddevice."""

import io
import sounddevice as sd
import soundfile as sf


class AudioOutAdapter:
    """
    Audio output adapter for playing synthesized speech.

    Interface for transport layer - abstracts audio playback.
    """

    # Consistent audio settings to avoid CoreAudio errors
    SAMPLE_RATE = 24000  # Match common TTS output
    CHANNELS = 1  # Mono

    def __init__(self):
        """Initialize audio output."""
        self.is_playing = False
        self._current_stream = None

    def play(self, audio_buffer: bytes, retry_on_error: bool = True) -> None:
        """
        Play audio from buffer with CoreAudio crash protection.

        Args:
            audio_buffer: Audio bytes (MP3, WAV, etc.)
            retry_on_error: Retry once on error -50

        Raises:
            RuntimeError: If playback fails after retry
        """
        if not audio_buffer:
            return

        try:
            self._play_internal(audio_buffer)
        except Exception as e:
            error_msg = str(e)
            # Check for CoreAudio error -50 (device/format mismatch)
            if retry_on_error and ("-50" in error_msg or "PaMacCore" in error_msg):
                # Reset audio subsystem and retry once
                self._reset_audio()
                try:
                    self._play_internal(audio_buffer)
                except Exception as retry_err:
                    raise RuntimeError(
                        f"Audio playback failed after retry: {retry_err}"
                    ) from retry_err
            else:
                raise RuntimeError(f"Audio playback failed: {e}") from e

    def _play_internal(self, audio_buffer: bytes) -> None:
        """
        Internal playback with proper cleanup.

        Args:
            audio_buffer: Audio bytes to play
        """
        data = None
        samplerate = None

        try:
            # Read audio from buffer
            audio_io = io.BytesIO(audio_buffer)
            data, samplerate = sf.read(audio_io)

            # Ensure consistent format
            if data.ndim > 1:
                # Convert stereo to mono if needed
                data = data.mean(axis=1)

            # Play (blocking) with consistent settings
            self.is_playing = True

            # Use default device with matching settings
            sd.play(data, samplerate=samplerate, blocking=True)

        finally:
            # Always reset playing flag
            self.is_playing = False

    def _reset_audio(self) -> None:
        """
        Reset audio subsystem to recover from CoreAudio errors.

        Stops any playing audio and resets sounddevice state.
        """
        try:
            sd.stop()
        except Exception:
            # Ignore errors during cleanup - safe to suppress
            pass  # nosec

        self.is_playing = False
        self._current_stream = None

    def stop(self) -> None:
        """Stop current playback."""
        if self.is_playing:
            try:
                sd.stop()
            finally:
                self.is_playing = False
                self._current_stream = None
