"""LiveKit token generation endpoint."""

import os

from fastapi import APIRouter, HTTPException

from backend.api.models import TokenResponse
from backend.api.storage import SessionStorage
from backend.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["tokens"])

# Module-level storage instance — can be overridden for testing
_storage = SessionStorage()


def _get_storage() -> SessionStorage:
    """Return the current storage instance."""
    return _storage


@router.get("/{session_id}/token", response_model=TokenResponse)
def get_session_token(session_id: str) -> TokenResponse:
    """
    Generate a LiveKit participant token for the session.

    Returns a JWT with room join and publish permissions.
    """
    storage = _get_storage()
    try:
        data = storage.load(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if data is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    room_name = data.get("livekit_room_name")
    if not room_name:
        raise HTTPException(status_code=400, detail="Session has no LiveKit room")

    api_key = os.getenv("LIVEKIT_API_KEY", "")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=500, detail="LiveKit credentials not configured"
        )

    try:
        from livekit.api import AccessToken, VideoGrants

        token = AccessToken(api_key=api_key, api_secret=api_secret)
        token.with_identity(f"participant-{session_id[:8]}")
        token.with_grants(VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        ))
        jwt_str = token.to_jwt()
    except ImportError:
        raise HTTPException(
            status_code=500, detail="livekit package not installed"
        )
    except Exception as e:
        logger.error(f"Failed to generate token: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate token")

    return TokenResponse(token=jwt_str, room_name=room_name)
