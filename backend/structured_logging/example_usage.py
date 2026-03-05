"""Example usage of structured logging in InterviewOS.

This file demonstrates best practices for integrating structured logging
into interview agents and related components.
"""

import asyncio
import uuid
from typing import Optional

from backend.structured_logging import get_logger, set_global_context, clear_global_context
from backend.config import AgentConfig


# ---------------------------------------------------------------------------
# Example 1: Basic Logging
# ---------------------------------------------------------------------------

def example_basic_logging():
    """Basic logging with event types."""
    logger = get_logger(__name__)

    # Simple info log
    logger.info("Application started", event_type="app_start")

    # Warning with context
    logger.warning(
        "Using fallback TTS provider",
        event_type="tts_fallback",
        reason="primary_unavailable"
    )

    # Error with extra fields
    logger.error(
        "LLM request failed",
        event_type="llm_error",
        retry_count=2,
        elapsed_ms=12000
    )


# ---------------------------------------------------------------------------
# Example 2: Session-Level Context
# ---------------------------------------------------------------------------

def example_session_context():
    """Using global context for session-level logging."""
    logger = get_logger(__name__)

    # Generate session ID
    session_id = str(uuid.uuid4())

    # Set global context once at session start
    set_global_context(session_id=session_id)

    # All subsequent logs automatically include session_id
    logger.info("Session initialized", event_type="session_start")
    logger.info("Phase advanced to scope", event_type="phase_transition")

    # Clean up at session end
    clear_global_context()


# ---------------------------------------------------------------------------
# Example 3: Async Logging in Voice Loop
# ---------------------------------------------------------------------------

async def example_async_logging():
    """Non-blocking async logging for real-time scenarios."""
    logger = get_logger(__name__)
    session_id = str(uuid.uuid4())

    set_global_context(session_id=session_id)

    # Simulate voice loop turns
    for turn in range(1, 6):
        # Use async methods to prevent I/O blocking
        await logger.info_async(
            f"Processing turn {turn}",
            event_type="turn_start",
            turn_number=turn
        )

        # Simulate processing
        await asyncio.sleep(0.1)

        await logger.info_async(
            f"Turn {turn} completed",
            event_type="turn_complete",
            turn_number=turn,
            latency_ms=100
        )

    clear_global_context()


# ---------------------------------------------------------------------------
# Example 4: Interview Agent Integration
# ---------------------------------------------------------------------------

class ExampleInterviewAgent:
    """Example agent with structured logging."""

    def __init__(self, config: AgentConfig, scenario: str):
        """Initialize agent with structured logging."""
        self.config = config
        self.scenario = scenario
        self.session_id = str(uuid.uuid4())
        self.turn_number = 0

        # Get logger for this class
        self.logger = get_logger(__name__)

        # Set global context
        set_global_context(session_id=self.session_id)

        # Log session start
        self.logger.info(
            "Interview agent initialized",
            event_type="session_start",
            scenario=scenario
        )

    async def handle_turn(self, user_text: str) -> str:
        """Handle user turn with async logging."""
        self.turn_number += 1

        # Log turn start (async to prevent blocking)
        await self.logger.info_async(
            "Processing user turn",
            event_type="turn_start",
            turn_number=self.turn_number,
            text_length=len(user_text)
        )

        try:
            # Simulate LLM processing
            response = await self._generate_response(user_text)

            # Log success
            await self.logger.info_async(
                "Turn completed successfully",
                event_type="turn_complete",
                turn_number=self.turn_number,
                response_length=len(response)
            )

            return response

        except Exception as e:
            # Log error with exception info
            await self.logger.error_async(
                f"Turn failed: {e}",
                event_type="turn_error",
                turn_number=self.turn_number,
                exc_info=True
            )
            raise

    async def _generate_response(self, user_text: str) -> str:
        """Simulate LLM response generation."""
        await asyncio.sleep(0.1)
        return f"Response to: {user_text}"

    def close(self):
        """Clean up session."""
        self.logger.info(
            "Session ended",
            event_type="session_end",
            total_turns=self.turn_number
        )
        clear_global_context()


# ---------------------------------------------------------------------------
# Example 5: Error Handling with Retry Logic
# ---------------------------------------------------------------------------

async def example_error_handling():
    """Error handling with structured logging."""
    logger = get_logger(__name__)
    session_id = str(uuid.uuid4())

    set_global_context(session_id=session_id)

    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Simulate operation that might fail
            if retry_count < 2:
                raise TimeoutError("LLM timeout")

            await logger.info_async(
                "Operation succeeded",
                event_type="llm_success",
                retry_count=retry_count
            )
            break

        except TimeoutError as e:
            retry_count += 1

            if retry_count < max_retries:
                # Log warning for retryable error
                await logger.warning_async(
                    f"LLM timeout, retrying ({retry_count}/{max_retries})",
                    event_type="llm_timeout_retry",
                    retry_count=retry_count,
                    error=str(e)
                )
            else:
                # Log error for exhausted retries
                await logger.error_async(
                    "LLM retries exhausted",
                    event_type="llm_retry_exhausted",
                    retry_count=retry_count,
                    exc_info=True
                )
                raise

    clear_global_context()


# ---------------------------------------------------------------------------
# Example 6: Phase Transition Logging
# ---------------------------------------------------------------------------

async def example_phase_transitions():
    """Logging phase transitions with context."""
    logger = get_logger(__name__)
    session_id = str(uuid.uuid4())

    set_global_context(session_id=session_id)

    phases = ["intro", "scope", "architecture", "deep_dive", "wrap"]
    turn_number = 0

    for phase in phases:
        turn_number += 1

        await logger.info_async(
            f"Advancing to {phase} phase",
            event_type="phase_transition",
            turn_number=turn_number,
            phase=phase,
            previous_phase=phases[phases.index(phase) - 1] if phase != "intro" else None
        )

        # Simulate phase work
        await asyncio.sleep(0.1)

    clear_global_context()


# ---------------------------------------------------------------------------
# Example 7: Complete Session Lifecycle
# ---------------------------------------------------------------------------

async def example_complete_session():
    """Complete session lifecycle with structured logging."""
    # Initialize config and logging
    config = AgentConfig.from_env()
    config.init_logging()  # Initialize structured logging

    # Create agent
    agent = ExampleInterviewAgent(config, scenario="Design a URL shortener")

    try:
        # Simulate interview turns
        user_inputs = [
            "What are the requirements?",
            "How would you design this?",
            "What about scalability?"
        ]

        for user_text in user_inputs:
            response = await agent.handle_turn(user_text)
            print(f"Agent: {response}")

    finally:
        # Clean up
        agent.close()


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Example 1: Basic Logging ===")
    example_basic_logging()
    print()

    print("=== Example 2: Session Context ===")
    example_session_context()
    print()

    print("=== Example 3: Async Logging ===")
    asyncio.run(example_async_logging())
    print()

    print("=== Example 4: Error Handling ===")
    asyncio.run(example_error_handling())
    print()

    print("=== Example 5: Phase Transitions ===")
    asyncio.run(example_phase_transitions())
    print()

    print("=== Example 6: Complete Session ===")
    # Uncomment to run (requires valid .env configuration)
    # asyncio.run(example_complete_session())
