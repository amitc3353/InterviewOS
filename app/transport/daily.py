"""Daily.co transport - Phase 2 (future implementation)."""

from app.transport.base import Transport
from app.engine import InterviewEngine


class DailyTransport(Transport):
    """
    Daily.co WebRTC transport.

    Phase 2: Full-duplex voice loop via Daily.co
    - WebRTC rooms
    - VAD (Voice Activity Detection)
    - Echo cancellation
    - Web-accessible

    NOT IMPLEMENTED YET - Placeholder for Phase 2
    """

    def __init__(self, room_url: str):
        """
        Initialize Daily.co transport.

        Args:
            room_url: Daily.co room URL
        """
        self.room_url = room_url
        raise NotImplementedError("Phase 2 - Daily.co transport not implemented yet")

    def run(self, engine: InterviewEngine) -> None:
        """Run interview loop via Daily.co."""
        raise NotImplementedError("Phase 2 - Daily.co transport not implemented yet")
