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
        scenario = sys.argv[1]
    
    logger.info(f"Starting interview agent for scenario: {scenario}")
    logger.info(f"LiveKit URL: {config.livekit_url}")
    logger.info(f"Using model: {config.llm_model}")
    logger.info(f"TTS voice: {config.tts_voice}")
    
    # Run the agent
    run_agent(config, scenario)


if __name__ == "__main__":
    main()
