"""Session management endpoints."""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.api.models import (
    CreateSessionRequest,
    FeedbackResponse,
    SessionListResponse,
    SessionResponse,
    SessionStateResponse,
)
from backend.api.storage import SessionStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Module-level storage instance — can be overridden for testing
_storage = SessionStorage()

# Default scorecards directory
_SCORECARDS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    )))),
    "data",
    "scorecards",
)


def _get_storage() -> SessionStorage:
    """Return the current storage instance."""
    return _storage


def _get_scorecards_dir() -> str:
    """Return the path to the scorecards directory."""
    return _SCORECARDS_DIR


def _create_livekit_room(room_name: str) -> Optional[str]:
    """
    Create a LiveKit room via RoomServiceClient.

    Returns the room name on success, None if LiveKit is unavailable.
    """
    try:
        import os

        from livekit.api import LiveKitAPI

        livekit_url = os.getenv("LIVEKIT_URL", "")
        api_key = os.getenv("LIVEKIT_API_KEY", "")
        api_secret = os.getenv("LIVEKIT_API_SECRET", "")

        if not all([livekit_url, api_key, api_secret]):
            logger.warning("LiveKit credentials not configured, skipping room creation")
            return room_name

        api = LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)
        api.room.create_room(name=room_name)
        logger.info(f"LiveKit room created: {room_name}")
        return room_name
    except ImportError:
        logger.warning("livekit package not installed, skipping room creation")
        return room_name
    except Exception as e:
        logger.error(f"Failed to create LiveKit room: {e}")
        return room_name


def _session_data_to_response(data: dict) -> SessionResponse:
    """Convert stored session data to SessionResponse."""
    return SessionResponse(
        session_id=data["session_id"],
        scenario=data["scenario"],
        phase=data.get("phase", "intro"),
        locked_constraints=data.get("locked_constraints", {}),
        total_turns=data.get("total_turns", 0),
        elapsed_seconds=data.get("elapsed_seconds", 0.0),
        livekit_room_name=data.get("livekit_room_name"),
        created_at=data.get("created_at", ""),
    )


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(request: CreateSessionRequest) -> SessionResponse:
    """
    Create a new interview session.

    Creates an InterviewSession, optionally creates a LiveKit room,
    and persists the session to storage.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now()
    room_name = f"interview-{session_id[:8]}"

    # Attempt LiveKit room creation
    livekit_room = _create_livekit_room(room_name)

    session_data = {
        "session_id": session_id,
        "scenario": request.scenario,
        "phase": "intro",
        "locked_constraints": {},
        "conversation_history": [],
        "transcript": [],
        "metadata": {
            "candidate_name": request.candidate_name,
        },
        "scorecard": None,
        "session_start_time": now.isoformat(),
        "created_at": now.isoformat(),
        "elapsed_seconds": 0.0,
        "total_turns": 0,
        "livekit_room_name": livekit_room,
    }

    storage = _get_storage()
    storage.save(session_data)

    logger.info(f"Session created: {session_id} scenario={request.scenario}")

    return _session_data_to_response(session_data)


@router.get("", response_model=SessionListResponse)
def list_sessions() -> SessionListResponse:
    """List all past interview sessions."""
    storage = _get_storage()
    sessions = storage.list_sessions()
    return SessionListResponse(
        sessions=[_session_data_to_response(s) for s in sessions],
        total=len(sessions),
    )


@router.get("/{session_id}/state", response_model=SessionStateResponse)
def get_session_state(session_id: str) -> SessionStateResponse:
    """
    Get current state of an interview session.

    Returns phase, locked_constraints, turn_count, and conversation history.
    """
    storage = _get_storage()
    try:
        data = storage.load(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if data is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    return SessionStateResponse(
        session_id=data["session_id"],
        phase=data.get("phase", "intro"),
        locked_constraints=data.get("locked_constraints", {}),
        turn_count=data.get("total_turns", 0),
        phase_turn_count=data.get("phase_turn_count", 0),
        elapsed_seconds=data.get("elapsed_seconds", 0.0),
        conversation_history=data.get("conversation_history", []),
    )


@router.get("/{session_id}/feedback", response_model=FeedbackResponse)
def get_session_feedback(session_id: str) -> FeedbackResponse:
    """
    Get post-interview feedback scorecard for the session.

    Reads and parses data/scorecards/{session_id}.json.
    """
    # Validate session ID format via storage path check
    storage = _get_storage()
    try:
        storage._session_path(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    scorecard_path = os.path.join(_get_scorecards_dir(), f"{session_id}.json")

    if not os.path.exists(scorecard_path):
        raise HTTPException(
            status_code=404,
            detail=f"Feedback not found for session {session_id}",
        )

    try:
        with open(scorecard_path, "r") as f:
            scorecard_data = json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Invalid scorecard data")
    except Exception as e:
        logger.error(f"Failed to read scorecard: {e}")
        raise HTTPException(status_code=500, detail="Failed to read scorecard")

    return FeedbackResponse(**scorecard_data)
