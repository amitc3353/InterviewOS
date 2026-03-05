"""JSON filesystem storage for interview sessions."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Default storage directory
DEFAULT_STORAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "sessions",
)


class SessionStorage:
    """Persists interview sessions to JSON files on the filesystem."""

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        self.storage_dir = storage_dir or DEFAULT_STORAGE_DIR
        os.makedirs(self.storage_dir, exist_ok=True)

    def _session_path(self, session_id: str) -> str:
        """Return the file path for a given session ID.

        Raises:
            ValueError: If session_id contains path traversal characters.
        """
        safe_id = os.path.basename(session_id)
        if not safe_id or safe_id != session_id:
            raise ValueError(f"Invalid session ID format: {session_id}")
        return os.path.join(self.storage_dir, f"{safe_id}.json")

    def save(self, session_data: Dict) -> None:
        """
        Save session data to a JSON file.

        Args:
            session_data: Dictionary with at least a 'session_id' key.
        """
        session_id = session_data["session_id"]
        path = self._session_path(session_id)
        try:
            with open(path, "w") as f:
                json.dump(session_data, f, indent=2, default=str)
            logger.debug(f"Session saved: {session_id}")
        except OSError as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            raise

    def load(self, session_id: str) -> Optional[Dict]:
        """
        Load a session by ID.

        Returns:
            Session data dict or None if not found.
        """
        path = self._session_path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    def list_sessions(self) -> List[Dict]:
        """
        List all saved sessions, sorted by creation time (newest first).

        Returns:
            List of session data dicts.
        """
        sessions: List[Dict] = []
        try:
            for filename in os.listdir(self.storage_dir):
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(self.storage_dir, filename)
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    sessions.append(data)
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(f"Skipping corrupt session file {filename}: {e}")
        except OSError as e:
            logger.error(f"Failed to list sessions: {e}")

        # Sort by created_at descending (newest first)
        sessions.sort(
            key=lambda s: s.get("created_at", ""),
            reverse=True,
        )
        return sessions

    def delete(self, session_id: str) -> bool:
        """
        Delete a session by ID.

        Returns:
            True if deleted, False if not found.
        """
        path = self._session_path(session_id)
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
            logger.debug(f"Session deleted: {session_id}")
            return True
        except OSError as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
