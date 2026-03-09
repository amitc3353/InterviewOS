"""Run an interview agent."""

import sys
from pathlib import Path

# Add parent directory to path so we can import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from backend.config import AgentConfig
from backend.agents.interview_agent import entrypoint, prewarm  # Phased interview agent
from backend.structured_logging import get_logger
from livekit.agents import WorkerOptions, cli

# Load environment variables
load_dotenv()

logger = get_logger(__name__)


def main():
    """Main entry point."""
    # Load configuration
    config = AgentConfig.from_env()

    # Validate configuration
    if not config.validate():
        logger.error("Invalid configuration. Please check your .env file.")
        logger.error("Required: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, "
                    "DEEPGRAM_API_KEY, ANTHROPIC_API_KEY, CARTESIA_API_KEY")
        sys.exit(1)

    # Initialize structured logging from environment config
    config.init_logging()

    # Initialize Sentry error tracking
    config.init_sentry()

    logger.info("=" * 80)
    logger.info("Starting InterviewOS Agent")
    logger.info(f"LiveKit URL: {config.livekit_url}")
    logger.info(f"LLM Model: {config.llm_model}")
    logger.info(f"TTS Provider: {config.tts_provider}")
    logger.info(f"Cartesia Voice ID: {config.cartesia_voice_id}")
    logger.info(f"VAD Sensitivity: {config.vad_sensitivity}")
    logger.info(f"Silence Threshold: {config.silence_threshold_ms}ms")
    logger.info(f"Semantic Turn Detection: {config.use_semantic_turn_detection}")
    logger.info(f"API Keys: Deepgram={AgentConfig.mask_secret(config.deepgram_api_key)}, "
                f"Anthropic={AgentConfig.mask_secret(config.anthropic_api_key)}, "
                f"Cartesia={AgentConfig.mask_secret(config.cartesia_api_key)}")
    logger.info("=" * 80)
    logger.info("Note: Scenario is passed via LiveKit room metadata when creating the room")
    
    # Create worker options with entrypoint
    worker_opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        ws_url=config.livekit_url,
        api_key=config.livekit_api_key,
        api_secret=config.livekit_api_secret,
    )
    
    # Run agent server (use 'start' or 'dev' subcommand)
    cli.run_app(worker_opts)


if __name__ == "__main__":
    main()
