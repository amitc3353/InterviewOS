"""Configuration and environment variable loading."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Config:
    """Application configuration loaded from environment variables."""

    # Required API keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
    DAILY_API_KEY = os.getenv("DAILY_API_KEY")
    DAILY_DOMAIN = os.getenv("DAILY_DOMAIN")

    # Paths
    PROJECT_ROOT = Path(__file__).parent.parent
    TRANSCRIPTS_DIR = PROJECT_ROOT / "transcripts"
    AUDIO_DIR = PROJECT_ROOT / "audio"
    SCORES_DIR = PROJECT_ROOT / "scores"

    @classmethod
    def validate(cls):
        """Validate that all required environment variables are set."""
        missing = []

        required_vars = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "DEEPGRAM_API_KEY",
            "DAILY_API_KEY",
            "DAILY_DOMAIN",
        ]

        for var in required_vars:
            if not getattr(cls, var):
                missing.append(var)

        if missing:
            raise ValueError(
                f"❌ Missing required environment variables:\n"
                f"   {', '.join(missing)}\n\n"
                f"💡 Copy .env.example to .env and fill in your API keys."
            )

    @classmethod
    def ensure_dirs(cls):
        """Ensure all required directories exist."""
        cls.TRANSCRIPTS_DIR.mkdir(exist_ok=True)
        cls.AUDIO_DIR.mkdir(exist_ok=True)
        cls.SCORES_DIR.mkdir(exist_ok=True)
