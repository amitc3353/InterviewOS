"""WebSocket endpoint for real-time transcript streaming."""

import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.storage import SessionStorage
from backend.api.transcript_manager import TranscriptEvent, get_transcript_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["websocket"])

# Module-level storage instance — can be overridden for testing
_storage = SessionStorage()


def _get_storage() -> SessionStorage:
    """Return the current storage instance."""
    return _storage


def _history_entry_to_message(
    entry: Dict[str, Any], index: int, phase: str
) -> Dict[str, Any]:
    """Convert a conversation_history entry to WebSocket message format."""
    role = entry.get("role", "")
    speaker = "interviewer" if role == "assistant" else "candidate"
    return {
        "speaker": speaker,
        "text": entry.get("content", ""),
        "timestamp": entry.get("timestamp", ""),
        "phase": phase,
        "turn_number": index,
    }


@router.websocket("/{session_id}/transcript")
async def transcript_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    Stream transcript events for an interview session in real-time.

    On connect:
      - Validates session_id exists in storage
      - Sends existing conversation history as initial messages
      - Subscribes to new transcript events from the interview agent

    Message format:
      {
        "speaker": "interviewer" | "candidate",
        "text": "...",
        "timestamp": "ISO8601",
        "phase": "intro" | "scope" | ...,
        "turn_number": int
      }

    Closes with code 4004 if session not found, 4000 on invalid session ID.
    """
    storage = _get_storage()

    # Validate session ID format
    try:
        data = storage.load(session_id)
    except ValueError:
        await websocket.close(code=4000, reason="Invalid session ID format")
        return

    if data is None:
        await websocket.close(code=4004, reason=f"Session {session_id} not found")
        return

    await websocket.accept()
    logger.info(f"WebSocket connected for session {session_id}")

    manager = get_transcript_manager()
    queue = await manager.subscribe(session_id)

    try:
        # Send existing conversation history
        history: List[Dict] = data.get("conversation_history", [])
        phase = data.get("phase", "intro")
        for idx, entry in enumerate(history):
            message = _history_entry_to_message(entry, idx, phase)
            await websocket.send_json(message)

        # Stream new events as they arrive
        while True:
            try:
                event: TranscriptEvent = await asyncio.wait_for(
                    queue.get(), timeout=30.0
                )
                await websocket.send_json(event.to_dict())
            except asyncio.TimeoutError:
                # Send keepalive ping to detect stale connections
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        await manager.unsubscribe(session_id, queue)
        logger.debug(f"WebSocket cleanup complete for session {session_id}")
