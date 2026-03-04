"""Test script to verify Sentry integration works end-to-end.

Run this script with SENTRY_DSN configured in .env to verify that:
1. Sentry SDK initializes correctly
2. Session context is set properly
3. Exceptions are captured and sent to GlitchTip/Sentry

Usage:
    python backend/test_sentry.py
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from backend.config import AgentConfig
from backend.models.session import SessionState, InterviewPhase
from backend.interview.sentry_context import (
    set_interview_context,
    capture_exception_with_context,
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Test Sentry integration."""
    logger.info("=" * 80)
    logger.info("Sentry Integration Test")
    logger.info("=" * 80)

    # Load config
    config = AgentConfig.from_env()

    # Initialize Sentry
    logger.info("Initializing Sentry...")
    sentry_initialized = config.init_sentry()

    if not sentry_initialized:
        logger.warning("Sentry not initialized. Check SENTRY_DSN in .env")
        logger.warning("If Sentry is disabled or no DSN provided, this is expected.")
        return

    logger.info("✓ Sentry initialized successfully")
    logger.info(f"  Environment: {config.sentry_environment}")
    logger.info(f"  DSN configured: {config.sentry_dsn[:30]}...")

    # Create test session state
    logger.info("\nCreating test session state...")
    state = SessionState()
    state.phase = InterviewPhase.ARCHITECTURE
    state.total_turn_count = 10
    state.phase_turn_count = 3
    state.add_locked_constraint("database", "PostgreSQL")
    state.add_locked_constraint("cache", "Redis")

    session_id = "test-sentry-session-12345"

    # Set Sentry context
    logger.info("Setting Sentry context...")
    set_interview_context(session_id, state)
    logger.info("✓ Sentry context set")
    logger.info(f"  Session ID: {session_id}")
    logger.info(f"  Turn: {state.total_turn_count}")
    logger.info(f"  Phase: {state.phase.value}")

    # Test exception capture
    logger.info("\nTesting exception capture...")
    logger.info("Raising a test exception...")

    try:
        # Raise a test exception
        raise ValueError("Test exception from Sentry integration test")
    except Exception as e:
        logger.info("Capturing exception with context...")
        capture_exception_with_context(
            exception=e,
            session_id=session_id,
            state=state,
            extra_context={
                "test_type": "integration_test",
                "test_timestamp": "2026-03-04",
                "expected": True,
            }
        )
        logger.info("✓ Exception captured and sent to Sentry")

    logger.info("\n" + "=" * 80)
    logger.info("Test complete! Check your GlitchTip/Sentry dashboard:")
    logger.info("  - Look for the 'ValueError: Test exception' event")
    logger.info("  - Verify tags: session_id, turn_number, phase")
    logger.info("  - Verify context: interview_session, extra")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
