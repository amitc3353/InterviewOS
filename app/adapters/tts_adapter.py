"""TTS Adapter - Text-to-speech via OpenAI."""

from openai import OpenAI
from app.config import Config


class TTSAdapter:
    """
    TTS adapter for converting text to speech.

    Interface for transport layer - abstracts TTS implementation.
    """

    def __init__(self):
        """Initialize OpenAI client."""
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in .env")

        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)

    def synthesize(self, text: str) -> bytes:
        """
        Convert text to speech audio.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes (MP3 format)
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            response = self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",  # Professional, neutral voice
                input=text,
            )

            # Return audio bytes
            return response.content

        except Exception as e:
            raise RuntimeError(f"OpenAI TTS failed: {e}")
