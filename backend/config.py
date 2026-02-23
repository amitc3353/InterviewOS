"""Configuration for InterviewOS agents."""

import os
from dataclasses import dataclass
from typing import Optional


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
    
    # Model configuration
    stt_provider: str = "deepgram"
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    tts_provider: str = "openai"
    tts_voice: str = "echo"  # alloy, echo, fable, onyx, nova, shimmer
    
    # VAD configuration
    vad_sensitivity: float = 0.5  # 0.0-1.0
    silence_threshold_ms: int = 600  # milliseconds of silence before considering turn complete
    
    # Turn detection
    use_semantic_turn_detection: bool = True  # Use both VAD + semantic turn detection
    
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
        ]
        return all(required_fields)
