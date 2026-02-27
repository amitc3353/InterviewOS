"""Configuration for InterviewOS agents."""

import os
from dataclasses import dataclass, field

@dataclass
class AgentConfig:
    """Agent configuration."""
    
    # LiveKit configuration
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    
    # API keys
    deepgram_api_key: str
    anthropic_api_key: str
    openai_api_key: str
    cartesia_api_key: str
    
    # Model configuration
    # NOTE: stt_provider, llm_provider, tts_provider are currently decorative
    # Actual providers are hardcoded in interview_agent.py
    # TODO: Wire these to actually switch providers
    stt_provider: str = "deepgram"
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    tts_provider: str = "cartesia"
    cartesia_voice_id: str = "f786b574-daa5-4673-aa0c-cbe3e8534c02"  # Cartesia plugin default (Katie)
    cartesia_speed: float = 1.0  # Normal speed (sonic-3 requires float)

    # VAD configuration
    vad_sensitivity: float = 0.5  # 0.0-1.0
    silence_threshold_ms: int = 600  # milliseconds of silence before considering turn complete

    # Endpointing — how long to wait after speech before triggering STT
    min_endpointing_delay: float = 0.6   # seconds; start here, tune upward if candidates get cut off
    max_endpointing_delay: float = 5.0   # seconds; covers long thinking pauses

    # Turn detection
    use_semantic_turn_detection: bool = False  # Disabled for now - using VAD only
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load configuration from environment variables."""
        return cls(
            livekit_url=os.getenv("LIVEKIT_URL", ""),
            livekit_api_key=os.getenv("LIVEKIT_API_KEY", ""),
            livekit_api_secret=os.getenv("LIVEKIT_API_SECRET", ""),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            cartesia_api_key=os.getenv("CARTESIA_API_KEY", ""),
            cartesia_voice_id=os.getenv("CARTESIA_VOICE_ID", "f786b574-daa5-4673-aa0c-cbe3e8534c02"),
            min_endpointing_delay=float(os.getenv("MIN_ENDPOINTING_DELAY", "0.6")),
            max_endpointing_delay=float(os.getenv("MAX_ENDPOINTING_DELAY", "5.0")),
            silence_threshold_ms=int(os.getenv("SILENCE_THRESHOLD_MS", "600")),
        )
    
    def validate(self) -> bool:
        """Validate that all required fields are set."""
        required_fields = [
            self.livekit_url,
            self.livekit_api_key,
            self.livekit_api_secret,
            self.deepgram_api_key,
            self.anthropic_api_key,
            self.openai_api_key,
            self.cartesia_api_key,
        ]
        return all(required_fields)
