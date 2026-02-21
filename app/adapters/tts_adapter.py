"""TTS Adapter - Text-to-speech via OpenAI."""

from openai import OpenAI
from app.config import Config


# Voice Configuration Presets for A/B Testing
VOICE_CONFIGS = {
    "alloy_hd": {
        "name": "Alloy HD (Neutral & Balanced)",
        "model": "tts-1-hd",  # High quality
        "voice": "alloy",
        "speed": 0.95,  # Slightly slower for naturalness
        "response_format": "mp3",
        "description": "Neutral, clear, professional. Safe default for technical interviews.",
    },
    "onyx_hd": {
        "name": "Onyx HD (Authoritative & Clear)",
        "model": "tts-1-hd",
        "voice": "onyx",  # Deeper, more authoritative
        "speed": 0.92,  # Slightly slower, more deliberate
        "response_format": "mp3",
        "description": "Deep, authoritative voice. Good for technical authority and gravitas.",
    },
    "nova_hd": {
        "name": "Nova HD (Warm & Conversational)",
        "model": "tts-1-hd",
        "voice": "nova",  # Warm, engaging
        "speed": 0.95,  # Natural pace
        "response_format": "mp3",
        "description": "Warm, friendly, conversational. Best for natural peer-to-peer feel.",
    },
}

# Default voice config
DEFAULT_VOICE = "nova_hd"


class TTSAdapter:
    """
    TTS adapter for converting text to speech.

    Interface for transport layer - abstracts TTS implementation.
    """

    def __init__(self, voice_config: str = DEFAULT_VOICE):
        """
        Initialize OpenAI client.

        Args:
            voice_config: Voice preset name (alloy_hd, onyx_hd, nova_hd)
        """
        if not Config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in .env")

        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)

        # Load voice config
        if voice_config not in VOICE_CONFIGS:
            raise ValueError(
                f"Unknown voice config: {voice_config}. Choose from: {list(VOICE_CONFIGS.keys())}"
            )

        self.config = VOICE_CONFIGS[voice_config]

    def synthesize(self, text: str) -> bytes:
        """
        Convert text to speech audio.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes (MP3 format, high quality)
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            response = self.client.audio.speech.create(
                model=self.config["model"],
                voice=self.config["voice"],
                input=text,
                speed=self.config["speed"],
                response_format=self.config["response_format"],
            )

            # Return audio bytes
            return response.content

        except Exception as e:
            raise RuntimeError(f"OpenAI TTS failed: {e}") from e
