"""Sentry context management for interview sessions."""

from typing import Dict, Optional

import sentry_sdk

from ..models.session import SessionState
from ..structured_logging import get_logger

logger = get_logger(__name__)


def set_interview_context(session_id: str, state: Optional[SessionState] = None) -> None:
    """
    Set Sentry context with interview session information.

    This tags all subsequent Sentry events with session metadata
    for easier debugging and tracking.

    Args:
        session_id: Unique session identifier
        state: Optional SessionState to extract additional context
    """
    try:
        # Set user context (session_id as user identifier)
        sentry_sdk.set_user({"id": session_id})

        # Set tags
        tags: Dict[str, str] = {
            "session_id": session_id,
        }

        if state:
            tags["turn_number"] = str(state.total_turn_count)
            tags["phase"] = state.phase.value
            tags["phase_turn_count"] = str(state.phase_turn_count)

        for key, value in tags.items():
            sentry_sdk.set_tag(key, value)

        # Set context with detailed session state
        if state:
            sentry_sdk.set_context("interview_session", {
                "session_id": session_id,
                "total_turns": state.total_turn_count,
                "phase": state.phase.value,
                "phase_turns": state.phase_turn_count,
                "elapsed_seconds": state.elapsed_seconds(),
                "phase_elapsed_seconds": state.phase_elapsed_seconds(),
                "locked_constraints_count": len(state.locked_constraints),
            })

    except Exception as e:
        # Never let Sentry context setting break the application
        logger.warning(f"Failed to set Sentry context: {e}")


def update_turn_context(state: SessionState) -> None:
    """
    Update Sentry context with current turn information.

    Call this after each turn to keep context fresh.

    Args:
        state: Current SessionState
    """
    try:
        sentry_sdk.set_tag("turn_number", str(state.total_turn_count))
        sentry_sdk.set_tag("phase_turn_count", str(state.phase_turn_count))

        # Update context
        sentry_sdk.set_context("interview_session", {
            "total_turns": state.total_turn_count,
            "phase": state.phase.value,
            "phase_turns": state.phase_turn_count,
            "elapsed_seconds": state.elapsed_seconds(),
            "phase_elapsed_seconds": state.phase_elapsed_seconds(),
            "locked_constraints_count": len(state.locked_constraints),
        })

    except Exception as e:
        logger.warning(f"Failed to update Sentry turn context: {e}")


def capture_exception_with_context(
    exception: Exception,
    session_id: str,
    state: Optional[SessionState] = None,
    extra_context: Optional[Dict] = None
) -> None:
    """
    Capture an exception with full interview context.

    Args:
        exception: Exception to capture
        session_id: Session identifier
        state: Optional SessionState for additional context
        extra_context: Optional additional context dict
    """
    try:
        # Set context first
        set_interview_context(session_id, state)

        # Add any extra context
        if extra_context:
            sentry_sdk.set_context("extra", extra_context)

        # Capture the exception
        sentry_sdk.capture_exception(exception)

    except Exception as e:
        logger.warning(f"Failed to capture exception in Sentry: {e}")
