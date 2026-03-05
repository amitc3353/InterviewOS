"""Async pub/sub manager for real-time transcript events."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TranscriptEvent:
    """A single transcript event to be sent over WebSocket."""

    def __init__(
        self,
        speaker: str,
        text: str,
        phase: str,
        turn_number: int,
        timestamp: Optional[str] = None,
    ) -> None:
        self.speaker = speaker
        self.text = text
        self.phase = phase
        self.turn_number = turn_number
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON transmission."""
        return {
            "speaker": self.speaker,
            "text": self.text,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "turn_number": self.turn_number,
        }


class TranscriptEventManager:
    """
    Manages real-time transcript event subscriptions.

    Interview agents publish events; WebSocket clients subscribe to receive them.
    Each session can have multiple subscribers (e.g., multiple browser tabs).
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        """
        Subscribe to transcript events for a session.

        Returns:
            An asyncio.Queue that will receive TranscriptEvent objects.
        """
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            if session_id not in self._subscribers:
                self._subscribers[session_id] = []
            self._subscribers[session_id].append(queue)
        logger.debug(f"Client subscribed to session {session_id}")
        return queue

    async def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber's queue from the session."""
        async with self._lock:
            if session_id in self._subscribers:
                try:
                    self._subscribers[session_id].remove(queue)
                except ValueError:
                    pass
                if not self._subscribers[session_id]:
                    del self._subscribers[session_id]
        logger.debug(f"Client unsubscribed from session {session_id}")

    async def publish(self, session_id: str, event: TranscriptEvent) -> None:
        """
        Publish a transcript event to all subscribers of a session.

        Non-blocking: drops events if a subscriber's queue is full.
        """
        async with self._lock:
            queues = self._subscribers.get(session_id, [])

        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    f"Subscriber queue full for session {session_id}, dropping event"
                )

    def publish_sync(self, session_id: str, event: TranscriptEvent) -> None:
        """
        Synchronously publish an event to all subscribers of a session.

        Thread-safe alternative to publish() for use from non-async contexts
        (e.g., test code running outside the ASGI event loop). Bypasses the
        async lock and calls put_nowait() directly.
        """
        queues = self._subscribers.get(session_id, [])
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    f"Subscriber queue full for session {session_id}, dropping event"
                )

    def subscriber_count(self, session_id: str) -> int:
        """Return the number of active subscribers for a session."""
        return len(self._subscribers.get(session_id, []))


# Module-level singleton — shared between agent and WebSocket router
_manager = TranscriptEventManager()


def get_transcript_manager() -> TranscriptEventManager:
    """Return the global TranscriptEventManager instance."""
    return _manager
