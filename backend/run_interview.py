"""Run an interview agent."""

import logging
import sys
from pathlib import Path

# Add parent directory to path so we can import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from backend.config import AgentConfig
from backend.agents.interview_agent import run_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()
    
    # Load configuration
    config = AgentConfig.from_env()
    
    # Validate configuration
    if not config.validate():
        logger.error("Invalid configuration. Please check your .env file.")
        logger.error("Required: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, "
                    "DEEPGRAM_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY")
        sys.exit(1)
    
    # Get scenario from command line or use default
    scenario = "Design a URL shortener"
    if len(sys.argv) > 1:
        scenario = " ".join(sys.argv[1:])  # Join all args as scenario
    
    logger.info("=" * 80)
    logger.info(f"Starting InterviewOS Agent")
    logger.info(f"Scenario: {scenario}")
    logger.info(f"LiveKit URL: {config.livekit_url}")
    logger.info(f"LLM Model: {config.llm_model}")
    logger.info(f"TTS Voice: {config.tts_voice}")
    logger.info(f"VAD Sensitivity: {config.vad_sensitivity}")
    logger.info(f"Silence Threshold: {config.silence_threshold_ms}ms")
    logger.info("=" * 80)
    
    # Run the agent
    try:
        run_agent(config, scenario)
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
