"""Session state management."""

from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime


@dataclass
class Turn:
    """Single interview turn."""
    turn_number: int
    candidate_transcript: str
    interviewer_response: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SessionState:
    """Interview session state."""
    scenario: str
    turn_count: int = 0
    current_phase: str = "requirements_gathering"
    turns: List[Turn] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_turn(self, transcript: str, response: dict) -> None:
        """Add a turn to the session."""
        self.turn_count += 1
        turn = Turn(
            turn_number=self.turn_count,
            candidate_transcript=transcript,
            interviewer_response=response
        )
        self.turns.append(turn)
    
    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "scenario": self.scenario,
            "turn_count": self.turn_count,
            "current_phase": self.current_phase,
            "started_at": self.started_at,
            "turns": [
                {
                    "turn_number": t.turn_number,
                    "candidate": t.candidate_transcript,
                    "interviewer": t.interviewer_response,
                    "timestamp": t.timestamp
                }
                for t in self.turns
            ]
        }
