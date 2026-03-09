"""Configuration for InterviewOS agents."""

import os
from dataclasses import dataclass, field
from typing import Optional

try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

from .structured_logging import get_logger

logger = get_logger(__name__)

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
    cartesia_speed: float = 0.85  # Slightly slower for deliberate interview pace (sonic-3 requires float)
    cartesia_pronunciation_dict_id: Optional[str] = None

    # VAD configuration
    vad_sensitivity: float = 0.5  # 0.0-1.0
    silence_threshold_ms: int = 600  # milliseconds of silence before considering turn complete

    # Endpointing — how long to wait after speech before triggering STT
    min_endpointing_delay: float = 0.6   # seconds; start here, tune upward if candidates get cut off
    max_endpointing_delay: float = 5.0   # seconds; covers long thinking pauses

    # Turn detection
    use_semantic_turn_detection: bool = True

    # Sentry error tracking
    sentry_dsn: Optional[str] = None
    sentry_environment: str = "production"
    sentry_enabled: bool = True

    # Logging configuration
    log_level: str = "INFO"  # DEBUG/INFO/WARNING/ERROR/CRITICAL
    log_format: str = "console"  # "console" or "json"
    
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
            cartesia_speed=float(os.getenv("CARTESIA_SPEED", "0.85")),
            vad_sensitivity=float(os.getenv("VAD_SENSITIVITY", "0.5")),
            min_endpointing_delay=float(os.getenv("MIN_ENDPOINTING_DELAY", "0.6")),
            max_endpointing_delay=float(os.getenv("MAX_ENDPOINTING_DELAY", "5.0")),
            silence_threshold_ms=int(os.getenv("SILENCE_THRESHOLD_MS", "600")),
            use_semantic_turn_detection=os.getenv("SEMANTIC_TURN_DETECTION", "true").lower() != "false",
            cartesia_pronunciation_dict_id=os.getenv("CARTESIA_PRONUNCIATION_DICT_ID") or None,
            sentry_dsn=os.getenv("SENTRY_DSN") or None,
            sentry_environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            sentry_enabled=os.getenv("SENTRY_ENABLED", "true").lower() != "false",
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            log_format=os.getenv("LOG_FORMAT", "console").lower(),
        )
    
    # Common placeholder values that indicate keys haven't been configured
    _PLACEHOLDER_PATTERNS = (
        "your_",
        "sk-xxx",
        "key_here",
        "replace_me",
        "todo",
        "changeme",
        "placeholder",
    )

    def validate(self) -> bool:
        """Validate that all required fields are set and not placeholder values."""
        required_keys = {
            "livekit_url": self.livekit_url,
            "livekit_api_key": self.livekit_api_key,
            "livekit_api_secret": self.livekit_api_secret,
            "deepgram_api_key": self.deepgram_api_key,
            "anthropic_api_key": self.anthropic_api_key,
            "openai_api_key": self.openai_api_key,
            "cartesia_api_key": self.cartesia_api_key,
        }

        for name, value in required_keys.items():
            if not value:
                logger.error(f"Missing required config: {name}")
                return False
            if self._is_placeholder(value):
                logger.error(f"Config '{name}' appears to be a placeholder value")
                return False

        return True

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        """Check if a value looks like a placeholder that hasn't been configured."""
        value_lower = value.lower()
        return any(p in value_lower for p in AgentConfig._PLACEHOLDER_PATTERNS)

    @staticmethod
    def mask_secret(value: str) -> str:
        """Mask a secret value for safe logging, showing only last 4 chars."""
        if not value or len(value) <= 4:
            return "****"
        return f"****{value[-4:]}"

    def init_sentry(self) -> bool:
        """
        Initialize Sentry SDK for error tracking.

        Returns:
            True if Sentry was initialized, False otherwise
        """
        # Check if Sentry is available
        if not SENTRY_AVAILABLE:
            logger.warning("sentry-sdk not installed, skipping error tracking")
            return False

        # Check if Sentry is enabled
        if not self.sentry_enabled:
            logger.info("Sentry disabled via SENTRY_ENABLED=false")
            return False

        # Check if DSN is configured
        if not self.sentry_dsn:
            logger.info("Sentry DSN not configured, skipping error tracking")
            return False

        try:
            sentry_sdk.init(
                dsn=self.sentry_dsn,
                environment=self.sentry_environment,
                traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
                profiles_sample_rate=0.1,  # 10% of transactions for profiling
            )
            logger.info(f"Sentry initialized for environment: {self.sentry_environment}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Sentry: {e}")
            return False

    def init_logging(self) -> bool:
        """
        Initialize structured logging system.

        Returns:
            True if logging was initialized successfully, False otherwise
        """
        try:
            # Import here to avoid circular imports
            from .structured_logging import configure_logging, LogLevel

            # Map string level to LogLevel enum
            level_map = {
                "DEBUG": LogLevel.DEBUG,
                "INFO": LogLevel.INFO,
                "WARNING": LogLevel.WARNING,
                "ERROR": LogLevel.ERROR,
                "CRITICAL": LogLevel.CRITICAL,
            }

            level = level_map.get(self.log_level, LogLevel.INFO)

            # Configure structured logging
            configure_logging(
                level=level,
                format_mode=self.log_format,
                include_timestamp=True
            )

            logger.info(f"Structured logging initialized: level={self.log_level}, format={self.log_format}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize structured logging: {e}")
            return False
