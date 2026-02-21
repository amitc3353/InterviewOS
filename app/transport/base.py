"""Base transport interface."""

from abc import ABC, abstractmethod
from app.engine import InterviewEngine


class Transport(ABC):
    """
    Base transport interface.

    Defines contract for all transport implementations (local mic, Daily.co, etc.)
    """

    @abstractmethod
    def run(self, engine: InterviewEngine) -> None:
        """
        Run the interview loop.

        Args:
            engine: InterviewEngine instance to drive the conversation
        """
        pass
